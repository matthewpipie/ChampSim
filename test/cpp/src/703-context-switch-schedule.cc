#include <catch.hpp>

#include <sstream>
#include <string>

#include "context_switch_schedule.h"

TEST_CASE("context_switch_schedule parses and filters by core id")
{
  const std::string log = R"(noise line
***0,100,111
***1,200,222
***0,300,333,9999
***0,400,444
Thread 0 processed 500 instructions
***0,500,555,1
)";

  auto sched0 = context_switch_schedule::parse_lines(log, 0);
  auto sched1 = context_switch_schedule::parse_lines(log, 1);

  REQUIRE_FALSE(sched0.check_and_advance(99).has_value());
  {
    const auto boundary = sched0.check_and_advance(100);
    REQUIRE(boundary.has_value());
    REQUIRE(boundary->new_thread_id == 111);
    REQUIRE(boundary->old_context_length == 100);
    REQUIRE(boundary->new_context_length == 200);
  }
  REQUIRE(sched0.check_and_advance(150) == std::nullopt);
  {
    const auto boundary = sched0.check_and_advance(300);
    REQUIRE(boundary.has_value());
    REQUIRE(boundary->new_thread_id == 333);
    REQUIRE(boundary->old_context_length == 200);
    REQUIRE(boundary->new_context_length == 100);
  }
  {
    const auto boundary = sched0.check_and_advance(400);
    REQUIRE(boundary.has_value());
    REQUIRE(boundary->new_thread_id == 444);
    REQUIRE(boundary->old_context_length == 100);
    REQUIRE(boundary->new_context_length == 100);
  }
  {
    const auto boundary = sched0.check_and_advance(500);
    REQUIRE(boundary.has_value());
    REQUIRE(boundary->new_thread_id == 555);
    REQUIRE(boundary->old_context_length == 100);
    REQUIRE(boundary->new_context_length == 0);
  }

  REQUIRE_FALSE(sched1.check_and_advance(199).has_value());
  {
    const auto boundary = sched1.check_and_advance(200);
    REQUIRE(boundary.has_value());
    REQUIRE(boundary->new_thread_id == 222);
    REQUIRE(boundary->old_context_length == 200);
    REQUIRE(boundary->new_context_length == 0);
  }
}

TEST_CASE("context_switch_schedule fires multiple switches in one cycle")
{
  const std::string log = "***0,10,1\n***0,20,2\n";
  auto sched = context_switch_schedule::parse_lines(log, 0);

  {
    const auto boundary = sched.check_and_advance(25);
    REQUIRE(boundary.has_value());
    REQUIRE(boundary->new_thread_id == 1);
    REQUIRE(boundary->old_context_length == 10);
    REQUIRE(boundary->new_context_length == 10);
  }
  {
    const auto boundary = sched.check_and_advance(25);
    REQUIRE(boundary.has_value());
    REQUIRE(boundary->new_thread_id == 2);
    REQUIRE(boundary->old_context_length == 10);
    REQUIRE(boundary->new_context_length == 0);
  }
  REQUIRE(sched.check_and_advance(25) == std::nullopt);
}

TEST_CASE("context_switch_schedule rejects non-monotonic instruction numbers")
{
  const std::string log = "***0,10,1\n***0,10,2\n";
  REQUIRE_THROWS_AS(context_switch_schedule::parse_lines(log, 0), std::runtime_error);
}
