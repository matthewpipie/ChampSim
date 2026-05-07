/*
 *    Copyright 2023 The ChampSim Contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "champsim.h"

#include <algorithm>
#include <chrono>
#include <numeric>
#include <vector>
#include <fmt/chrono.h>
#include <fmt/core.h>

#include "environment.h"
#include "event_listeners.h"
#include "ooo_cpu.h"
#include "operable.h"
#include "phase_info.h"
#include "tracereader.h"

constexpr int DEADLOCK_CYCLE{500};

const auto start_time = std::chrono::steady_clock::now();

std::chrono::seconds elapsed_time() { return std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now() - start_time); }

namespace champsim
{
long do_cycle(environment& env, std::vector<tracereader>& traces, std::vector<std::size_t> trace_index, champsim::chrono::clock& global_clock)
{
  auto operables = env.operable_view();
  std::sort(std::begin(operables), std::end(operables),
            [](const champsim::operable& lhs, const champsim::operable& rhs) { return lhs.current_time < rhs.current_time; });

  // Operate
  long progress{0};
  for (champsim::operable& op : operables) {
    progress += op.operate_on(global_clock);
  }

  // Read from trace
  for (O3_CPU& cpu : env.cpu_view()) {
    //cpu is halted, don't provide instructions
    if(cpu.halt)
      continue;

    auto& trace = traces.at(trace_index.at(cpu.cpu));
    for (auto pkt_count = cpu.IN_QUEUE_SIZE - static_cast<long>(std::size(cpu.input_queue)); !trace.eof() && pkt_count > 0; --pkt_count) {
      cpu.input_queue.push_back(trace());
    }
  }

  return progress;
}

phase_stats do_phase(const phase_info& phase, environment& env, std::vector<tracereader>& traces, champsim::chrono::clock& global_clock)
{
  auto operables = env.operable_view();
  auto [phase_name, is_warmup, length, trace_index, trace_names] = phase;

  // Initialize phase
  for (champsim::operable& op : operables) {
    //op.warmup = is_warmup;
    op.warmup = false;
    op.halt = false;
    op.begin_phase();
  }

  const auto time_quantum = std::accumulate(std::cbegin(operables), std::cend(operables), champsim::chrono::clock::duration::max(),
                                            [](const auto acc, const operable& y) { return std::min(acc, y.clock_period); });

  bool livelock_trigger{false};
  uint64_t livelock_period{10000000};
  uint64_t livelock_timer{0};
  //                                   die | critical | warning
  std::vector<double> livelock_threshold{0.01, 0.02, 0.05};
  std::vector<uint64_t> livelock_instr(std::size(env.cpu_view()), 0);

  // Perform phase
  int stalled_cycle{0};
  std::vector<bool> phase_complete(std::size(env.cpu_view()), false);
  while (!std::accumulate(std::begin(phase_complete), std::end(phase_complete), true, std::logical_and{})) {
    auto next_phase_complete = phase_complete;
    global_clock.tick(time_quantum);

    auto progress = do_cycle(env, traces, trace_index, global_clock);

    if (progress == 0) {
      ++stalled_cycle;
    } else {
      stalled_cycle = 0;
    }

    // Livelock detect, every livelock_period cycles, check progress and alert the user
    livelock_timer++;
    if (livelock_timer >= livelock_period) {
      // for each cpu
      for (O3_CPU& cpu : env.cpu_view()) {
        // cpu is halted, don't check for livelock
        if(cpu.halt)
          continue;

        // for each threshold
        for (auto thres = std::begin(livelock_threshold); thres != std::end(livelock_threshold); thres++) {
          double livelock_ipc = std::ceil(cpu.sim_instr() - livelock_instr[cpu.cpu]) / std::ceil(livelock_period);
          if (livelock_ipc <= *thres) {
            if (std::distance(std::begin(livelock_threshold), thres) == 0) {
              livelock_trigger = true;
              fmt::print("{} CPU {} panic: IPC {:.5g} < {:.5g}\n", phase_name, cpu.cpu, livelock_ipc, *thres);
            } else if (std::distance(std::begin(livelock_threshold), thres) == 1)
              fmt::print("{} CPU {} critical: IPC {:.5g} < {:.5g}\n", phase_name, cpu.cpu, livelock_ipc, *thres);
            else
              fmt::print("{} CPU {} warning: IPC {:.5g} < {:.5g}\n", phase_name, cpu.cpu, livelock_ipc, *thres);

            break;
          }
        }
        livelock_instr[cpu.cpu] = cpu.sim_instr();
      }
      livelock_timer = 0;
    }

    if (stalled_cycle >= DEADLOCK_CYCLE || livelock_trigger) {
      std::for_each(std::begin(operables), std::end(operables), [](champsim::operable& c) { c.print_deadlock(); });
      abort();
    }

    // If any trace reaches EOF, terminate all phases
    if (std::any_of(std::begin(traces), std::end(traces), [](const auto& tr) { return tr.eof(); })) {
      std::fill(std::begin(next_phase_complete), std::end(next_phase_complete), true);
    }

    // Check for phase finish
    for (O3_CPU& cpu : env.cpu_view()) {
      // Phase complete
      next_phase_complete[cpu.cpu] = next_phase_complete[cpu.cpu] || (cpu.sim_instr() >= length);

      //halt cpu if warmup
      if(next_phase_complete[cpu.cpu] && is_warmup && !cpu.halt) {
        cpu.halt = true;
        fmt::print("{} halting CPU {} at instruction {} cycle {} for remainder of phase\n", phase_name, cpu.cpu, cpu.sim_instr(), cpu.sim_cycle());
      }
    }

    for (O3_CPU& cpu : env.cpu_view()) {
      if (next_phase_complete[cpu.cpu] != phase_complete[cpu.cpu]) {
        for (champsim::operable& op : operables) {
          op.end_phase(cpu.cpu);
        }

        fmt::print("{} finished CPU {} instructions: {} cycles: {} cumulative IPC: {:.4g} (Simulation time: {:%H hr %M min %S sec})\n", phase_name, cpu.cpu,
                   cpu.sim_instr(), cpu.sim_cycle(), std::ceil(cpu.sim_instr()) / std::ceil(cpu.sim_cycle()), elapsed_time());
      }
    }

    phase_complete = next_phase_complete;
  }

  for (O3_CPU& cpu : env.cpu_view()) {
    fmt::print("{} complete CPU {} instructions: {} cycles: {} cumulative IPC: {:.4g} (Simulation time: {:%H hr %M min %S sec})\n", phase_name, cpu.cpu,
               cpu.sim_instr(), cpu.sim_cycle(), std::ceil(cpu.sim_instr()) / std::ceil(cpu.sim_cycle()), elapsed_time());
  }

  phase_stats stats;
  stats.name = phase.name;

  for (std::size_t i = 0; i < std::size(trace_index); ++i) {
    stats.trace_names.push_back(trace_names.at(trace_index.at(i)));
  }

  auto cpus = env.cpu_view();
  std::transform(std::begin(cpus), std::end(cpus), std::back_inserter(stats.sim_cpu_stats), [](const O3_CPU& cpu) { return cpu.sim_stats; });
  std::transform(std::begin(cpus), std::end(cpus), std::back_inserter(stats.roi_cpu_stats), [](const O3_CPU& cpu) { return cpu.roi_stats; });

  auto caches = env.cache_view();
  std::transform(std::begin(caches), std::end(caches), std::back_inserter(stats.sim_cache_stats), [](const CACHE& cache) { return cache.sim_stats; });
  std::transform(std::begin(caches), std::end(caches), std::back_inserter(stats.roi_cache_stats), [](const CACHE& cache) { return cache.roi_stats; });

  auto dram = env.dram_view();
  std::transform(std::begin(dram.channels), std::end(dram.channels), std::back_inserter(stats.sim_dram_stats),
                 [](const DRAM_CHANNEL& chan) { return chan.sim_stats; });
  std::transform(std::begin(dram.channels), std::end(dram.channels), std::back_inserter(stats.roi_dram_stats),
                 [](const DRAM_CHANNEL& chan) { return chan.roi_stats; });

  return stats;
}

// simulation entry point
std::vector<phase_stats> main(environment& env, std::vector<phase_info>& phases, std::vector<tracereader>& traces)
{
  for (champsim::operable& op : env.operable_view()) {
    op.initialize();
  }

  champsim::chrono::clock global_clock;
  std::vector<phase_stats> results;
  for (auto phase : phases) {
    // call event listeners
    handle_event<Event::BEGIN_PHASE>(phase.is_warmup);
    // handle_begin_phase(0, phase.is_warmup);

    auto stats = do_phase(phase, env, traces, global_clock);
    //if (!phase.is_warmup) {
    if (!phase.is_warmup && phase.name.compare("Warmup") != 0) {
      results.push_back(stats);
    }
  }

  return results;
}

uint64_t cumsum(std::vector<uint64_t> &v, size_t p) {
    uint64_t cumsum = 0;
    for (size_t ii = 0; ii < p; ii++) {
        cumsum += v[ii];
    }
    return cumsum;
}
void make_print_hist(std::string prologue, std::vector<uint64_t> &v) {
    // create histogram from raw data
    uint64_t sum = 0;
    uint64_t uniq = 0;
    std::unordered_map<uint64_t, uint64_t> hist;
    std::unordered_map<uint64_t, uint64_t> bin_hist;
    std::sort(v.begin(), v.end());
    for (auto &i : v) {
        if (hist[i] == 0) uniq++;
        hist[i]++;
        sum += i;
        bin_hist[64 - __builtin_clzll(i)]++;
    }
    for (size_t i = 0; i < 100; i++) {
        size_t p = i*v.size() / 100;
        fmt::print("{} p{} {} {}\n", prologue, i, v[p], cumsum(v, p));
    }
    for (size_t i = 991; i < 1000; i++) {
        size_t p = i*v.size() / 1000;
        fmt::print("{} p99.{} {} {}\n", prologue, i-990, v[p], cumsum(v, p));
    }
    for (size_t i = 9991; i < 10000; i++) {
        size_t p = i*v.size() / 10000;
        fmt::print("{} p99.9{} {} {}\n", prologue, i-9990, v[p], cumsum(v, p));
    }
    for (size_t i = 99991; i < 100000; i++) {
        size_t p = i*v.size() / 100000;
        fmt::print("{} p99.99{} {} {}\n", prologue, i-99990, v[p], cumsum(v, p));
    }
    for (size_t i = 999991; i < 1000000; i++) {
        size_t p = i*v.size() / 1000000;
        fmt::print("{} p99.999{} {} {}\n", prologue, i-999990, v[p], cumsum(v, p));
    }
    fmt::print("{} p100 {} {}\n", prologue, v.back(), sum);
    fmt::print("{} cnt {}\n", prologue, v.size());
    fmt::print("{} sum {}\n", prologue, sum);
    fmt::print("{} uniq {}\n", prologue, uniq);
    fmt::print("{} v0 {}\n", prologue, hist[0]);
    fmt::print("{} v1 {}\n", prologue, hist[1]);
    fmt::print("{} v2 {}\n", prologue, hist[2]);
    for (auto &[k, v] : bin_hist) {
        fmt::print("{} bin{} {}\n", prologue, k, v);
    }
}

void study_trace(std::vector<phase_info> &phases, tracereader& trace) {
  uint64_t study_instr = 0;
  uint64_t data_access = 0;
  uint64_t instr_access = 0;
  using namespace std;
  unordered_map<uint64_t, vector<uint64_t>> line_uses;
  unordered_map<uint64_t, vector<uint64_t>> line_uses_access;
  vector<uint64_t> reuse_dists;
  vector<uint64_t> reuse_dists_access;
  unordered_map<uint64_t, vector<uint64_t>> i_line_uses;
  vector<uint64_t> i_reuse_dists;
  uint64_t last_branch = 0;
  uint64_t last_taken_branch = 0;
  vector<uint64_t> branch_distances;
  vector<uint64_t> taken_branch_distances;

  for (auto &phase : phases) {
    auto [phase_name, is_warmup, length, trace_index, trace_names] = phase;

    for (int64_t sim_instr = 0; sim_instr < length; sim_instr++) {
      if (trace.eof()) {
        fmt::print("trace file done (shouldn't happen?)\n");
        break;
      }
      ooo_model_instr instr = trace();
      if (!is_warmup) {
        // do studying
        for (auto source : instr.source_memory) {
            uint64_t source_block = source.to<uint64_t>() / 64 * 64;
            auto &v = line_uses[source_block];
            v.push_back(study_instr);
            if (v.size() > 1) {
                reuse_dists.push_back(v.back() - v[v.size() - 2]);
            }
            auto &va = line_uses_access[source_block];
            va.push_back(data_access++);
            if (va.size() > 1) {
                reuse_dists_access.push_back(va.back() - va[va.size() - 2]);
            }
        }
        for (auto dest : instr.destination_memory) {
            uint64_t dest_block = dest.to<uint64_t>() / 64 * 64;
            auto &v = line_uses[dest_block];
            v.push_back(study_instr);
            if (v.size() > 1) {
                reuse_dists.push_back(v.back() - v[v.size() - 2]);
            }
            auto &va = line_uses_access[dest_block];
            va.push_back(data_access++);
            if (va.size() > 1) {
                reuse_dists_access.push_back(va.back() - va[va.size() - 2]);
            }
        }
        uint64_t i_source_block = instr.ip.to<uint64_t>() / 64 * 64;
        auto &i_v = i_line_uses[i_source_block];
        i_v.push_back(study_instr);
        if (i_v.size() > 1) {
            i_reuse_dists.push_back(i_v.back() - i_v[i_v.size() - 2]);
        }

        if (instr.is_branch) {
            branch_distances.push_back(study_instr - last_branch);
            last_branch = study_instr;
            if (instr.branch_taken) {
                taken_branch_distances.push_back(study_instr - last_taken_branch);
                last_taken_branch = study_instr;
            }
        }

        study_instr++;
      }
    }
  }
  fmt::print("Study results:\n");
  vector<uint64_t> line_use_cnts;
  for (auto &[k, v] : line_uses) line_use_cnts.push_back(v.size());
  make_print_hist("data lines", line_use_cnts);

  vector<uint64_t> i_line_use_cnts;
  for (auto &[k, v] : i_line_uses) i_line_use_cnts.push_back(v.size());
  make_print_hist("instruction lines", i_line_use_cnts);

  make_print_hist("data reuse", reuse_dists);
  make_print_hist("data reuse_access", reuse_dists_access);
  make_print_hist("instruction reuse", i_reuse_dists);

  make_print_hist("branch freq", branch_distances);
  make_print_hist("taken_branch freq", taken_branch_distances);

}

} // namespace champsim
