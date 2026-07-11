/*
 * dynamorio_source.cc — the ONLY translation unit that includes DynamoRIO.
 *
 * Built with the DR include/link flags from dr.mk (opt-in via DYNAMORIO=1).
 * When DR is not enabled, ENABLE_DYNAMORIO is undefined and this file compiles
 * to a stub so the build still works without DynamoRIO present.
 *
 * The instruction-translation helpers (getBranchType / update_inst_registers /
 * assignBranchRegisters / update_branch_info and the memref-gathering state
 * machine) are ported from the offline converter
 *   private-google-workload-traces-v2-to-champsim/src/main.cpp
 * preserved as closely as possible so the online feed reproduces the offline
 * input_instr stream byte-for-byte (M2 parity). See that file for the extensive
 * commentary on the SP=6 / FLAGS=25 / IP=26 magic-register contract and the
 * REG_DEPENDENCY_OFFSET (+100) applied to every non-branch register.
 */
#include "dynamorio_source.h"

#include <cstdio>

#ifdef ENABLE_DYNAMORIO

// DynamoRIO standalone decoder + scheduler API.
#include "dr_api.h"
#include "drmemtrace/scheduler.h"

#include <array>
#include <cstring>
#include <limits>
#include <random>
#include <stdexcept>
#include <unordered_map>
#include <vector>

using namespace dynamorio::drmemtrace;

