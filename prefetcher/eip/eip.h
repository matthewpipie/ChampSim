#ifndef PREFETCHER_EIP_H
#define PREFETCHER_EIP_H

#include <cstdint>

#include "address.h"
#include "modules.h"

struct eip : public champsim::modules::prefetcher {
  using prefetcher::prefetcher;
  //uint32_t prefetcher_cache_operate(champsim::address addr, champsim::address ip, uint8_t cache_hit, bool useful_prefetch, access_type type,
                                    //uint32_t metadata_in);
  uint32_t prefetcher_cache_operate(champsim::address __addr, champsim::address __ip, uint8_t cache_hit, bool prefetch_hit, access_type type, uint32_t metadata_in);
  //uint32_t prefetcher_cache_fill(champsim::address addr, long set, long way, uint8_t prefetch, champsim::address evicted_addr, uint32_t metadata_in);
  uint32_t prefetcher_cache_fill(uint64_t v_addr, long set, long way, uint8_t prefetch, uint64_t evicted_v_addr, uint32_t metadata_in);

  void prefetcher_initialize();
  //void prefetcher_branch_operate(champsim::address ip, uint8_t branch_type, champsim::address branch_target) {}
  void prefetcher_branch_operate(uint64_t ip, uint8_t branch_type, uint64_t branch_target);
  void prefetcher_cycle_operate();
  void prefetcher_final_stats();

// TODO: improve
  int cpu = 0;
};

#endif
