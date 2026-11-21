#include "protocol/BasicCodec.h"
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTextStream>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <type_traits>

using namespace rm27;
namespace {
void check(bool condition, const char *description)
{
    if (!condition) throw std::runtime_error(description);
}

template<class T> T decoded(const char *topic, const char *hex)
{
    auto result = protocol::decode(QString::fromLatin1(topic), QByteArray::fromHex(hex));
    check(result.message.has_value(), "fixed payload must parse");
    return std::get<T>(*result.message);
}

QJsonObject toJson(const domain::BasicMessage &message)
{
    return std::visit([](const auto &value) -> QJsonObject {
        QJsonObject result;
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, domain::GameData>) {
            if (value.current_round) result.insert(QStringLiteral("current_round"), static_cast<double>(*value.current_round));
            if (value.total_rounds) result.insert(QStringLiteral("total_rounds"), static_cast<double>(*value.total_rounds));
            if (value.red_score) result.insert(QStringLiteral("red_score"), static_cast<double>(*value.red_score));
            if (value.blue_score) result.insert(QStringLiteral("blue_score"), static_cast<double>(*value.blue_score));
            if (value.current_stage) result.insert(QStringLiteral("current_stage"), static_cast<double>(*value.current_stage));
            if (value.stage_countdown_sec) result.insert(QStringLiteral("stage_countdown_sec"), static_cast<double>(*value.stage_countdown_sec));
            if (value.stage_elapsed_sec) result.insert(QStringLiteral("stage_elapsed_sec"), static_cast<double>(*value.stage_elapsed_sec));
            if (value.is_paused) result.insert(QStringLiteral("is_paused"), *value.is_paused);
            if (value.game_result) result.insert(QStringLiteral("game_result"), static_cast<double>(*value.game_result));
            if (value.end_reason) result.insert(QStringLiteral("end_reason"), static_cast<double>(*value.end_reason));
        }
        if constexpr (std::is_same_v<T, domain::GlobalUnitData>) {
            if (value.base_health) result.insert(QStringLiteral("base_health"), static_cast<double>(*value.base_health));
            if (value.base_status) result.insert(QStringLiteral("base_status"), static_cast<double>(*value.base_status));
            if (value.base_shield) result.insert(QStringLiteral("base_shield"), static_cast<double>(*value.base_shield));
            if (value.outpost_R_health) result.insert(QStringLiteral("outpost_R_health"), static_cast<double>(*value.outpost_R_health));
            if (value.outpost_R_status) result.insert(QStringLiteral("outpost_R_status"), static_cast<double>(*value.outpost_R_status));
            if (value.enemy_base_health) result.insert(QStringLiteral("enemy_base_health"), static_cast<double>(*value.enemy_base_health));
            if (value.enemy_base_status) result.insert(QStringLiteral("enemy_base_status"), static_cast<double>(*value.enemy_base_status));
            if (value.enemy_base_shield) result.insert(QStringLiteral("enemy_base_shield"), static_cast<double>(*value.enemy_base_shield));
            if (value.outpost_B_health) result.insert(QStringLiteral("outpost_B_health"), static_cast<double>(*value.outpost_B_health));
            if (value.outpost_B_status) result.insert(QStringLiteral("outpost_B_status"), static_cast<double>(*value.outpost_B_status));
            if (value.total_damage_ally) result.insert(QStringLiteral("total_damage_ally"), static_cast<double>(*value.total_damage_ally));
            if (value.total_damage_enemy) result.insert(QStringLiteral("total_damage_enemy"), static_cast<double>(*value.total_damage_enemy));
            if (value.total_CP_ally) result.insert(QStringLiteral("total_CP_ally"), static_cast<double>(*value.total_CP_ally));
            if (value.total_CP_enemy) result.insert(QStringLiteral("total_CP_enemy"), static_cast<double>(*value.total_CP_enemy));
            QJsonArray robot_health;
            for (auto item : value.robot_health) robot_health.append(static_cast<double>(item));
            result.insert(QStringLiteral("robot_health"), robot_health);
            QJsonArray robot_bullets;
            for (auto item : value.robot_bullets) robot_bullets.append(static_cast<double>(item));
            result.insert(QStringLiteral("robot_bullets"), robot_bullets);
        }
        if constexpr (std::is_same_v<T, domain::LogisticsData>) {
            if (value.remaining_economy) result.insert(QStringLiteral("remaining_economy"), static_cast<double>(*value.remaining_economy));
            if (value.total_economy_obtained) result.insert(QStringLiteral("total_economy_obtained"), QString::number(*value.total_economy_obtained));
            if (value.tech_level) result.insert(QStringLiteral("tech_level"), static_cast<double>(*value.tech_level));
            if (value.encryption_level) result.insert(QStringLiteral("encryption_level"), static_cast<double>(*value.encryption_level));
        }
        if constexpr (std::is_same_v<T, domain::RobotStaticData>) {
            if (value.connection_state) result.insert(QStringLiteral("connection_state"), static_cast<double>(*value.connection_state));
            if (value.field_state) result.insert(QStringLiteral("field_state"), static_cast<double>(*value.field_state));
            if (value.alive_state) result.insert(QStringLiteral("alive_state"), static_cast<double>(*value.alive_state));
            if (value.robot_id) result.insert(QStringLiteral("robot_id"), static_cast<double>(*value.robot_id));
            if (value.robot_type) result.insert(QStringLiteral("robot_type"), static_cast<double>(*value.robot_type));
            if (value.performance_system_shooter) result.insert(QStringLiteral("performance_system_shooter"), static_cast<double>(*value.performance_system_shooter));
            if (value.performance_system_chassis) result.insert(QStringLiteral("performance_system_chassis"), static_cast<double>(*value.performance_system_chassis));
            if (value.level) result.insert(QStringLiteral("level"), static_cast<double>(*value.level));
            if (value.max_health) result.insert(QStringLiteral("max_health"), static_cast<double>(*value.max_health));
            if (value.max_heat) result.insert(QStringLiteral("max_heat"), static_cast<double>(*value.max_heat));
            if (value.heat_cooldown_rate) result.insert(QStringLiteral("heat_cooldown_rate"), static_cast<double>(*value.heat_cooldown_rate));
            if (value.max_power) result.insert(QStringLiteral("max_power"), static_cast<double>(*value.max_power));
            if (value.max_buffer_energy) result.insert(QStringLiteral("max_buffer_energy"), static_cast<double>(*value.max_buffer_energy));
            if (value.max_chassis_energy) result.insert(QStringLiteral("max_chassis_energy"), static_cast<double>(*value.max_chassis_energy));
        }
        if constexpr (std::is_same_v<T, domain::RobotDynamicData>) {
            if (value.current_health) result.insert(QStringLiteral("current_health"), static_cast<double>(*value.current_health));
            if (value.current_heat) result.insert(QStringLiteral("current_heat"), static_cast<double>(*value.current_heat));
            if (value.last_projectile_fire_rate) result.insert(QStringLiteral("last_projectile_fire_rate"), static_cast<double>(*value.last_projectile_fire_rate));
            if (value.reserved) result.insert(QStringLiteral("reserved"), static_cast<double>(*value.reserved));
            if (value.current_buffer_energy) result.insert(QStringLiteral("current_buffer_energy"), static_cast<double>(*value.current_buffer_energy));
            if (value.current_experience) result.insert(QStringLiteral("current_experience"), static_cast<double>(*value.current_experience));
            if (value.experience_for_upgrade) result.insert(QStringLiteral("experience_for_upgrade"), static_cast<double>(*value.experience_for_upgrade));
            if (value.total_projectiles_fired) result.insert(QStringLiteral("total_projectiles_fired"), static_cast<double>(*value.total_projectiles_fired));
            if (value.remaining_ammo) result.insert(QStringLiteral("remaining_ammo"), static_cast<double>(*value.remaining_ammo));
            if (value.is_out_of_combat) result.insert(QStringLiteral("is_out_of_combat"), *value.is_out_of_combat);
            if (value.out_of_combat_countdown) result.insert(QStringLiteral("out_of_combat_countdown"), static_cast<double>(*value.out_of_combat_countdown));
            if (value.can_remote_heal) result.insert(QStringLiteral("can_remote_heal"), *value.can_remote_heal);
            if (value.can_remote_ammo) result.insert(QStringLiteral("can_remote_ammo"), *value.can_remote_ammo);
        }
        if constexpr (std::is_same_v<T, domain::RobotModuleData>) {
            if (value.power_manager) result.insert(QStringLiteral("power_manager"), static_cast<double>(*value.power_manager));
            if (value.rfid) result.insert(QStringLiteral("rfid"), static_cast<double>(*value.rfid));
            if (value.light_strip) result.insert(QStringLiteral("light_strip"), static_cast<double>(*value.light_strip));
            if (value.small_shooter) result.insert(QStringLiteral("small_shooter"), static_cast<double>(*value.small_shooter));
            if (value.big_shooter) result.insert(QStringLiteral("big_shooter"), static_cast<double>(*value.big_shooter));
            if (value.uwb) result.insert(QStringLiteral("uwb"), static_cast<double>(*value.uwb));
            if (value.armor) result.insert(QStringLiteral("armor"), static_cast<double>(*value.armor));
            if (value.video_transmission) result.insert(QStringLiteral("video_transmission"), static_cast<double>(*value.video_transmission));
            if (value.capacitor) result.insert(QStringLiteral("capacitor"), static_cast<double>(*value.capacitor));
            if (value.main_controller) result.insert(QStringLiteral("main_controller"), static_cast<double>(*value.main_controller));
            if (value.modular_42mm) result.insert(QStringLiteral("modular_42mm"), static_cast<double>(*value.modular_42mm));
        }
        return result;
    }, message);
}