namespace champsim::dr
{
namespace
{
// ---- safe_num_cast (ported verbatim from offline safe_num_cast.hpp) ----------
template <typename ToType, typename FromType>
constexpr ToType safe_num_cast(FromType value)
{
  static_assert(std::is_integral_v<ToType> && std::is_integral_v<FromType>, "safe_num_cast requires integral types");
  using ToTypeLimits = std::numeric_limits<ToType>;
  if constexpr (std::is_signed_v<FromType> && std::is_signed_v<ToType>) {
    if (value < ToTypeLimits::min() || value > ToTypeLimits::max())
      throw std::runtime_error("safe_num_cast: signed value out of range");
  } else if constexpr (!std::is_signed_v<FromType> && std::is_signed_v<ToType>) {
    if (value > static_cast<std::make_unsigned_t<ToType>>(ToTypeLimits::max()))
      throw std::runtime_error("safe_num_cast: unsigned value too large for signed target");
  } else if constexpr (std::is_signed_v<FromType> && !std::is_signed_v<ToType>) {
    if (value < 0 || static_cast<std::make_unsigned_t<FromType>>(value) > ToTypeLimits::max())
      throw std::runtime_error("safe_num_cast: negative or out-of-range value for unsigned target");
  } else {
    if (value > ToTypeLimits::max())
      throw std::runtime_error("safe_num_cast: unsigned value out of range");
  }
  return static_cast<ToType>(value);
}

// ---- threadsafe_rand (ported from offline threadsafe_rand.hpp) ---------------
// Only exercised for indirect/conditional branches that carry no source
// register in the trace; mirrors the offline path so parity holds whenever that
// path is not hit (as in the arizona reference).
template <typename T>
T threadsafe_rand(const T& min, const T& max)
{
  static thread_local std::mt19937* generator = nullptr;
  if (generator == nullptr) {
    std::random_device rd;
    generator = new std::mt19937(rd());
  }
  std::uniform_int_distribution<T> distribution(min, max);
  return distribution(*generator);
}

#define TESTANY(mask, var) (((mask) & (var)) != 0)

constexpr ssize_t REG_DEPENDENCY_OFFSET = 100;
static_assert(REG_DEPENDENCY_OFFSET > champsim::REG_STACK_POINTER, "offset must exceed SP magic id");
static_assert(REG_DEPENDENCY_OFFSET > champsim::REG_FLAGS, "offset must exceed FLAGS magic id");
static_assert(REG_DEPENDENCY_OFFSET > champsim::REG_INSTRUCTION_POINTER, "offset must exceed IP magic id");

constexpr unsigned char RAND_REG_RANGE_MIN = REG_DEPENDENCY_OFFSET;
constexpr unsigned char RAND_REG_RANGE_MAX = RAND_REG_RANGE_MIN + 15;

constexpr unsigned REG_SRC_NUM_INSTR = NUM_INSTR_SOURCES;
constexpr unsigned REG_DST_NUM_INSTR = NUM_INSTR_DESTINATIONS;
constexpr unsigned MEM_SRC_NUM_INSTR = NUM_INSTR_SOURCES;
constexpr unsigned MEM_DST_NUM_INSTR = NUM_INSTR_DESTINATIONS;

// ---- register-assignment helpers (offset +100 for non-branch regs) -----------
bool addSrcRegister(input_instr& ci, unsigned& srcCount, ushort reg)
{
  if (srcCount >= REG_SRC_NUM_INSTR)
    return false;
  ci.source_registers[srcCount++] = safe_num_cast<unsigned char>(reg + REG_DEPENDENCY_OFFSET);
  return true;
}
bool addDstRegister(input_instr& ci, unsigned& dstCount, ushort reg)
{
  if (dstCount >= REG_DST_NUM_INSTR)
    return false;
  ci.destination_registers[dstCount++] = safe_num_cast<unsigned char>(reg + REG_DEPENDENCY_OFFSET);
  return true;
}
// Branch register helpers: no offset (they carry the magic SP/IP/FLAGS ids).
bool addSrcRegisterForBranch(input_instr& ci, unsigned& srcCount, ushort reg)
{
  if (srcCount >= REG_SRC_NUM_INSTR)
    return false;
  ci.source_registers[srcCount++] = safe_num_cast<unsigned char>(reg);
  return true;
}
bool addDstRegisterForBranch(input_instr& ci, unsigned& dstCount, ushort reg)
{
  if (dstCount >= REG_DST_NUM_INSTR)
    return false;
  ci.destination_registers[dstCount++] = safe_num_cast<unsigned char>(reg);
  return true;
}
bool addSrcRegistersForBranch(input_instr& ci, unsigned& srcCount, const std::vector<ushort>& regs)
{
  for (ushort reg : regs)
    if (!addSrcRegisterForBranch(ci, srcCount, reg))
      return false;
  return true;
}
bool addDstRegistersForBranch(input_instr& ci, unsigned& dstCount, const std::vector<ushort>& regs)
{
  for (ushort reg : regs)
    if (!addDstRegisterForBranch(ci, dstCount, reg))
      return false;
  return true;
}

// Consolidated branch-specific register assignments (specialized, no offset).
bool assignBranchRegisters(input_instr& ci, unsigned& srcCount, unsigned& dstCount, trace_type_t branchType)
{
  switch (branchType) {
  case TRACE_TYPE_INSTR_DIRECT_JUMP:
    break;
  case TRACE_TYPE_INSTR_INDIRECT_JUMP:
    if (srcCount == 0) {
      if (!addSrcRegisterForBranch(ci, srcCount, threadsafe_rand<ushort>(RAND_REG_RANGE_MIN, RAND_REG_RANGE_MAX)))
        return false;
    }
    break;
  case TRACE_TYPE_INSTR_CONDITIONAL_JUMP:
  case TRACE_TYPE_INSTR_TAKEN_JUMP:
  case TRACE_TYPE_INSTR_UNTAKEN_JUMP:
    if (srcCount == 0) {
      if (threadsafe_rand<int>(0, 1) == 0) {
        if (!addSrcRegisterForBranch(ci, srcCount, threadsafe_rand<ushort>(RAND_REG_RANGE_MIN, RAND_REG_RANGE_MAX)))
          return false;
      } else {
        if (!addSrcRegisterForBranch(ci, srcCount, champsim::REG_FLAGS))
          return false;
      }
    }
    if (!addSrcRegisterForBranch(ci, srcCount, champsim::REG_INSTRUCTION_POINTER))
      return false;
    break;
  case TRACE_TYPE_INSTR_DIRECT_CALL:
    srcCount = 0;
    if (!addSrcRegistersForBranch(ci, srcCount, {champsim::REG_STACK_POINTER, champsim::REG_INSTRUCTION_POINTER}))
      return false;
    dstCount = 0;
    if (!addDstRegistersForBranch(ci, dstCount, {champsim::REG_STACK_POINTER, champsim::REG_INSTRUCTION_POINTER}))
      return false;
    for (unsigned i = srcCount; i < REG_SRC_NUM_INSTR; i++)
      if (!addSrcRegisterForBranch(ci, srcCount, 0))
        return false;
    for (unsigned i = dstCount; i < REG_DST_NUM_INSTR; i++)
      if (!addDstRegisterForBranch(ci, dstCount, 0))
        return false;
    break;
  case TRACE_TYPE_INSTR_INDIRECT_CALL:
    if (srcCount == 0) {
      if (!addSrcRegisterForBranch(ci, srcCount, threadsafe_rand<ushort>(RAND_REG_RANGE_MIN, RAND_REG_RANGE_MAX)))
        return false;
    }
    if (!addSrcRegistersForBranch(ci, srcCount, {champsim::REG_STACK_POINTER, champsim::REG_INSTRUCTION_POINTER}))
      return false;
    if (!addDstRegisterForBranch(ci, dstCount, champsim::REG_STACK_POINTER))
      return false;
    break;
  case TRACE_TYPE_INSTR_RETURN:
    if (!addSrcRegisterForBranch(ci, srcCount, champsim::REG_STACK_POINTER))
      return false;
    if (!addDstRegisterForBranch(ci, dstCount, champsim::REG_STACK_POINTER))
      return false;
    break;
  default:
    break;
  }
  return true;
}

// Populate ci's src/dst registers from a decoded DR instruction.
void update_inst_registers(memref_t record, instr_t& dr_instr, input_instr& ci)
{
  unsigned srcCount = 0;
  unsigned dstCount = 0;
  uint used_flag = instr_get_arith_flags(&dr_instr, DR_QUERY_DEFAULT);

  for (uint i = 0; i < safe_num_cast<uint>(instr_num_srcs(&dr_instr)); i++) {
    opnd_t opnd = instr_get_src(&dr_instr, i);
    for (int opnum = 0; opnum < opnd_num_regs_used(opnd); opnum++) {
      reg_id_t reg = opnd_get_reg_used(opnd, opnum);
      if (!addSrcRegister(ci, srcCount, safe_num_cast<ushort>(reg)))
        return;
    }
  }
  for (uint i = 0; i < safe_num_cast<uint>(instr_num_dsts(&dr_instr)); i++) {
    opnd_t opnd = instr_get_dst(&dr_instr, i);
    for (int opnum = 0; opnum < opnd_num_regs_used(opnd); opnum++) {
      reg_id_t reg = opnd_get_reg_used(opnd, opnum);
      if (!addDstRegister(ci, dstCount, safe_num_cast<ushort>(reg)))
        return;
    }
  }

  if (TESTANY(EFLAGS_WRITE_ARITH, used_flag)) {
    if (!addDstRegisterForBranch(ci, dstCount, champsim::REG_FLAGS))
      return;
  }
  if (TESTANY(EFLAGS_READ_ARITH, used_flag)) {
    if (!addSrcRegisterForBranch(ci, srcCount, champsim::REG_FLAGS))
      return;
  }

  if (record.instr.type == TRACE_TYPE_INSTR) {
    return;
  } else {
    dstCount = 0;
    if (!addDstRegisterForBranch(ci, dstCount, champsim::REG_INSTRUCTION_POINTER))
      return;
  }

  if (!assignBranchRegisters(ci, srcCount, dstCount, record.instr.type))
    return;
}

// Set is_branch / branch_taken from the record type.
void update_branch_info(memref_t record, input_instr& ci)
{
  switch (record.instr.type) {
  case TRACE_TYPE_INSTR:
    ci.is_branch = false;
    ci.branch_taken = false;
    break;
  case TRACE_TYPE_INSTR_DIRECT_JUMP:
  case TRACE_TYPE_INSTR_INDIRECT_JUMP:
  case TRACE_TYPE_INSTR_DIRECT_CALL:
  case TRACE_TYPE_INSTR_INDIRECT_CALL:
  case TRACE_TYPE_INSTR_RETURN:
  case TRACE_TYPE_INSTR_TAKEN_JUMP:
    ci.is_branch = true;
    ci.branch_taken = true;
    break;
  case TRACE_TYPE_INSTR_UNTAKEN_JUMP:
    ci.is_branch = true;
    ci.branch_taken = false;
    break;
  case TRACE_TYPE_INSTR_CONDITIONAL_JUMP:
    ci.is_branch = true;
    ci.branch_taken = false;
    break;
  default:
    ci.is_branch = false;
    ci.branch_taken = false;
    break;
  }
}

// 3 GiB per-core decode-cache cap, matching the offline converter.
constexpr std::size_t CACHE_MEM_LIMIT_PERTHREAD = 3lu * 1024lu * 1024lu * 1024lu;

} // namespace

// ---- dr_scheduler::impl ------------------------------------------------------
struct dr_scheduler::impl {
  dr_config cfg;
  scheduler_t scheduler;
  std::vector<scheduler_t::stream_t*> streams;
  void* dcontext = nullptr;

