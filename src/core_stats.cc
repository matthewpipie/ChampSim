#include "core_stats.h"

cpu_stats operator-(cpu_stats lhs, cpu_stats rhs)
{
  lhs.begin_instrs -= rhs.begin_instrs;
  lhs.begin_cycles -= rhs.begin_cycles;
  lhs.end_instrs -= rhs.end_instrs;
  lhs.end_cycles -= rhs.end_cycles;
  lhs.total_rob_occupancy_at_branch_mispredict -= rhs.total_rob_occupancy_at_branch_mispredict;

  lhs.td_retiring_slots -= rhs.td_retiring_slots;
  lhs.td_frontend_bound_slots -= rhs.td_frontend_bound_slots;
  lhs.td_backend_bound_slots -= rhs.td_backend_bound_slots;
  lhs.td_bad_spec_slots -= rhs.td_bad_spec_slots;
  lhs.td_backend_rob_full_slots -= rhs.td_backend_rob_full_slots;
  lhs.td_backend_lq_short_slots -= rhs.td_backend_lq_short_slots;
  lhs.td_backend_sq_short_slots -= rhs.td_backend_sq_short_slots;

  lhs.total_branch_types -= rhs.total_branch_types;
  lhs.branch_type_misses -= rhs.branch_type_misses;
  lhs.btb_misses -= rhs.btb_misses;
  lhs.bp_misses -= rhs.bp_misses;
  lhs.both_misses -= rhs.both_misses;

  return lhs;
}
