#include "BasicCodec.h"
#include "rm27_base.pb.h"

#include <array>
#include <cmath>
#include <type_traits>

namespace rm27::protocol {
namespace {
constexpr std::array<TopicContract, 6> contracts{{
    {"GameStatus", 5, 1}, {"GlobalUnitStatus", 1, 1},
    {"GlobalLogisticsStatus", 1, 1}, {"RobotStaticStatus", 1, 1},
    {"RobotDynamicStatus", 10, 1}, {"RobotModuleStatus", 1, 1}
}};

domain::GameData fromWire(const wire::GameStatus &source)
{
    domain::GameData result;
    if (source.has_current_round()) result.current_round = source.current_round();
    if (source.has_total_rounds()) result.total_rounds = source.total_rounds();
    if (source.has_red_score()) result.red_score = source.red_score();
    if (source.has_blue_score()) result.blue_score = source.blue_score();
    if (source.has_current_stage()) result.current_stage = source.current_stage();
    if (source.has_stage_countdown_sec()) result.stage_countdown_sec = source.stage_countdown_sec();
    if (source.has_stage_elapsed_sec()) result.stage_elapsed_sec = source.stage_elapsed_sec();
    if (source.has_is_paused()) result.is_paused = source.is_paused();
    if (source.has_game_result()) result.game_result = source.game_result();
    if (source.has_end_reason()) result.end_reason = source.end_reason();
    return result;
}

wire::GameStatus toWire(const domain::GameData &source)
{
    wire::GameStatus result;
    if (source.current_round) result.set_current_round(*source.current_round);
    if (source.total_rounds) result.set_total_rounds(*source.total_rounds);
    if (source.red_score) result.set_red_score(*source.red_score);
    if (source.blue_score) result.set_blue_score(*source.blue_score);
    if (source.current_stage) result.set_current_stage(*source.current_stage);
    if (source.stage_countdown_sec) result.set_stage_countdown_sec(*source.stage_countdown_sec);
    if (source.stage_elapsed_sec) result.set_stage_elapsed_sec(*source.stage_elapsed_sec);
    if (source.is_paused) result.set_is_paused(*source.is_paused);
    if (source.game_result) result.set_game_result(*source.game_result);
    if (source.end_reason) result.set_end_reason(*source.end_reason);
    return result;
}

domain::GlobalUnitData fromWire(const wire::GlobalUnitStatus &source)
{
    domain::GlobalUnitData result;
    if (source.has_base_health()) result.base_health = source.base_health();
    if (source.has_base_status()) result.base_status = source.base_status();
    if (source.has_base_shield()) result.base_shield = source.base_shield();
    if (source.has_outpost_r_health()) result.outpost_R_health = source.outpost_r_health();
    if (source.has_outpost_r_status()) result.outpost_R_status = source.outpost_r_status();
    if (source.has_enemy_base_health()) result.enemy_base_health = source.enemy_base_health();
    if (source.has_enemy_base_status()) result.enemy_base_status = source.enemy_base_status();
    if (source.has_enemy_base_shield()) result.enemy_base_shield = source.enemy_base_shield();
    if (source.has_outpost_b_health()) result.outpost_B_health = source.outpost_b_health();
    if (source.has_outpost_b_status()) result.outpost_B_status = source.outpost_b_status();
    if (source.has_total_damage_ally()) result.total_damage_ally = source.total_damage_ally();
    if (source.has_total_damage_enemy()) result.total_damage_enemy = source.total_damage_enemy();
    if (source.has_total_cp_ally()) result.total_CP_ally = source.total_cp_ally();
    if (source.has_total_cp_enemy()) result.total_CP_enemy = source.total_cp_enemy();
    result.robot_health.assign(source.robot_health().begin(), source.robot_health().end());
    result.robot_bullets.assign(source.robot_bullets().begin(), source.robot_bullets().end());
    return result;
}

wire::GlobalUnitStatus toWire(const domain::GlobalUnitData &source)
{
    wire::GlobalUnitStatus result;
    if (source.base_health) result.set_base_health(*source.base_health);
    if (source.base_status) result.set_base_status(*source.base_status);
    if (source.base_shield) result.set_base_shield(*source.base_shield);
    if (source.outpost_R_health) result.set_outpost_r_health(*source.outpost_R_health);
    if (source.outpost_R_status) result.set_outpost_r_status(*source.outpost_R_status);
    if (source.enemy_base_health) result.set_enemy_base_health(*source.enemy_base_health);
    if (source.enemy_base_status) result.set_enemy_base_status(*source.enemy_base_status);
    if (source.enemy_base_shield) result.set_enemy_base_shield(*source.enemy_base_shield);
    if (source.outpost_B_health) result.set_outpost_b_health(*source.outpost_B_health);
    if (source.outpost_B_status) result.set_outpost_b_status(*source.outpost_B_status);
    if (source.total_damage_ally) result.set_total_damage_ally(*source.total_damage_ally);
    if (source.total_damage_enemy) result.set_total_damage_enemy(*source.total_damage_enemy);
    if (source.total_CP_ally) result.set_total_cp_ally(*source.total_CP_ally);
    if (source.total_CP_enemy) result.set_total_cp_enemy(*source.total_CP_enemy);
    for (auto value : source.robot_health) result.add_robot_health(value);
    for (auto value : source.robot_bullets) result.add_robot_bullets(value);
    return result;
}

domain::LogisticsData fromWire(const wire::GlobalLogisticsStatus &source)
{
    domain::LogisticsData result;
    if (source.has_remaining_economy()) result.remaining_economy = source.remaining_economy();
    if (source.has_total_economy_obtained()) result.total_economy_obtained = source.total_economy_obtained();
    if (source.has_tech_level()) result.tech_level = source.tech_level();
    if (source.has_encryption_level()) result.encryption_level = source.encryption_level();
    return result;
}

wire::GlobalLogisticsStatus toWire(const domain::LogisticsData &source)
{
    wire::GlobalLogisticsStatus result;
    if (source.remaining_economy) result.set_remaining_economy(*source.remaining_economy);
    if (source.total_economy_obtained) result.set_total_economy_obtained(*source.total_economy_obtained);
    if (source.tech_level) result.set_tech_level(*source.tech_level);
    if (source.encryption_level) result.set_encryption_level(*source.encryption_level);
    return result;
}

domain::RobotStaticData fromWire(const wire::RobotStaticStatus &source)
{
    domain::RobotStaticData result;
    if (source.has_connection_state()) result.connection_state = source.connection_state();
    if (source.has_field_state()) result.field_state = source.field_state();
    if (source.has_alive_state()) result.alive_state = source.alive_state();
    if (source.has_robot_id()) result.robot_id = source.robot_id();
    if (source.has_robot_type()) result.robot_type = source.robot_type();
    if (source.has_performance_system_shooter()) result.performance_system_shooter = source.performance_system_shooter();
    if (source.has_performance_system_chassis()) result.performance_system_chassis = source.performance_system_chassis();
    if (source.has_level()) result.level = source.level();
    if (source.has_max_health()) result.max_health = source.max_health();
    if (source.has_max_heat()) result.max_heat = source.max_heat();
    if (source.has_heat_cooldown_rate()) result.heat_cooldown_rate = source.heat_cooldown_rate();
    if (source.has_max_power()) result.max_power = source.max_power();
    if (source.has_max_buffer_energy()) result.max_buffer_energy = source.max_buffer_energy();
    if (source.has_max_chassis_energy()) result.max_chassis_energy = source.max_chassis_energy();
    return result;
}

wire::RobotStaticStatus toWire(const domain::RobotStaticData &source)
{
    wire::RobotStaticStatus result;
    if (source.connection_state) result.set_connection_state(*source.connection_state);
    if (source.field_state) result.set_field_state(*source.field_state);
    if (source.alive_state) result.set_alive_state(*source.alive_state);
    if (source.robot_id) result.set_robot_id(*source.robot_id);
    if (source.robot_type) result.set_robot_type(*source.robot_type);
    if (source.performance_system_shooter) result.set_performance_system_shooter(*source.performance_system_shooter);
    if (source.performance_system_chassis) result.set_performance_system_chassis(*source.performance_system_chassis);
    if (source.level) result.set_level(*source.level);
    if (source.max_health) result.set_max_health(*source.max_health);
    if (source.max_heat) result.set_max_heat(*source.max_heat);
    if (source.heat_cooldown_rate) result.set_heat_cooldown_rate(*source.heat_cooldown_rate);
    if (source.max_power) result.set_max_power(*source.max_power);
    if (source.max_buffer_energy) result.set_max_buffer_energy(*source.max_buffer_energy);
    if (source.max_chassis_energy) result.set_max_chassis_energy(*source.max_chassis_energy);
    return result;
}

domain::RobotDynamicData fromWire(const wire::RobotDynamicStatus &source)
{
    domain::RobotDynamicData result;
    if (source.has_current_health()) result.current_health = source.current_health();
    if (source.has_current_heat()) result.current_heat = source.current_heat();
    if (source.has_last_projectile_fire_rate()) result.last_projectile_fire_rate = source.last_projectile_fire_rate();
    if (source.has_reserved()) result.reserved = source.reserved();
    if (source.has_current_buffer_energy()) result.current_buffer_energy = source.current_buffer_energy();
    if (source.has_current_experience()) result.current_experience = source.current_experience();
    if (source.has_experience_for_upgrade()) result.experience_for_upgrade = source.experience_for_upgrade();
    if (source.has_total_projectiles_fired()) result.total_projectiles_fired = source.total_projectiles_fired();
    if (source.has_remaining_ammo()) result.remaining_ammo = source.remaining_ammo();
    if (source.has_is_out_of_combat()) result.is_out_of_combat = source.is_out_of_combat();
    if (source.has_out_of_combat_countdown()) result.out_of_combat_countdown = source.out_of_combat_countdown();
    if (source.has_can_remote_heal()) result.can_remote_heal = source.can_remote_heal();
    if (source.has_can_remote_ammo()) result.can_remote_ammo = source.can_remote_ammo();
    return result;
}

wire::RobotDynamicStatus toWire(const domain::RobotDynamicData &source)
{
    wire::RobotDynamicStatus result;
    if (source.current_health) result.set_current_health(*source.current_health);
    if (source.current_heat) result.set_current_heat(*source.current_heat);
    if (source.last_projectile_fire_rate) result.set_last_projectile_fire_rate(*source.last_projectile_fire_rate);
    if (source.reserved) result.set_reserved(*source.reserved);
    if (source.current_buffer_energy) result.set_current_buffer_energy(*source.current_buffer_energy);
    if (source.current_experience) result.set_current_experience(*source.current_experience);
    if (source.experience_for_upgrade) result.set_experience_for_upgrade(*source.experience_for_upgrade);
    if (source.total_projectiles_fired) result.set_total_projectiles_fired(*source.total_projectiles_fired);
    if (source.remaining_ammo) result.set_remaining_ammo(*source.remaining_ammo);
    if (source.is_out_of_combat) result.set_is_out_of_combat(*source.is_out_of_combat);
    if (source.out_of_combat_countdown) result.set_out_of_combat_countdown(*source.out_of_combat_countdown);
    if (source.can_remote_heal) result.set_can_remote_heal(*source.can_remote_heal);
    if (source.can_remote_ammo) result.set_can_remote_ammo(*source.can_remote_ammo);
    return result;
}

domain::RobotModuleData fromWire(const wire::RobotModuleStatus &source)
{
    domain::RobotModuleData result;
    if (source.has_power_manager()) result.power_manager = source.power_manager();
    if (source.has_rfid()) result.rfid = source.rfid();
    if (source.has_light_strip()) result.light_strip = source.light_strip();
    if (source.has_small_shooter()) result.small_shooter = source.small_shooter();
    if (source.has_big_shooter()) result.big_shooter = source.big_shooter();
    if (source.has_uwb()) result.uwb = source.uwb();
    if (source.has_armor()) result.armor = source.armor();
    if (source.has_video_transmission()) result.video_transmission = source.video_transmission();
    if (source.has_capacitor()) result.capacitor = source.capacitor();
    if (source.has_main_controller()) result.main_controller = source.main_controller();
    if (source.has_modular_42mm()) result.modular_42mm = source.modular_42mm();
    return result;
}

wire::RobotModuleStatus toWire(const domain::RobotModuleData &source)
{
    wire::RobotModuleStatus result;
    if (source.power_manager) result.set_power_manager(*source.power_manager);
    if (source.rfid) result.set_rfid(*source.rfid);
    if (source.light_strip) result.set_light_strip(*source.light_strip);
    if (source.small_shooter) result.set_small_shooter(*source.small_shooter);
    if (source.big_shooter) result.set_big_shooter(*source.big_shooter);
    if (source.uwb) result.set_uwb(*source.uwb);
    if (source.armor) result.set_armor(*source.armor);
    if (source.video_transmission) result.set_video_transmission(*source.video_transmission);
    if (source.capacitor) result.set_capacitor(*source.capacitor);
    if (source.main_controller) result.set_main_controller(*source.main_controller);
    if (source.modular_42mm) result.set_modular_42mm(*source.modular_42mm);
    return result;
}

QString validate(const domain::BasicMessage &message)
{
    return std::visit([](const auto &value) -> QString {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, domain::GlobalUnitData>) {
            if (!value.robot_health.empty() && value.robot_health.size() != 8)
                return QStringLiteral("robot_health 必须为空或为协议规定的 8 项。");
            if (!value.robot_bullets.empty() && value.robot_bullets.size() != 6)
                return QStringLiteral("robot_bullets 必须为空或为 P-002 指定基准的 6 项。");
        } else if constexpr (std::is_same_v<T, domain::RobotStaticData>) {
            if (value.heat_cooldown_rate && !std::isfinite(*value.heat_cooldown_rate))
                return QStringLiteral("heat_cooldown_rate 不是有限数值。");
        } else if constexpr (std::is_same_v<T, domain::RobotDynamicData>) {
            if ((value.current_heat && !std::isfinite(*value.current_heat))
                || (value.last_projectile_fire_rate && !std::isfinite(*value.last_projectile_fire_rate)))
                return QStringLiteral("机器人热量或射速不是有限数值。");
        } else if constexpr (std::is_same_v<T, domain::RobotModuleData>) {
            for (const auto field : {value.power_manager, value.rfid, value.light_strip,
                    value.small_shooter, value.big_shooter, value.uwb, value.armor,
                    value.video_transmission, value.capacitor, value.main_controller}) {
                if (field && *field > 2)
                    return QStringLiteral("模块状态必须为 0、1 或 2。");
            }
            if (value.modular_42mm && *value.modular_42mm > 1)
                return QStringLiteral("42mm 安装权限必须为 0 或 1。");
        }
        return {};
    }, message);
}

template<class Wire>
DecodeResult parse(const QByteArray &payload)
{
    Wire message;
    if (!message.ParseFromArray(payload.constData(), static_cast<int>(payload.size())))
        return {std::nullopt, QStringLiteral("Protobuf 负载不完整或格式错误。")};
    domain::BasicMessage result = fromWire(message);
    const auto error = validate(result);
    if (!error.isEmpty()) return {std::nullopt, error};
    return {std::move(result), {}};
}
} // namespace

