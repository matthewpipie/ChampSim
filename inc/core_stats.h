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
