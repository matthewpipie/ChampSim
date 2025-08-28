#include "stride_v1.h"
#include <vector>
#include <iostream>

uint32_t stride_v1::prefetcher_cache_operate(champsim::address addr, champsim::address ip, uint8_t cache_hit, bool useful_prefetch, access_type type,
                                             uint32_t metadata_in)
{
  //champsim::block_number pf_addr{addr};
  //prefetch_line(champsim::address{pf_addr + 1}, true, metadata_in);
  //return metadata_in;
    // invoke_prefetcher(uint64_t pc, uint64_t address, uint8_t cache_hit, uint8_t type, vector<uint64_t> &pref_addr);
  std::vector<uint64_t> pref_addr{};
  stride->invoke_prefetcher(ip.to<uint64_t>(), addr.to<uint64_t>(), cache_hit, champsim::to_underlying(type), pref_addr);
  for (uint64_t &pre_addr : pref_addr) {
      if (num_prints < 1000) {
        cout << "prefetching " << pre_addr << "\n";
        num_prints++;
      }
    prefetch_line(pre_addr, true, metadata_in);
  }
  return metadata_in;
}

uint32_t stride_v1::prefetcher_cache_fill(champsim::address addr, long set, long way, uint8_t prefetch, champsim::address evicted_addr, uint32_t metadata_in)
{
    // void register_fill(uint64_t address);
  //stride->register_fill(addr.to<uint64_t>());
  return metadata_in;
}

void stride_v1::prefetcher_initialize()
{
    stride = new StridePrefetcher();
}

void stride_v1::prefetcher_final_stats() {
    stride->dump_stats();
}
