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

#ifndef CONTEXT_SWITCH_SCHEDULE_H
#define CONTEXT_SWITCH_SCHEDULE_H

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

struct context_switch_event {
  uint64_t instruction_number{};
  uint64_t thread_id{};
};

class context_switch_schedule
{
  std::vector<context_switch_event> events_;
  std::size_t next_index_{0};

public:
  static context_switch_schedule parse_file(const std::filesystem::path& path, int log_core_id);
  static context_switch_schedule parse_lines(std::string_view text, int log_core_id);

  std::optional<uint64_t> check_and_advance(uint64_t num_retired);
};

#endif
