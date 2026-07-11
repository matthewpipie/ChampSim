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

#include <algorithm>
#include <fstream>
#include <numeric>
#include <string>
#include <vector>
#include <CLI/CLI.hpp>
#include <fmt/core.h>
#include <sys/resource.h>

#include "cache.h" // for CACHE
#include "champsim.h"
#ifndef CHAMPSIM_TEST_BUILD
#include "core_inst.inc"
#endif
#include "defaults.hpp"
#include "dpc_api.h"
#include "dynamorio_core_source.h"
#include "dynamorio_source.h"
#include "environment.h"
#include "event_listeners.h"
#include "ooo_cpu.h" // for O3_CPU
#include "phase_info.h"
#include "stats_printer.h"
#include "tracereader.h"
#include "vmem.h"

namespace champsim
{
std::vector<phase_stats> main(environment& env, std::vector<phase_info>& phases, std::vector<tracereader>& traces);
void study_trace(std::vector<phase_info> &phases, tracereader& trace);
}

#ifndef CHAMPSIM_TEST_BUILD
using configured_environment = champsim::configured::generated_environment<CHAMPSIM_BUILD>;

const std::size_t NUM_CPUS = configured_environment::num_cpus;

const unsigned BLOCK_SIZE = configured_environment::block_size;
const unsigned PAGE_SIZE = configured_environment::page_size;
#endif
const unsigned LOG2_BLOCK_SIZE = champsim::lg2(BLOCK_SIZE);
const unsigned LOG2_PAGE_SIZE = champsim::lg2(PAGE_SIZE);

namespace champsim
{
environment* g_env = nullptr;
}

//------------------------------------//
// DPC4 API
//------------------------------------//
uint8_t get_dram_bw()
{
  MEMORY_CONTROLLER& mc = champsim::g_env->dram_view();
  return mc.get_bw();
}

long long get_retired_insts(uint8_t cpu_id)
{
  assert(cpu_id < NUM_CPUS);
  O3_CPU& cpu = champsim::g_env->cpu_view().at(cpu_id);
  return cpu.num_retired;
}

