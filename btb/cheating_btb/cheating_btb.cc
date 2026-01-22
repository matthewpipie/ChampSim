#include "cheating_btb.h"

#include "instruction.h"

std::pair<champsim::address, bool> cheating_btb::btb_prediction(champsim::address ip, uint8_t branch_type, champsim::address cheating_branch_target) {
    return {cheating_branch_target, branch_type != BRANCH_CONDITIONAL};
}
