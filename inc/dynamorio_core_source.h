/*
 * dynamorio_core_source.h — per-core adapter that makes a dr_scheduler output
 * satisfy ChampSim's `tracereader` concept (ooo_model_instr operator()() + eof)
 * plus the optionally-detected has_next() used to signal front-end bubbles.
 *
 * This header pulls in ChampSim core types (ooo_model_instr) and therefore must
 * NOT be included by the DynamoRIO translation unit. Only main.cc (which builds
 * the live sources) includes it.
 */
#ifndef DYNAMORIO_CORE_SOURCE_H
#define DYNAMORIO_CORE_SOURCE_H

#include <optional>

#include "dynamorio_source.h"
#include "instruction.h"  // ooo_model_instr
#include "tracereader.h"  // champsim::apply_branch_target

class O3_CPU; // full type only needed in the glue TU

namespace champsim::dr
{
// Reads a core's current simulated time in picoseconds. Defined in
// src/dynamorio_core_source.cc (a non-DR TU that may include ooo_cpu.h).
uint64_t cpu_current_time_ps(const O3_CPU* cpu);

/*
 * dr_core_source adapts one output of a shared dr_scheduler to the tracereader
 * concept. It keeps a one-instruction lookahead (pending_) so it can fill each
 * branch's branch_target with the following instruction's IP, mirroring
 * bulk_tracereader::set_branch_targets one instruction at a time.
 */
class dr_core_source
{
  dr_scheduler* sched_;
  int core_;
  const O3_CPU* cpu_;
  bool use_time_;

  bool eof_ = false;                       // underlying stream exhausted AND drained
  std::optional<ooo_model_instr> pending_; // produced, awaiting its branch target
  std::optional<ooo_model_instr> ready_;   // resolved, awaiting operator()()

  // Pull one raw instruction from the scheduler (honoring cur_time when
  // use_time_). Returns nullopt on a bubble or once the stream is exhausted;
  // sets stream_eof_ when the scheduler reports EOF.
  bool stream_eof_ = false;
  std::optional<ooo_model_instr> pull_raw()
  {
    input_instr raw{};
    bool eof = false;
    const uint64_t cur_time = use_time_ ? cpu_current_time_ps(cpu_) : 0;
    if (sched_->try_next(core_, cur_time, raw, eof)) {
      return ooo_model_instr{static_cast<uint8_t>(core_), raw};
    }
    if (eof) {
      stream_eof_ = true;
    }
    return std::nullopt;
  }

public:
  dr_core_source(dr_scheduler* sched, int core, const O3_CPU* cpu, bool use_time)
      : sched_(sched), core_(core), cpu_(cpu), use_time_(use_time)
  {
  }

  // Detected by tracereader: returns false when no instruction is ready this
  // cycle (WAIT/IDLE bubble). Does the actual scheduler work and caches the
  // resolved instruction in ready_ for operator()().
  bool has_next()
  {
    if (ready_.has_value()) {
      return true;
    }
    if (eof_) {
      return false;
    }

    // Bootstrap / advance the one-instruction lookahead. We need `pending_`
    // held back so its branch_target can be resolved by the next instruction.
    while (true) {
      auto raw = pull_raw();
      if (!raw.has_value()) {
        if (stream_eof_) {
          // Flush the final held instruction (its branch_target stays empty,
          // matching set_branch_targets' treatment of the last element).
          if (pending_.has_value()) {
            ready_ = std::move(pending_);
            pending_.reset();
            return true;
          }
          eof_ = true;
          return false;
        }
        return false; // bubble: retry next cycle
      }

      if (!pending_.has_value()) {
        pending_ = std::move(raw);
        continue; // need one more to resolve pending_'s target
      }

      ready_ = champsim::apply_branch_target(std::move(*pending_), *raw);
      pending_ = std::move(raw);
      return true;
    }
  }

  ooo_model_instr operator()()
  {
    if (!ready_.has_value()) {
      // Contract: operator() is only called after has_next() returned true.
      (void)has_next();
    }
    ooo_model_instr retval = std::move(*ready_);
    ready_.reset();
    return retval;
  }

  [[nodiscard]] bool eof() const { return eof_; }
};

} // namespace champsim::dr

#endif // DYNAMORIO_CORE_SOURCE_H