#ifndef CHAMPSIM_TEST_BUILD
int main(int argc, char** argv) // NOLINT(bugprone-exception-escape)
{
  // M1 DynamoRIO link smoke test: handled before CLI parsing so it does not
  // require the (otherwise mandatory) positional trace arguments.
  for (int i = 1; i < argc; ++i) {
    if (std::string{argv[i]} == "--dr-selftest") {
      return champsim::dr::selftest();
    }
  }

  configured_environment gen_environment{};

  CLI::App app{"A microarchitecture simulator for research and education"};

  bool knob_cloudsuite{false};
  long long warmup_instructions = 0;
  long long simulation_instructions = std::numeric_limits<long long>::max();
  std::string json_file_name;
  std::vector<std::string> requested_listeners;
  std::vector<std::string> trace_names;
  std::string dynamorio_trace_dir;
  std::string dr_dump_file;

  auto set_heartbeat_callback = [&](auto) {
    for (O3_CPU& cpu : gen_environment.cpu_view()) {
      cpu.show_heartbeat = false;
    }
  };
  
  bool study_performance{false};

  app.add_flag("-c,--cloudsuite", knob_cloudsuite, "Read all traces using the cloudsuite format");
  app.add_flag("--hide-heartbeat", set_heartbeat_callback, "Hide the heartbeat output");
  app.add_flag("--study-performance", study_performance, "Study performance instead of simulating");
  auto* warmup_instr_option = app.add_option("-w,--warmup-instructions", warmup_instructions, "The number of instructions in the warmup phase");
  auto* deprec_warmup_instr_option =
      app.add_option("--warmup_instructions", warmup_instructions, "[deprecated] use --warmup-instructions instead")->excludes(warmup_instr_option);
  auto* sim_instr_option = app.add_option("-i,--simulation-instructions", simulation_instructions,
                                          "The number of instructions in the detailed phase. If not specified, run to the end of the trace.");
  auto* deprec_sim_instr_option =
      app.add_option("--simulation_instructions", simulation_instructions, "[deprecated] use --simulation-instructions instead")->excludes(sim_instr_option);

  auto* json_option =
      app.add_option("--json", json_file_name, "The name of the file to receive JSON output. If no name is specified, stdout will be used")->expected(0, 1);

  app.add_option("--listeners", requested_listeners, "A list of the listeners to be attached to the run");

  app.add_option("--dynamorio-trace-dir", dynamorio_trace_dir,
                 "Feed instructions live from a DynamoRIO thread-trace directory (the workload's trace/ subdir) instead of trace files. "
                 "Reconstructs NUM_CPUS cores from the thread traces.");
  app.add_option("--dr-dump-trace", dr_dump_file,
                 "[debug] Dump --simulation-instructions input_instr records from a 1-core DynamoRIO feed (offline parity, no time feedback) to this "
                 "file and exit. Requires --dynamorio-trace-dir and -i.");

  // Positional traces are optional: they are mutually exclusive with
  // --dynamorio-trace-dir (validated after parsing).
  app.add_option("traces", trace_names, "The paths to the traces")->expected(0, static_cast<int>(NUM_CPUS))->check(CLI::ExistingFile);

  CLI11_PARSE(app, argc, argv);

  const bool dr_mode = !dynamorio_trace_dir.empty() || !dr_dump_file.empty();

  // Raise the open-file limit before the DynamoRIO scheduler opens every thread
  // trace at init (mirrors the offline converter's setrlim()).
  if (dr_mode) {
    rlimit lim{};
    if (getrlimit(RLIMIT_NOFILE, &lim) == 0) {
      lim.rlim_cur = lim.rlim_max;
      if (setrlimit(RLIMIT_NOFILE, &lim) != 0) {
        fmt::print("WARNING: could not raise RLIMIT_NOFILE; DynamoRIO scheduler init may fail on wide traces.\n");
      }
    }
  }

  // Debug M2 parity path: dump the raw input_instr stream from a 1-core live
  // feed (no simulated clock, offline scheduler options) and exit before any
  // simulator setup. Compare against the offline .champsim.gz reference.
  if (!dr_dump_file.empty()) {
    if (dynamorio_trace_dir.empty()) {
      fmt::print("ERROR: --dr-dump-trace requires --dynamorio-trace-dir.\n");
      return 1;
    }
    if (sim_instr_option->count() == 0 && deprec_sim_instr_option->count() == 0) {
      fmt::print("ERROR: --dr-dump-trace requires -i/--simulation-instructions (the record count).\n");
      return 1;
    }
    champsim::dr::dr_config cfg;
    cfg.trace_dir = dynamorio_trace_dir;
    cfg.num_cores = 1;
    cfg.use_time_feedback = false;
    cfg.dependency_timestamps = true;
    champsim::dr::dr_scheduler sched{cfg};

    std::ofstream out{dr_dump_file, std::ios::binary};
    if (!out) {
      fmt::print("ERROR: could not open dump file {}\n", dr_dump_file);
      return 1;
    }
    long long produced = 0;
    while (produced < simulation_instructions) {
      input_instr rec{};
      bool eof = false;
      if (sched.try_next(0, 0, rec, eof)) {
        out.write(reinterpret_cast<const char*>(&rec), sizeof(rec));
        ++produced;
      } else if (eof) {
        break;
      }
    }
    out.close();
    fmt::print("[dr] dumped {} input_instr records to {}\n", produced, dr_dump_file);
    return 0;
  }

  champsim::g_env = &gen_environment;
  init_event_listeners(requested_listeners);

  const bool warmup_given = (warmup_instr_option->count() > 0) || (deprec_warmup_instr_option->count() > 0);
  const bool simulation_given = (sim_instr_option->count() > 0) || (deprec_sim_instr_option->count() > 0);

  if (deprec_warmup_instr_option->count() > 0) {
    fmt::print("WARNING: option --warmup_instructions is deprecated. Use --warmup-instructions instead.\n");
  }

  if (deprec_sim_instr_option->count() > 0) {
    fmt::print("WARNING: option --simulation_instructions is deprecated. Use --simulation-instructions instead.\n");
  }

  if (simulation_given && !warmup_given) {
    // Warmup is 20% by default
    // NOLINTNEXTLINE(cppcoreguidelines-avoid-magic-numbers,readability-magic-numbers)
    warmup_instructions = simulation_instructions / 5;
  }

  // dr_sched must outlive `traces` and champsim::main (the live sources hold a
  // pointer into it), so it lives at main() scope on the heap for a stable
  // address.
  std::unique_ptr<champsim::dr::dr_scheduler> dr_sched;
  std::vector<champsim::tracereader> traces;

  if (!dynamorio_trace_dir.empty()) {
    if (!trace_names.empty()) {
      fmt::print("ERROR: positional trace files are mutually exclusive with --dynamorio-trace-dir.\n");
      return 1;
    }

    champsim::dr::dr_config cfg;
    cfg.trace_dir = dynamorio_trace_dir;
    cfg.num_cores = static_cast<int>(NUM_CPUS);
    cfg.use_time_feedback = true;
    cfg.dependency_timestamps = true;
    dr_sched = std::make_unique<champsim::dr::dr_scheduler>(cfg);

    for (std::size_t i = 0; i < NUM_CPUS; ++i) {
      trace_names.push_back(fmt::format("dynamorio:core{}", i));
      O3_CPU& cpu = gen_environment.cpu_view().at(i);
      traces.emplace_back(champsim::dr::dr_core_source{dr_sched.get(), static_cast<int>(i), &cpu, /*use_time=*/true});
    }
  } else {
    if (trace_names.size() != NUM_CPUS) {
      fmt::print("ERROR: expected {} trace file(s) (one per CPU), got {}.\n", NUM_CPUS, trace_names.size());
      return 1;
    }
    std::transform(
        std::begin(trace_names), std::end(trace_names), std::back_inserter(traces),
        [knob_cloudsuite, repeat = simulation_given, i = uint8_t(0)](auto name) mutable { return get_tracereader(name, i++, knob_cloudsuite, repeat); });
  }

  std::vector<champsim::phase_info> phases{
      {
          champsim::phase_info{"Warmup", true, warmup_instructions, std::vector<std::size_t>(std::size(trace_names), 0), trace_names},
          //champsim::phase_info{"Warmup", false, warmup_instructions, std::vector<std::size_t>(std::size(trace_names), 0), trace_names},
       champsim::phase_info{"Simulation", false, simulation_instructions, std::vector<std::size_t>(std::size(trace_names), 0), trace_names}}};

  for (auto& p : phases) {
    std::iota(std::begin(p.trace_index), std::end(p.trace_index), 0);
  }

  fmt::print("\n*** ChampSim Multicore Out-of-Order Simulator ***\nWarmup Instructions: {}\nSimulation Instructions: {}\nNumber of CPUs: {}\nPage size: {}\nStudy performance: {}\n\n",
             phases.at(0).length, phases.at(1).length, std::size(gen_environment.cpu_view()), PAGE_SIZE, study_performance);

  if (!study_performance) {
    auto phase_stats = champsim::main(gen_environment, phases, traces);

    fmt::print("\nChampSim completed all CPUs\n\n");

    champsim::plain_printer{std::cout}.print(phase_stats);

    for (CACHE& cache : gen_environment.cache_view()) {
      cache.impl_prefetcher_final_stats();
    }

    for (CACHE& cache : gen_environment.cache_view()) {
      cache.impl_replacement_final_stats();
    }

    if (json_option->count() > 0) {
      if (json_file_name.empty()) {
        champsim::json_printer{std::cout}.print(phase_stats);
      } else {
        std::ofstream json_file{json_file_name};
        champsim::json_printer{json_file}.print(phase_stats);
      }
    }
  } else {
    if (traces.size() != 1) {
      fmt::print("\nPlease only specify one trace with study-performance!\n");
    } else {
      champsim::study_trace(phases, traces.at(0));
    }
  }

  return 0;
}
#endif
