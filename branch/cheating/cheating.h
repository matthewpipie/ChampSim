#ifndef BRANCH_CHEATING_H
#define BRANCH_CHEATING_H

#include "modules.h"

struct cheating : champsim::modules::branch_predictor {

  using branch_predictor::branch_predictor;

  bool predict_branch(champsim::address ip, champsim::address predicted_target, bool always_taken, uint8_t branch_type, bool cheating_branch_taken);
  void last_branch_result(champsim::address ip, champsim::address branch_target, bool taken, uint8_t branch_type) {}
};

#endif