  // Per-output resumable assembly state.
  enum class asm_state { NEED_INSTR, GATHER_MEM };
  struct core_state {
    asm_state state = asm_state::NEED_INSTR;
    input_instr cur{};
    memref_t start_record{};
    unsigned src_mem = 0;
    unsigned dst_mem = 0;
    bool have_lookahead = false;
    memref_t lookahead{};
    std::unordered_map<std::size_t, input_instr> cs_pc_instr_map;
  };
  std::vector<core_state> cores;

  explicit impl(const dr_config& c) : cfg(c)
  {
    std::vector<scheduler_t::input_workload_t> sched_inputs;
    sched_inputs.emplace_back(cfg.trace_dir);

    scheduler_t::scheduler_options_t sched_ops(scheduler_t::MAP_TO_ANY_OUTPUT,
                                               cfg.dependency_timestamps ? scheduler_t::DEPENDENCY_TIMESTAMPS : scheduler_t::DEPENDENCY_IGNORE,
                                               scheduler_t::SCHEDULER_DEFAULTS);
    if (cfg.use_time_feedback) {
      // 1 time-unit == 1 picosecond, so cpu->current_time (already ps) feeds in
      // directly. quantum_duration_us then drives preemption off the real clock.
      sched_ops.time_units_per_us = 1e6;
      sched_ops.single_lockstep_output = true;    // one thread round-robins all N outputs
      sched_ops.honor_infinite_timeouts = false;  // bounded block clearance
      if (cfg.quantum_time) {
        sched_ops.quantum_unit = scheduler_t::QUANTUM_TIME;
      }
    }

    scheduler_t::scheduler_status_t status = scheduler.init(sched_inputs, cfg.num_cores, std::move(sched_ops));
    if (status != scheduler_t::STATUS_SUCCESS) {
      std::fprintf(stderr, "[dr] scheduler.init failed: status=%d error=%s\n", static_cast<int>(status), scheduler.get_error_string().c_str());
      throw std::runtime_error("dr_scheduler: scheduler.init failed");
    }

    dcontext = dr_standalone_init();

    auto filetype = scheduler.get_stream(0)->get_filetype();
    if (TESTANY(OFFLINE_FILE_TYPE_ARCH_REGDEPS, filetype)) {
      dr_set_isa_mode(dcontext, DR_ISA_REGDEPS, nullptr);
    }

    streams.reserve(safe_num_cast<std::size_t>(cfg.num_cores));
    for (int i = 0; i < cfg.num_cores; ++i) {
      streams.push_back(scheduler.get_stream(i));
    }
    cores.resize(safe_num_cast<std::size_t>(cfg.num_cores));
  }

