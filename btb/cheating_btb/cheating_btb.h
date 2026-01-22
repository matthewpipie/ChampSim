#ifndef BTB_CHEATING_BTB_H
#define BTB_CHEATING_BTB_H

#include "address.h"
#include "modules.h"

class cheating_btb : champsim::modules::btb
{

public:
  using btb::btb;
  cheating_btb() : btb(nullptr) {}

  // void initialize_btb();
  std::pair<champsim::address, bool> btb_prediction(champsim::address ip, uint8_t branch_type, champsim::address cheating_branch_target);
  void update_btb(champsim::address ip, champsim::address branch_target, bool taken, uint8_t branch_type) {}
};

#endif
