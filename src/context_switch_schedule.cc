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

#include "context_switch_schedule.h"

#include <algorithm>
#include <fstream>
#include <regex>
#include <sstream>
#include <stdexcept>

namespace
{
const std::regex context_switch_line_re{R"(^\*\*\*(\d+),(\d+),(\d+)(?:,\d+)?\s*$)"};

bool parse_context_switch_line(std::string_view line, int log_core_id, context_switch_event& out)
{
  if (line.find("Processed") != std::string_view::npos) {
    return false;
  }

  const std::string line_str{line};
  std::smatch match;
  if (!std::regex_match(line_str, match, context_switch_line_re)) {
    return false;
  }

  const int core_id = std::stoi(match[1].str());
  if (core_id != log_core_id) {
    return false;
  }

  out.instruction_number = std::stoull(match[2].str());
  out.thread_id = std::stoull(match[3].str());
  return true;
}
} // namespace

context_switch_schedule context_switch_schedule::parse_file(const std::filesystem::path& path, int log_core_id)
{
  std::ifstream in{path};
  if (!in) {
    throw std::runtime_error{"failed to open context switch log: " + path.string()};
  }

  std::ostringstream buffer;
  buffer << in.rdbuf();
  return parse_lines(buffer.str(), log_core_id);
}

context_switch_schedule context_switch_schedule::parse_lines(std::string_view text, int log_core_id)
{
  context_switch_schedule sched;
  std::istringstream in{std::string{text}};
  std::string line;

  while (std::getline(in, line)) {
    if (!line.empty() && line.back() == '\r') {
      line.pop_back();
    }

    context_switch_event event{};
    if (parse_context_switch_line(line, log_core_id, event)) {
      sched.events_.push_back(event);
    }
  }

  std::sort(sched.events_.begin(), sched.events_.end(),
            [](const context_switch_event& a, const context_switch_event& b) { return a.instruction_number < b.instruction_number; });

  for (std::size_t i = 1; i < sched.events_.size(); ++i) {
    if (sched.events_[i].instruction_number <= sched.events_[i - 1].instruction_number) {
      throw std::runtime_error{"context switch log instruction numbers must be strictly increasing for core " + std::to_string(log_core_id)};
    }
  }

  return sched;
}

std::optional<context_switch_boundary> context_switch_schedule::check_and_advance(uint64_t num_retired)
{
  if (next_index_ >= events_.size()) {
    return std::nullopt;
  }

  if (num_retired < events_[next_index_].instruction_number) {
    return std::nullopt;
  }

  const std::size_t current_index = next_index_;
  const uint64_t switch_instruction = events_[current_index].instruction_number;
  const uint64_t new_thread_id = events_[current_index].thread_id;

  const uint64_t old_context_length = switch_instruction - last_switch_instruction_number_;
  const uint64_t new_context_length =
      (current_index + 1 < events_.size()) ? events_[current_index + 1].instruction_number - switch_instruction : 0;

  last_switch_instruction_number_ = switch_instruction;
  ++next_index_;

  return context_switch_boundary{new_thread_id, old_context_length, new_context_length};
}
