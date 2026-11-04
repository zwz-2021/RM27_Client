#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <variant>
#include <vector>

namespace rm27::domain {

enum class Team { Red, Blue };
enum class RobotRole { Heavy, Reserved, Infantry, Aerial, Sentry, Dart, Radar, Base, Outpost };
struct RobotIdentity {
    std::uint32_t id;
    Team team;
    RobotRole role;
};

// P-003, user instruction 2026-11-01: migrate RM26's static-message convention.
// These numbers belong to RobotStaticStatus.robot_type, not RobotStatus.type.
inline std::optional<RobotRole> robotRoleFromStaticType(std::uint32_t type)
{
    switch (type) {
    case 1: return RobotRole::Heavy;
    case 2: return RobotRole::Reserved;
    case 3: case 4: case 5: return RobotRole::Infantry;
    case 6: return RobotRole::Aerial;
    case 7: return RobotRole::Sentry;
    case 8: return RobotRole::Dart;
    case 9: return RobotRole::Radar;
    default: return std::nullopt;
    }
}

// Appendix 2 IDs are independent of the type fallback above. In particular,
// IDs 10/11 name base/outpost, but no static type 10/11 convention was found.
inline std::optional<RobotIdentity> identifyRobot(std::uint32_t id)
{
    const bool blue = id >= 101 && id <= 111;
    if (!(id >= 1 && id <= 11) && !blue) return std::nullopt;
    const auto number = blue ? id - 100 : id;
    RobotRole role;
    switch (number) {
    case 1: role = RobotRole::Heavy; break;
    case 2: role = RobotRole::Reserved; break;
    case 3: case 4: case 5: role = RobotRole::Infantry; break;
    case 6: role = RobotRole::Aerial; break;
    case 7: role = RobotRole::Sentry; break;
    case 8: role = RobotRole::Dart; break;
    case 9: role = RobotRole::Radar; break;
    case 10: role = RobotRole::Base; break;
    case 11: role = RobotRole::Outpost; break;
    default: return std::nullopt;
    }
    return RobotIdentity{id, blue ? Team::Blue : Team::Red, role};
}

// Missing optional values remain unknown; zero is a valid received value.
struct GameData {
    std::optional<std::uint32_t> current_round, total_rounds, red_score, blue_score, current_stage;
    std::optional<std::int32_t> stage_countdown_sec, stage_elapsed_sec;
    std::optional<bool> is_paused;
    std::optional<std::uint32_t> game_result, end_reason;
};

struct GlobalUnitData {
    std::optional<std::uint32_t> base_health, base_status, base_shield;
    std::optional<std::uint32_t> outpost_R_health, outpost_R_status;
    std::optional<std::uint32_t> enemy_base_health, enemy_base_status, enemy_base_shield;
    std::optional<std::uint32_t> outpost_B_health, outpost_B_status;
    std::vector<std::uint32_t> robot_health;
    std::vector<std::int32_t> robot_bullets;
    std::optional<std::uint32_t> total_damage_ally, total_damage_enemy, total_CP_ally, total_CP_enemy;
};

struct LogisticsData {
    std::optional<std::uint32_t> remaining_economy;
    std::optional<std::uint64_t> total_economy_obtained;
    std::optional<std::uint32_t> tech_level, encryption_level;
};

struct RobotStaticData {
    std::optional<std::uint32_t> connection_state, field_state, alive_state, robot_id;
    // Keep the raw optional number, including zero and unknown future values.
    std::optional<std::uint32_t> robot_type;
    std::optional<std::uint32_t> performance_system_shooter, performance_system_chassis, level;
    std::optional<std::uint32_t> max_health, max_heat;
    std::optional<float> heat_cooldown_rate;
    std::optional<std::uint32_t> max_power, max_buffer_energy, max_chassis_energy;

    std::optional<RobotRole> role() const
    {
        // Same precedence as the reference client: known ID first, type second.
        // A type fallback does not invent a robot ID or team.
        if (robot_id) {
            if (const auto identity = identifyRobot(*robot_id)) return identity->role;
        }
        return robot_type ? robotRoleFromStaticType(*robot_type) : std::nullopt;
    }
};

struct RobotDynamicData {
    std::optional<std::uint32_t> current_health;
    std::optional<float> current_heat, last_projectile_fire_rate;
    std::optional<std::uint32_t> reserved, current_buffer_energy, current_experience;
    std::optional<std::uint32_t> experience_for_upgrade, total_projectiles_fired, remaining_ammo;
    std::optional<bool> is_out_of_combat;
    std::optional<std::uint32_t> out_of_combat_countdown;
    std::optional<bool> can_remote_heal, can_remote_ammo;
};

using BasicMessage = std::variant<GameData, GlobalUnitData, LogisticsData,
                                  RobotStaticData, RobotDynamicData>;

// Relative slots; blue IDs = red IDs + 100. Health includes both teams.
inline constexpr std::array<int, 8> healthSlots{1, 3, 4, 7, 101, 103, 104, 107};
// P-002: the existing simulator/RM26 sending order, not an official array definition.
inline constexpr std::array<int, 6> bulletSlots{1, 2, 3, 4, 6, 7};

inline std::array<int, 8> healthRobotIds(bool bluePerspective)
{
    return bluePerspective ? std::array<int, 8>{101, 103, 104, 107, 1, 3, 4, 7} : healthSlots;
}

inline std::array<int, 6> bulletRobotIds(bool bluePerspective)
{
    auto ids = bulletSlots;
    if (bluePerspective) {
        for (auto &id : ids) id += 100;
    }
    return ids;
}

} // namespace rm27::domain
