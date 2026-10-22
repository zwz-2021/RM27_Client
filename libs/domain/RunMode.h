#pragma once

#include <optional>
#include <string_view>

namespace rm27::domain {

enum class RunMode { Official, Simulation };

std::optional<RunMode> parseRunMode(std::string_view value);

} // namespace rm27::domain