  ~impl()
  {
    if (dcontext != nullptr) {
      dr_standalone_exit();
    }
  }

  scheduler_t::stream_status_t read(int core, memref_t& record, uint64_t cur_time)
  {
    return cfg.use_time_feedback ? streams[safe_num_cast<std::size_t>(core)]->next_record(record, cur_time)
                                 : streams[safe_num_cast<std::size_t>(core)]->next_record(record);
  }

  // Translate one instruction record into `ci` (using the per-core CS decode
  // cache). Mirrors offline simulate_core's decode/reuse logic.
  void translate(core_state& cs, memref_t record, input_instr& ci)
  {
    std::size_t pc = record.instr.addr;

    bool cache_hit = false;
    if (!record.instr.encoding_is_new) {
      if (cs.cs_pc_instr_map.size() * sizeof(input_instr) >= CACHE_MEM_LIMIT_PERTHREAD) {
        cs.cs_pc_instr_map.clear();
      }
      auto it = cs.cs_pc_instr_map.find(pc);
      if (it != cs.cs_pc_instr_map.end()) {
        cache_hit = true;
        ci = it->second;
      }
    }

    if (!cache_hit) {
      instr_t dr_instr;
      instr_init(dcontext, &dr_instr);
      const app_pc decode_pc = reinterpret_cast<app_pc>(pc);
      decode_from_copy(dcontext, record.instr.encoding, decode_pc, &dr_instr);

      std::memset(&ci, 0, sizeof(ci));
      update_inst_registers(record, dr_instr, ci);
      ci.ip = record.instr.addr;

      instr_free(dcontext, &dr_instr);
    } else {
      // Reuse cached register decode; this instance may have different memory
      // operands and branch-taken info, so clear the memory fields.
      std::memset(&ci.destination_memory, 0, sizeof(ci.destination_memory));
      std::memset(&ci.source_memory, 0, sizeof(ci.source_memory));
    }

    update_branch_info(record, ci);
  }

