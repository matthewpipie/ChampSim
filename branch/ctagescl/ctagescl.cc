#include "ctagescl.h"
#include <cassert>
#include <cstdint>

#include <iostream>

#include "instruction.h"



void ctagescl::initialize_branch_predictor() {
  tage.emplace_back(1);
}

bool ctagescl::predict_branch(champsim::address __ip) {
  std::uint64_t ip = __ip.to<std::uint64_t>();
  ChampsimTageScl& predictor = tage[0];
  if (predictor.state == ChampsimTageScl::PREDICTED) {
    // If we get here is because last_branch_result was not called.
    // Hence, the last ip was not branch and we should retire it
    // without doing any operation such as updating the history.
    // predictor.impl.retire_non_branch_ip(predictor.id);
    tagescl::Branch_Type type;
    type.is_conditional = false;
    type.is_indirect = false;
    predictor.impl.commit_state_at_retire(predictor.id, predictor.last_ip, type,
                                          0, 0);
  }
  predictor.id = predictor.impl.get_new_branch_id();
  bool prediction = predictor.impl.get_prediction(predictor.id, ip);
  predictor.last_ip = ip;
  predictor.state = ChampsimTageScl::PREDICTED;
  return prediction;
}

void ctagescl::last_branch_result(champsim::address __ip, champsim::address __target,
                                bool __taken, std::uint8_t branch_type) {
  std::uint64_t ip = __ip.to<std::uint64_t>();
  std::uint64_t target = __target.to<std::uint64_t>();
  std::uint8_t taken = __taken;
  ChampsimTageScl& predictor = tage[0];
  assert(predictor.state == ChampsimTageScl::PREDICTED);
  assert(predictor.last_ip == ip);
  tagescl::Branch_Type type;
  type.is_conditional =
      branch_type == BRANCH_CONDITIONAL or branch_type == BRANCH_OTHER;
  type.is_indirect =
      branch_type == BRANCH_INDIRECT or branch_type == BRANCH_INDIRECT_CALL or
      branch_type == BRANCH_RETURN or branch_type == BRANCH_OTHER;
  predictor.impl.update_speculative_state(predictor.id, ip, type, taken,
                                          target);
  if (type.is_conditional) {
    predictor.impl.commit_state(predictor.id, ip, type, taken);
  }
  predictor.impl.commit_state_at_retire(predictor.id, ip, type, taken, target);
  predictor.state = ChampsimTageScl::NONE;
}