QString staticRoleName(const domain::RobotStaticData &message)
{
    const auto role = message.role();
    if (!role) return QStringLiteral("未知");
    switch (*role) {
    case domain::RobotRole::Heavy: return QStringLiteral("重装");
    case domain::RobotRole::Reserved: return QStringLiteral("保留");
    case domain::RobotRole::Infantry: return QStringLiteral("步兵");
    case domain::RobotRole::Aerial: return QStringLiteral("空中");
    case domain::RobotRole::Sentry: return QStringLiteral("哨兵");
    case domain::RobotRole::Dart: return QStringLiteral("飞镖");
    case domain::RobotRole::Radar: return QStringLiteral("雷达");
    case domain::RobotRole::Base: return QStringLiteral("基地");
    case domain::RobotRole::Outpost: return QStringLiteral("前哨");
    }
    return QStringLiteral("未知");
}

void selfTest()
{
    // Hand-calculated wire bytes, independently checked against the PDF.
    const auto game = decoded<domain::GameData>("GameStatus", "280430c1023806400048ff0150ff01");
    check(game.current_stage == 4 && game.stage_countdown_sec == 321, "stage/countdown field numbers");
    check(game.stage_elapsed_sec == 6 && game.is_paused && !*game.is_paused, "elapsed/false presence");
    check(game.game_result == 255 && game.end_reason == 255 && !game.current_round, "unset vs result sentinel");
    const auto dynamic = decoded<domain::RobotDynamicData>("RobotDynamicStatus", "08c10215000048414863");
    check(dynamic.current_health == 321 && dynamic.current_heat == 12.5f, "health and float heat");
    check(dynamic.remaining_ammo == 99 && !dynamic.reserved, "ammo is field 9, field 4 reserved");
    const auto stat = decoded<domain::RobotStaticData>("RobotStaticStatus", "206748d80450f001");
    check(stat.robot_id == 103 && stat.max_health == 600 && stat.max_heat == 240, "static ID/limits");
    const auto unit = decoded<domain::GlobalUnitData>("GlobalUnitStatus", "5a08010203040506070862060b16212c3742");
    check(unit.robot_health == std::vector<std::uint32_t>({1,2,3,4,5,6,7,8}), "eight health slots");
    check(unit.robot_bullets == std::vector<std::int32_t>({11,22,33,44,55,66}), "P-002 six bullet slots");
    const auto logistics = decoded<domain::LogisticsData>("GlobalLogisticsStatus", "080010ffffffffffffffffff01");
    check(logistics.remaining_economy == 0 && logistics.total_economy_obtained == std::numeric_limits<std::uint64_t>::max(),
          "zero economy presence and full uint64 precision");

    for (auto topic : {"GameStatus", "GlobalUnitStatus", "GlobalLogisticsStatus", "RobotStaticStatus", "RobotDynamicStatus", "RobotModuleStatus"}) {
        const auto empty = protocol::decode(QString::fromLatin1(topic), {});
        check(empty.message.has_value(), "empty protobuf is valid but unknown");
        const auto encoded = protocol::encode(*empty.message);
        check(encoded.error.isEmpty() && encoded.payload.isEmpty(), "empty stays empty");
        check(protocol::contractFor(QString::fromLatin1(topic))->maximumQos == 1, "QoS maximum 1");
    }
    check(!protocol::decode(QStringLiteral("GameStatus"), QByteArray::fromHex("3080")).message, "reject truncated varint");
    check(!protocol::decode(QStringLiteral("GameStatus"), QByteArray::fromHex("00")).message, "reject invalid field zero");
    check(!protocol::decode(QStringLiteral("NotATopic"), {}).message, "reject unsupported topic");
    check(!protocol::decode(QStringLiteral("GlobalUnitStatus"), QByteArray::fromHex("5a0101")).message, "reject wrong health length");
    check(!protocol::decode(QStringLiteral("GlobalUnitStatus"), QByteArray::fromHex("620101")).message, "reject wrong bullets length");
    check(!protocol::decode(QStringLiteral("RobotDynamicStatus"), QByteArray::fromHex("150000c07f")).message, "reject NaN heat");
    const auto future = decoded<domain::GameData>("GameStatus", "288407980607");
    check(future.current_stage == 900, "preserve unknown stage, accept unknown protobuf fields");

    const auto module = decoded<domain::RobotModuleData>("RobotModuleStatus", "08001001180220002801300238004001480250005801");
    check(module.power_manager == 0 && module.rfid == 1 && module.light_strip == 2
          && module.small_shooter == 0 && module.big_shooter == 1 && module.uwb == 2
          && module.armor == 0 && module.video_transmission == 1 && module.capacitor == 2
          && module.main_controller == 0 && module.modular_42mm == 1, "eleven module field numbers and independent values");
    const auto moduleEncoded = protocol::encode(module);
    check(moduleEncoded.error.isEmpty() && moduleEncoded.payload.toHex() == "08001001180220002801300238004001480250005801",
          "module fixed bytes roundtrip");
    const auto moduleZero = decoded<domain::RobotModuleData>("RobotModuleStatus", "5800");
    check(moduleZero.modular_42mm == 0 && !moduleZero.armor && !moduleZero.power_manager,
          "permission zero present and missing modules stay missing");
    for (int field = 1; field <= 11; ++field) {
        QByteArray invalid;
        invalid.append(static_cast<char>(field << 3));
        invalid.append(static_cast<char>(field == 11 ? 2 : 3));
        check(!protocol::decode(QStringLiteral("RobotModuleStatus"), invalid).message,
              "module invalid enum must reject the entire sample");
    }
    auto invalidPermission = module;
    invalidPermission.modular_42mm = 2;
    check(!protocol::encode(invalidPermission).error.isEmpty(), "encoder rejects permission 2");
    check(!protocol::decode(QStringLiteral("RobotModuleStatus"), QByteArray::fromHex("5880")).message,
          "module truncated varint rejected");
    const auto moduleFuture = decoded<domain::RobotModuleData>("RobotModuleStatus", "3801980601");
    check(moduleFuture.armor == 1, "unknown protobuf fields do not create extra armor states");
    check(protocol::contractFor(QStringLiteral("RobotModuleStatus"))->frequencyHz == 1,
          "module frequency is 1 Hz");

    domain::GameData signedTime;
    signedTime.stage_countdown_sec = -1;
    signedTime.stage_elapsed_sec = std::numeric_limits<std::int32_t>::min();
    auto encoded = protocol::encode(signedTime);
    auto result = protocol::decode(encoded.topic, encoded.payload);
    check(result.message && std::get<domain::GameData>(*result.message).stage_countdown_sec == -1
          && std::get<domain::GameData>(*result.message).stage_elapsed_sec == std::numeric_limits<std::int32_t>::min(),
          "signed time preserved");

    domain::GlobalUnitData signedAmmo;
    signedAmmo.robot_bullets = {-1,0,1,2,3,std::numeric_limits<std::int32_t>::min()};
    encoded = protocol::encode(signedAmmo);
    result = protocol::decode(encoded.topic, encoded.payload);
    check(result.message && std::get<domain::GlobalUnitData>(*result.message).robot_bullets == signedAmmo.robot_bullets,
          "signed cumulative ammo preserved");
    domain::RobotStaticData unknownType;
    unknownType.robot_type = 900;
    encoded = protocol::encode(unknownType);
    result = protocol::decode(encoded.topic, encoded.payload);
    check(result.message && std::get<domain::RobotStaticData>(*result.message).robot_type == 900, "P-003 raw type preserved");
    check(!std::get<domain::RobotStaticData>(*result.message).role(), "unknown type remains unknown");

    // P-003: independently checked against the two appendices and RM26 code.
    for (std::uint32_t type = 1; type <= 9; ++type) {
        const std::array<domain::RobotRole, 9> roles{
            domain::RobotRole::Heavy, domain::RobotRole::Reserved,
            domain::RobotRole::Infantry, domain::RobotRole::Infantry, domain::RobotRole::Infantry,
            domain::RobotRole::Aerial, domain::RobotRole::Sentry, domain::RobotRole::Dart, domain::RobotRole::Radar};
        domain::RobotStaticData typeOnly;
        typeOnly.robot_type = type;
        encoded = protocol::encode(typeOnly);
        result = protocol::decode(encoded.topic, encoded.payload);
        const auto &received = std::get<domain::RobotStaticData>(*result.message);
        check(received.role() == roles[type - 1], "P-003 static type role mapping");
        check(!received.robot_id && received.robot_type == type, "type fallback preserves missing ID");
        for (const auto offset : {0u, 100u}) {
            typeOnly.robot_id = type + offset;
            typeOnly.robot_type = 900; // Even an unknown type cannot override a known ID.
            encoded = protocol::encode(typeOnly);
            result = protocol::decode(encoded.topic, encoded.payload);
            const auto &identified = std::get<domain::RobotStaticData>(*result.message);
            check(identified.role() == roles[type - 1], "P-003 red/blue ID takes precedence");
            check(identified.robot_type == 900, "P-003 precedence does not rewrite raw type");
        }
    }
    auto fallback = decoded<domain::RobotStaticData>("RobotStaticStatus", "20e7072806");
    check(fallback.robot_id == 999 && fallback.robot_type == 6
          && fallback.role() == domain::RobotRole::Aerial, "unknown ID uses known type 6");
    const auto missingType = decoded<domain::RobotStaticData>("RobotStaticStatus", "2065");
    check(!missingType.robot_type && missingType.role() == domain::RobotRole::Heavy,
          "known ID without type remains identifiable, missing type stays missing");
    const auto zeroType = decoded<domain::RobotStaticData>("RobotStaticStatus", "2800");
    check(zeroType.robot_type == 0 && !zeroType.role(), "explicit type zero is present and unknown");
    check(!domain::RobotStaticData{}.role(), "empty static message has no role");
    check(!domain::robotRoleFromStaticType(10) && !domain::robotRoleFromStaticType(11),
          "appendix object IDs do not invent static types 10 or 11");

    check(domain::healthRobotIds(false) == std::array<int,8>{1,3,4,7,101,103,104,107}, "red health IDs");
    check(domain::healthRobotIds(true) == std::array<int,8>{101,103,104,107,1,3,4,7}, "blue health IDs");
    check(domain::bulletRobotIds(true) == std::array<int,6>{101,102,103,104,106,107}, "blue P-002 IDs");
    check(domain::identifyRobot(1)->role == domain::RobotRole::Heavy, "2027 heavy ID");
    check(domain::identifyRobot(102)->role == domain::RobotRole::Reserved, "2027 reserved ID");
    check(domain::identifyRobot(105)->role == domain::RobotRole::Infantry, "2027 infantry 5 ID");
    check(domain::identifyRobot(106)->role == domain::RobotRole::Aerial, "2027 aerial ID");
    check(domain::identifyRobot(111)->team == domain::Team::Blue, "blue outpost ID");
    check(!domain::identifyRobot(100) && !domain::identifyRobot(12), "unknown IDs stay unknown");
    check(protocol::contractFor(QStringLiteral("GameStatus"))->frequencyHz == 5, "game frequency");
    check(protocol::contractFor(QStringLiteral("RobotDynamicStatus"))->frequencyHz == 10, "dynamic frequency");
    check(protocol::contractFor(QStringLiteral("RobotStaticStatus"))->frequencyHz == 1, "static frequency");
}

