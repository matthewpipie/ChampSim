/*
 * dynamorio_core_source.cc — non-DynamoRIO glue for the per-core live source.
 *
 * This TU is intentionally free of DynamoRIO headers; it may include ChampSim's
 * heavy core headers (ooo_cpu.h) which the DR TU must avoid. It provides the
 * one function dr_core_source needs from the core model: the current simulated
 * time in picoseconds.
 */
#include "dynamorio_core_source.h"

#include "ooo_cpu.h" // O3_CPU (full type)

namespace champsim::dr
{
uint64_t cpu_current_time_ps(const O3_CPU* cpu)
{
  // clock::duration is picoseconds (see inc/chrono.h), so the raw count is ps.
  return static_cast<uint64_t>(cpu->current_time.time_since_epoch().count());
}
} // namespace champsim::dr
