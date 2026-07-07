/*
 *    Copyright 2023 The ChampSim Contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef BLOCK_H
#define BLOCK_H

#include "champsim.h"

namespace champsim
{
enum class line_kind { PrefetchUnknown, Data, Instr };

// Realistic context-switch save/restore (see CACHE::handle_context_switch).
//   LIVE       - normal line.
//   SAVE_PEND  - still-valid, still-serving line whose metadata writeout to the scratch
//                region is queued/in-flight; cleared to LIVE once the save write is issued.
//   RESTORE_PEND - reserved for a future pre-placement variant (unused in the baseline,
//                  which tracks restores in a side map).
enum class cs_line_state : uint8_t { LIVE, SAVE_PEND, RESTORE_PEND };

struct cache_block {
  bool valid = false;
  bool prefetch = false;
  bool dirty = false;

  line_kind kind = line_kind::Data;
  cs_line_state cs_state = cs_line_state::LIVE;

  champsim::address address{};
  champsim::address v_address{};
  champsim::address data{};

  uint32_t pf_metadata = 0;
};
} // namespace champsim

#endif
