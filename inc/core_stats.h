#ifndef CORE_STATS_H
#define CORE_STATS_H

#include <cstdint>
#include <string>

#include "event_counter.h"
#include "instruction.h"

enum cpu_portion {
    RetireROB = 0,
    CompleteInflightInstruction,
    ExecuteInstruction,
    ScheduleInstruction,
    HandleMemoryReturn,
    OperateLSQ,
    DispatchInstruction,
    DecodeInstruction,
    PromoteToDecode,
    FetchInstruction,
    CheckDIB
};

using namespace std::literals::string_view_literals;
inline constexpr std::array cpu_portion_names{
    "RetireROB"sv,
    "CompleteInflightInstruction"sv,
    "ExecuteInstruction"sv,
    "ScheduleInstruction"sv,
    "HandleMemoryReturn"sv,
    "OperateLSQ"sv,
    "DispatchInstruction"sv,
    "DecodeInstruction"sv,
    "PromoteToDecode"sv,
    "FetchInstruction"sv,
    "CheckDIB"sv
};

enum cpu_buffer {
    IFETCH_B = 0,
    DISPATCH_B,
    DECODE_B,
    RO_B,
    DIB_HIT_B,
    LOAD_B,
    STORE_B
};

inline constexpr std::array cpu_buffer_names{
    "IFETCH_B"sv,
    "DISPATCH_B"sv,
    "DECODE_B"sv,
    "RO_B"sv,
    "DIB_HIT_B"sv,
    "LOAD_B"sv,
    "STORE_B"sv
};



struct cpu_stats {
  std::string name;
  long long begin_instrs = 0;
  long long begin_cycles = 0;
  long long end_instrs = 0;
  long long end_cycles = 0;
  uint64_t total_rob_occupancy_at_branch_mispredict = 0;

  // Top-down (Yasin level 1) dispatch-slot accounting. Each cycle, every
  // dispatch slot (DISPATCH_WIDTH per cycle) is charged to exactly one bucket,
  // so the four counters sum to cycles() * DISPATCH_WIDTH.
  uint64_t td_retiring_slots = 0;       // a uop was dispatched into the ROB
  uint64_t td_frontend_bound_slots = 0; // backend had room, frontend had nothing ready
  uint64_t td_backend_bound_slots = 0;  // ROB / LQ / SQ blocked dispatch (sum of the three sub-counters below)
  uint64_t td_bad_spec_slots = 0;       // dispatch idle while in mispredict pause

  // Backend-bound breakdown. Each backend-bound slot is attributed to the
  // first applicable cause in priority order ROB -> LQ -> SQ (matching the
  // order the conditions are checked in the dispatch loop). The three
  // sub-counters partition td_backend_bound_slots exactly.
  uint64_t td_backend_rob_full_slots = 0;  // ROB had no free entry
  uint64_t td_backend_lq_short_slots = 0;  // ROB had room but LQ lacked entries for the head's loads
  uint64_t td_backend_sq_short_slots = 0;  // ROB & LQ had room but SQ lacked entries for the head's stores

  std::unordered_map<cpu_portion, std::map<uint64_t, uint64_t>> cpu_portion_distributions = {};
  std::unordered_map<cpu_buffer, std::map<size_t, uint64_t>> cpu_buffer_distributions = {};

  champsim::stats::event_counter<branch_type> total_branch_types = {};
  champsim::stats::event_counter<branch_type> branch_type_misses = {}; // btb or bp missed
  champsim::stats::event_counter<branch_type> bp_misses = {};
  champsim::stats::event_counter<branch_type> btb_misses = {};
  champsim::stats::event_counter<branch_type> both_misses = {};

  [[nodiscard]] auto instrs() const { return end_instrs - begin_instrs; }
  [[nodiscard]] auto cycles() const { return end_cycles - begin_cycles; }
};

cpu_stats operator-(cpu_stats lhs, cpu_stats rhs);

#endif