  bool try_next(int core, uint64_t cur_time, input_instr& out, bool& eof)
  {
    eof = false;
    core_state& cs = cores[safe_num_cast<std::size_t>(core)];

    while (true) {
      if (cs.state == asm_state::NEED_INSTR) {
        memref_t record;
        scheduler_t::stream_status_t status;
        if (cs.have_lookahead) {
          record = cs.lookahead;
          cs.have_lookahead = false;
          status = scheduler_t::STATUS_OK;
        } else {
          status = read(core, record, cur_time);
        }

        if (status == scheduler_t::STATUS_EOF) {
          eof = true;
          return false;
        }
        if (status == scheduler_t::STATUS_WAIT || status == scheduler_t::STATUS_IDLE) {
          if (cfg.use_time_feedback) {
            return false; // bubble; retry next cycle with an advanced clock
          }
          continue; // offline-parity: re-poll immediately
        }
        // STATUS_OK
        if (!type_is_instr(record.instr.type)) {
          continue; // skip markers / thread-exit / etc.
        }

        cs.start_record = record;
        translate(cs, record, cs.cur);
        cs.src_mem = 0;
        cs.dst_mem = 0;
        cs.state = asm_state::GATHER_MEM;
        continue;
      }

      // GATHER_MEM: collect this instruction's READ/WRITE records.
      memref_t rec;
      scheduler_t::stream_status_t status = read(core, rec, cur_time);

      if (status == scheduler_t::STATUS_EOF) {
        finalize(cs);
        out = cs.cur;
        cs.state = asm_state::NEED_INSTR;
        return true;
      }
      if (status == scheduler_t::STATUS_WAIT || status == scheduler_t::STATUS_IDLE) {
        if (cfg.use_time_feedback) {
          return false; // resumable: state/cur preserved for next call
        }
        continue;
      }
      // STATUS_OK
      if (rec.instr.type == TRACE_TYPE_READ) {
        if (cs.src_mem < MEM_SRC_NUM_INSTR) {
          cs.cur.source_memory[cs.src_mem++] = rec.instr.addr;
        }
        continue;
      }
      if (rec.instr.type == TRACE_TYPE_WRITE) {
        if (cs.dst_mem < MEM_DST_NUM_INSTR) {
          cs.cur.destination_memory[cs.dst_mem++] = rec.instr.addr;
        }
        continue;
      }

      // A non-memory record ends this instruction; carry it to the next call.
      cs.lookahead = rec;
      cs.have_lookahead = true;
      finalize(cs);
      out = cs.cur;
      cs.state = asm_state::NEED_INSTR;
      return true;
    }
  }

  void finalize(core_state& cs)
  {
    // Store the completed instruction into the decode cache on a miss, matching
    // offline (the cached memory fields are overwritten on a later hit).
    if (!cs.start_record.instr.encoding_is_new) {
      cs.cs_pc_instr_map[cs.start_record.instr.addr] = cs.cur;
    }
  }
};

// ---- dr_scheduler forwarding -------------------------------------------------
dr_scheduler::dr_scheduler(const dr_config& cfg) : pimpl_(std::make_unique<impl>(cfg)) {}
dr_scheduler::~dr_scheduler() = default;
dr_scheduler::dr_scheduler(dr_scheduler&&) noexcept = default;
dr_scheduler& dr_scheduler::operator=(dr_scheduler&&) noexcept = default;

bool dr_scheduler::try_next(int core, uint64_t cur_time_ps, input_instr& out, bool& eof) { return pimpl_->try_next(core, cur_time_ps, out, eof); }

int selftest()
{
  void* dcontext = dr_standalone_init();
  if (dcontext == nullptr) {
    std::fprintf(stderr, "[dr] dr_standalone_init() returned null\n");
    return 1;
  }
  std::printf("[dr] DynamoRIO standalone decoder initialized (dcontext=%p, _USES_DR_VERSION_=%d)\n", dcontext, _USES_DR_VERSION_);
  dr_standalone_exit();
  return 0;
}

} // namespace champsim::dr

#else // !ENABLE_DYNAMORIO

namespace champsim::dr
{
int selftest()
{
  std::fprintf(stderr, "[dr] ChampSim was built without DynamoRIO support (rebuild with DYNAMORIO=1).\n");
  return 2;
}

// Out-of-line stubs so a non-DR build still links references to dr_scheduler
// (e.g. the guarded paths in main.cc). These abort if actually reached.
struct dr_scheduler::impl {
};
dr_scheduler::dr_scheduler(const dr_config&)
{
  std::fprintf(stderr, "[dr] built without DynamoRIO support (rebuild with DYNAMORIO=1).\n");
  std::abort();
}
dr_scheduler::~dr_scheduler() = default;
dr_scheduler::dr_scheduler(dr_scheduler&&) noexcept = default;
dr_scheduler& dr_scheduler::operator=(dr_scheduler&&) noexcept = default;
bool dr_scheduler::try_next(int, uint64_t, input_instr&, bool&) { return false; }

} // namespace champsim::dr

#endif // ENABLE_DYNAMORIO
