#include "RunMode.h"

namespace rm27::domain {

std::optional<RunMode> parseRunMode(std::string_view value)
{
    if (value == "official") {
        return RunMode::Official;
    }
    if (value == "simulation") {
        return RunMode::Simulation;
    }
    return std::nullopt;
}

} // namespace rm27::domain