const TopicContract *contractFor(const QString &topic)
{
    for (const auto &contract : contracts)
        if (topic == QLatin1String(contract.name)) return &contract;
    return nullptr;
}

DecodeResult decode(const QString &topic, const QByteArray &payload)
{
    if (!contractFor(topic))
        return {std::nullopt, QStringLiteral("本批尚不支持该 topic：%1").arg(topic)};
    // Engineering memory bound, not an official fixed payload length.
    if (payload.size() > 1024 * 1024)
        return {std::nullopt, QStringLiteral("负载超过本地 1 MiB 防护上限。")};
    if (topic == QLatin1String("GameStatus")) return parse<wire::GameStatus>(payload);
    if (topic == QLatin1String("GlobalUnitStatus")) return parse<wire::GlobalUnitStatus>(payload);
    if (topic == QLatin1String("GlobalLogisticsStatus")) return parse<wire::GlobalLogisticsStatus>(payload);
    if (topic == QLatin1String("RobotStaticStatus")) return parse<wire::RobotStaticStatus>(payload);
    if (topic == QLatin1String("RobotDynamicStatus")) return parse<wire::RobotDynamicStatus>(payload);
    if (topic == QLatin1String("RobotModuleStatus")) return parse<wire::RobotModuleStatus>(payload);
    return {std::nullopt, QStringLiteral("未找到解析器。")};
}

