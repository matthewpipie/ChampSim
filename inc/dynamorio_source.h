/*
 * dynamorio_source.h — online DynamoRIO instruction feed for ChampSim.
 *
 * This header exposes ONLY pure ChampSim/std types. It must never include any
 * DynamoRIO header; all DynamoRIO usage is confined to src/dynamorio_source.cc
 * (the single translation unit compiled with the DR include/link flags from
 * dr.mk). Code elsewhere guards DR-specific paths on ENABLE_DYNAMORIO.
 *
 * It also deliberately avoids including ChampSim's heavier core headers
 * (instruction.h / ooo_cpu.h) so that the DynamoRIO TU, which includes this
 * header, does not pull ChampSim macros/types next to DynamoRIO's. The per-core
 * adapter that needs ooo_model_instr lives in dynamorio_core_source.h.
 */
#ifndef DYNAMORIO_SOURCE_H
#define DYNAMORIO_SOURCE_H

#include <cstdint>
#include <memory>
#include <string>

#include "trace_instruction.h" // input_instr (pure ChampSim)

namespace champsim::dr
{
// M1 smoke test: initialize the DynamoRIO standalone decoder context, print a
// confirmation, and tear it down. Returns 0 on success, non-zero on failure.
int selftest();

// Knobs controlling how the live DynamoRIO scheduler is driven.
struct dr_config {
  std::string trace_dir;   // workload's trace/ subdir (one *.memtrace.zip per thread)
  int num_cores = 1;       // == compiled NUM_CPUS

  // M2 = false (offline-parity: next_record(record), no simulated clock).
  // M3+ = true (next_record(record, cur_time) with ps-scaled time feedback).
  bool use_time_feedback = false;

  // DEPENDENCY_TIMESTAMPS (true, offline default) vs DEPENDENCY_IGNORE (false).
  bool dependency_timestamps = true;

  // QUANTUM_TIME (true) vs QUANTUM_INSTRUCTIONS (false, DR default).
  bool quantum_time = false;
};

/*
 * dr_scheduler owns one DynamoRIO scheduler_t over a trace directory and hands
 * out fully-populated input_instr records per output core on demand. All DR
 * types are hidden behind the pimpl.
 */
class dr_scheduler
{
public:
  explicit dr_scheduler(const dr_config& cfg);
  ~dr_scheduler();
  dr_scheduler(dr_scheduler&&) noexcept;
  dr_scheduler& operator=(dr_scheduler&&) noexcept;
  dr_scheduler(const dr_scheduler&) = delete;
  dr_scheduler& operator=(const dr_scheduler&) = delete;

  /*
   * Assemble exactly one fully-populated input_instr for output `core` at the
   * given simulated time (picoseconds; ignored unless use_time_feedback).
   *   returns true  -> `out` filled with a valid instruction.
   *   returns false -> no instruction this call:
   *                      eof == true  : the core's stream is exhausted.
   *                      eof == false : a WAIT/IDLE bubble; retry next cycle.
   * Mid-instruction assembly is resumable per core across bubbles.
   */
  bool try_next(int core, uint64_t cur_time_ps, input_instr& out, bool& eof);

private:
  struct impl;
  std::unique_ptr<impl> pimpl_;
};

} // namespace champsim::dr

#endif // DYNAMORIO_SOURCE_H
