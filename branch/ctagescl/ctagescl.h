#ifndef BRANCH_CTAGESCL_H
#define BRANCH_CTAGESCL_H

#include "modules.h"
#include "msl/fwcounter.h"

#include "tagescl/tagescl.hpp"


struct ChampsimTageScl {
  using Impl = tagescl::Tage_SC_L<tagescl::CONFIG_64KB>;
  enum State {
    NONE,
    PREDICTED,
  };

  ChampsimTageScl(std::size_t max_inflight_branches)
      : impl(max_inflight_branches), id(0), state(NONE) {}

  Impl impl;
  std::uint64_t last_ip;
  std::uint32_t id;
  State state;
};


class ctagescl : champsim::modules::branch_predictor {
public:
  std::vector<ChampsimTageScl> tage{};

  using branch_predictor::branch_predictor;

  bool predict_branch(champsim::address ip);
  void last_branch_result(champsim::address ip, champsim::address branch_target, bool taken, uint8_t branch_type);
  void initialize_branch_predictor();
};

#endif