EncodeResult encode(const domain::BasicMessage &message)
{
    const auto error = validate(message);
    if (!error.isEmpty()) return {{}, {}, error};
    return std::visit([](const auto &value) -> EncodeResult {
        const auto wire = toWire(value);
        std::string bytes;
        if (!wire.SerializeToString(&bytes))
            return {{}, {}, QStringLiteral("Protobuf 编码失败。")};
        QString topic;
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, domain::GameData>) topic = QStringLiteral("GameStatus");
        if constexpr (std::is_same_v<T, domain::GlobalUnitData>) topic = QStringLiteral("GlobalUnitStatus");
        if constexpr (std::is_same_v<T, domain::LogisticsData>) topic = QStringLiteral("GlobalLogisticsStatus");
        if constexpr (std::is_same_v<T, domain::RobotStaticData>) topic = QStringLiteral("RobotStaticStatus");
        if constexpr (std::is_same_v<T, domain::RobotDynamicData>) topic = QStringLiteral("RobotDynamicStatus");
        if constexpr (std::is_same_v<T, domain::RobotModuleData>) topic = QStringLiteral("RobotModuleStatus");
        return {topic, QByteArray(bytes.data(), static_cast<qsizetype>(bytes.size())), {}};
    }, message);
}
} // namespace rm27::protocol