void emitFixtures(const QString &directory)
{
    QDir dir(directory);
    check(dir.exists() || dir.mkpath(QStringLiteral(".")), "create fixture output directory");
    domain::GameData game;
    game.current_stage = 4; game.stage_countdown_sec = -1; game.is_paused = false;
    game.game_result = 255; game.end_reason = 255;
    domain::GlobalUnitData unit;
    unit.robot_health = {321,322,323,324,325,326,327,328};
    unit.robot_bullets = {-1,0,333,334,336,337};
    unit.outpost_R_health = 123; unit.outpost_B_health = 456;
    unit.total_CP_ally = 12; unit.total_CP_enemy = 34;
    domain::LogisticsData logistics;
    logistics.remaining_economy = 0;
    logistics.total_economy_obtained = std::numeric_limits<std::uint64_t>::max();
    domain::RobotStaticData stat;
    stat.robot_id = 103; stat.robot_type = 3; stat.max_health = 600; stat.max_heat = 240;
    stat.heat_cooldown_rate = 12.5f;
    domain::RobotDynamicData dynamic;
    dynamic.current_health = 321; dynamic.current_heat = 12.5f;
    dynamic.remaining_ammo = std::numeric_limits<std::uint32_t>::max();
    dynamic.reserved = 0;
    for (const domain::BasicMessage &message : std::vector<domain::BasicMessage>{game,unit,logistics,stat,dynamic}) {
        const auto encoded = protocol::encode(message);
        check(encoded.error.isEmpty(), "encode C++ fixture");
        QFile file(dir.filePath(encoded.topic + QStringLiteral(".bin")));
        check(file.open(QIODevice::WriteOnly), "open C++ fixture output");
        check(file.write(encoded.payload) == encoded.payload.size(), "write C++ fixture");
    }
}
} // namespace

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    try {
        const auto args = app.arguments();
        if (args.size() == 4 && (args[1] == QStringLiteral("--decode")
                                || args[1] == QStringLiteral("--decode-role"))) {
            QFile file(args[3]);
            check(file.open(QIODevice::ReadOnly), "open payload file");
            const auto decoded = protocol::decode(args[2], file.readAll());
            if (!decoded.message) {
                QTextStream(stderr) << decoded.error << Qt::endl;
                return 1;
            }
            auto json = toJson(*decoded.message);
            if (args[1] == QStringLiteral("--decode-role")) {
                check(std::holds_alternative<domain::RobotStaticData>(*decoded.message),
                      "--decode-role requires RobotStaticStatus");
                // Diagnostic output only. No extra field is added to the wire.
                json.insert(QStringLiteral("role"), staticRoleName(std::get<domain::RobotStaticData>(*decoded.message)));
            }
            QTextStream(stdout) << QJsonDocument(json).toJson(QJsonDocument::Compact) << Qt::endl;
        } else if (args.size() == 3 && args[1] == QStringLiteral("--emit-fixtures")) {
            emitFixtures(args[2]);
        } else if (args.size() == 1) {
            selfTest();
            QTextStream(stdout) << "Protocol basic checks passed." << Qt::endl;
        } else {
            QTextStream(stderr) << "Usage: RM27_ProtocolCheck [--decode TOPIC FILE | --decode-role RobotStaticStatus FILE | --emit-fixtures DIR]" << Qt::endl;
            return 2;
        }
        return 0;
    } catch (const std::exception &error) {
        QTextStream(stderr) << error.what() << Qt::endl;
        return 1;
    }
}

