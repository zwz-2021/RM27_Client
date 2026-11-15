#include "ClientViewModel.h"

#include <QStringList>
#include <type_traits>
#include <utility>

namespace rm27::presentation {
namespace {

const QString missing = QStringLiteral("—");

template<class T> QString number(const std::optional<T> &value)
{
    if (!value) return missing;
    if constexpr (std::is_same_v<T, bool>) {
        return *value ? QStringLiteral("是") : QStringLiteral("否");
    } else if constexpr (std::is_floating_point_v<T>) {
        return QString::number(*value, 'g', 9);
    } else if constexpr (std::is_signed_v<T>) {
        return QString::number(static_cast<qlonglong>(*value));
    } else {
        return QString::number(static_cast<qulonglong>(*value));
    }
}

template<class T> QString status(const domain::BasicSample<T> &sample)
{
    if (!sample.value) return QStringLiteral("未收到");
    return sample.stale ? QStringLiteral("已过期") : QStringLiteral("已收到");
}

template<class T> const T *fresh(const domain::BasicSample<T> &sample)
{
    return sample.value && !sample.stale ? &*sample.value : nullptr;
}

template<class T> QString unavailable(const domain::BasicSample<T> &sample)
{
    return sample.stale ? QStringLiteral("数据已过期，等待新的报文。")
                        : QStringLiteral("尚未收到本会话的数据。缺失值显示为 —。");
}

QString roleName(std::optional<domain::RobotRole> role)
{
    if (!role) return QStringLiteral("未知角色");
    switch (*role) {
    case domain::RobotRole::Heavy: return QStringLiteral("重装");
    case domain::RobotRole::Reserved: return QStringLiteral("保留编号");
    case domain::RobotRole::Infantry: return QStringLiteral("步兵");
    case domain::RobotRole::Aerial: return QStringLiteral("空中");
    case domain::RobotRole::Sentry: return QStringLiteral("哨兵");
    case domain::RobotRole::Dart: return QStringLiteral("飞镖");
    case domain::RobotRole::Radar: return QStringLiteral("雷达");
    case domain::RobotRole::Base: return QStringLiteral("基地");
    case domain::RobotRole::Outpost: return QStringLiteral("前哨站");
    }
    return QStringLiteral("未知角色");
}

QString enumeration(const std::optional<std::uint32_t> &value, const QStringList &names)
{
    if (!value) return missing;
    return *value < static_cast<std::uint32_t>(names.size())
        ? names.at(static_cast<int>(*value))
        : QStringLiteral("未知值 %1").arg(*value);
}

template<class T, std::size_t N>
QString formattedSlots(const std::vector<T> &values, const std::array<int, N> &ids)
{
    if (values.empty()) return missing;
    QStringList parts;
    for (std::size_t i = 0; i < values.size() && i < ids.size(); ++i) {
        parts.append(QStringLiteral("%1: %2").arg(ids[i]).arg(number(std::optional<T>(values[i]))));
    }
    return parts.join(QStringLiteral("  ·  "));
}

template<class T> QVariantMap topicEntry(const QString &topic, const domain::BasicSample<T> &sample)
{
    return {{QStringLiteral("topic"), topic}, {QStringLiteral("state"), status(sample)},
            {QStringLiteral("received"), sample.value.has_value()},
            {QStringLiteral("stale"), sample.stale},
            {QStringLiteral("receivedAtMs"), static_cast<qlonglong>(sample.receivedAtMs)}};
}

} // namespace

ClientViewModel::ClientViewModel(application::ClientSession &session,
                               std::optional<domain::RunMode> mode,
                               QString startupError, QString logPath, QObject *parent)
    : QObject(parent), session_(session), mode_(mode),
      startupError_(std::move(startupError)), logPath_(std::move(logPath))
{
    connect(&session_, &application::ClientSession::stateChanged,
            this, &ClientViewModel::stateChanged);
    connect(&session_, &application::ClientSession::snapshotChanged,
            this, &ClientViewModel::snapshotChanged);
    connect(&session_, &application::ClientSession::basicStateChanged,
            this, &ClientViewModel::basicStateChanged);
    connect(&session_, &application::ClientSession::diagnosticChanged,
            this, &ClientViewModel::diagnosticChanged);
    connect(&session_, &application::ClientSession::identityChanged,
            this, &ClientViewModel::identityChanged);
    connect(&session_, &application::ClientSession::actionFeedbackChanged,
            this, &ClientViewModel::actionFeedbackChanged);
}

QString ClientViewModel::modeText() const
{
    if (!mode_) return QStringLiteral("未确定（配置错误）");
    switch (*mode_) {
    case domain::RunMode::Official: return QStringLiteral("官方接入 · 设备未验证");
    case domain::RunMode::Simulation: return QStringLiteral("外部模拟器 · MQTT");
    case domain::RunMode::Preview: return QStringLiteral("内置心跳预览");
    }
    return QStringLiteral("未知模式");
}

QString ClientViewModel::connectionText() const
{
    switch (session_.connectionState()) {
    case domain::ConnectionState::Disconnected: return QStringLiteral("已停止");
    case domain::ConnectionState::Connecting: return QStringLiteral("连接中");
    case domain::ConnectionState::Subscribing: return QStringLiteral("Broker 已连接 · 正在订阅");
    case domain::ConnectionState::Connected:
        return preview() ? QStringLiteral("预览运行中") : QStringLiteral("五类订阅就绪");
    case domain::ConnectionState::RetryWaiting: return QStringLiteral("等待重连");
    case domain::ConnectionState::Unavailable: return QStringLiteral("连接不可用");
    }
    return QStringLiteral("未知状态");
}

QString ClientViewModel::connectionDetail() const { return session_.connectionDetail(); }
bool ClientViewModel::active() const { return session_.active(); }
bool ClientViewModel::canStart() const { return mode_.has_value() && !active(); }
bool ClientViewModel::hasSnapshot() const { return session_.hasSnapshot(); }
bool ClientViewModel::preview() const { return mode_ == domain::RunMode::Preview; }
QString ClientViewModel::sourceText() const
{
    return mode_ ? session_.sourceDescription() : QStringLiteral("连接配置未加载");
}
QString ClientViewModel::seatText() const
{
    if (!mode_ || preview()) return {};
    return infantrySeat() ? QStringLiteral("本地席位 · 步兵（只读）")
                          : QStringLiteral("本地席位 · 未指定（只读）");
}

bool ClientViewModel::infantrySeat() const
{
    return mode_.has_value() && !preview() && session_.seat() == domain::OperatorSeat::Infantry;
}

QVariantList ClientViewModel::receiverChoices() const
{
    QVariantList choices;
    for (const int id : domain::mqttRobotIds) {
        const auto identity = domain::identifyRobot(id).value();
        const QString team = identity.team == domain::Team::Red ? QStringLiteral("红方") : QStringLiteral("蓝方");
        const QString label = QStringLiteral("%1 · ID %2 · %3").arg(team).arg(id).arg(roleName(identity.role));
        choices.append(QVariantMap{{"id", id}, {"label", label}});
    }
    return choices;
}

void ClientViewModel::setPersonalConfigEditor(QString path, std::function<QString(int)> save)
{
    personalConfigPath_ = std::move(path);
    saveConfig_ = std::move(save);
    emit personalConfigPathChanged();
}

void ClientViewModel::saveInfantryConfig(int robotId)
{
    if (active()) {
        configFeedback_ = QStringLiteral("请先停止数据源，再保存接收配置。");
    } else if (!saveConfig_) {
        configFeedback_ = QStringLiteral("请通过 --config 打开个人接收配置。");
    } else {
        const auto error = saveConfig_(robotId);
        configFeedback_ = error.isEmpty()
            ? QStringLiteral("已保存步兵只读配置。下次连接使用 clientID %1。").arg(robotId)
            : QStringLiteral("保存失败，仍使用 clientID %1。\n%2").arg(configuredRobotId()).arg(error);
    }
    emit configFeedbackChanged();
}

QString ClientViewModel::actionFeedback() const { return session_.actionFeedback(); }
QString ClientViewModel::diagnosticText() const { return session_.diagnostic(); }

QString ClientViewModel::sequenceText() const
{
    return hasSnapshot() ? QString::number(session_.snapshot().sequence) : missing;
}

QString ClientViewModel::elapsedText() const
{
    return hasSnapshot() ? QStringLiteral("%1 s").arg(session_.snapshot().elapsedSeconds) : missing;
}

QString ClientViewModel::healthText() const
{
    const auto *value = fresh(session_.basicState().robotDynamic);
    return value ? number(value->current_health) : missing;
}

QString ClientViewModel::dynamicStatusText() const
{
    return status(session_.basicState().robotDynamic);
}

QString ClientViewModel::dynamicSummary() const
{
    const auto &sample = session_.basicState().robotDynamic;
    const auto *value = fresh(sample);
    if (!value) return unavailable(sample);
    return QStringLiteral("热量 %1  ·  剩余允许发弹量 %2\n"
                          "上次弹丸射速 %3  ·  缓冲能量 %4\n"
                          "当前经验 %5  ·  距下级仍需 %6  ·  累计发弹 %7\n"
                          "脱战 %8  ·  脱战倒计时原值 %9（单位待确认）\n"
                          "可远程回血 %10  ·  可远程补弹 %11")
        .arg(number(value->current_heat), number(value->remaining_ammo),
             number(value->last_projectile_fire_rate), number(value->current_buffer_energy),
             number(value->current_experience), number(value->experience_for_upgrade),
             number(value->total_projectiles_fired), number(value->is_out_of_combat),
             number(value->out_of_combat_countdown))
        .arg(number(value->can_remote_heal), number(value->can_remote_ammo));
}

QString ClientViewModel::robotIdentityText() const
{
    const auto *value = fresh(session_.basicState().robotStatic);
    if (!value) return missing;
    return QStringLiteral("ID %1 · %2").arg(number(value->robot_id), roleName(value->role()));
}

QString ClientViewModel::staticSummary() const
{
    const auto &sample = session_.basicState().robotStatic;
    const auto *value = fresh(sample);
    if (!value) return unavailable(sample);
    return QStringLiteral("机器人连接 %1  ·  在场 %2  ·  存活 %3\n"
                          "血量上限 %4  ·  等级 %5  ·  类型原值 %6\n"
                          "热量上限 %7  ·  每秒冷却 %8\n"
                          "最大功率 %9  ·  最大缓冲能量 %10  ·  最大底盘能量 %11\n"
                          "发射性能 %12  ·  底盘性能 %13")
        .arg(enumeration(value->connection_state, {QStringLiteral("未连接"), QStringLiteral("连接")}),
             enumeration(value->field_state, {QStringLiteral("上场"), QStringLiteral("未上场")}),
             enumeration(value->alive_state, {QStringLiteral("未知"), QStringLiteral("存活"), QStringLiteral("战亡")}),
             number(value->max_health), number(value->level), number(value->robot_type),
             number(value->max_heat), number(value->heat_cooldown_rate), number(value->max_power))
        .arg(number(value->max_buffer_energy), number(value->max_chassis_energy),
             enumeration(value->performance_system_shooter, {QStringLiteral("未知值 0"), QStringLiteral("冷却"), QStringLiteral("爆发")}),
             enumeration(value->performance_system_chassis, {QStringLiteral("未知值 0"), QStringLiteral("血量"), QStringLiteral("功率")}));
}

QString ClientViewModel::gameText() const
{
    const auto *value = fresh(session_.basicState().game);
    if (!value) return missing;
    return enumeration(value->current_stage,
        {QStringLiteral("未开始"), QStringLiteral("准备阶段"), QStringLiteral("十五秒自检"),
         QStringLiteral("五秒倒计时"), QStringLiteral("比赛阶段"), QStringLiteral("结算阶段")});
}

QString ClientViewModel::gameSummary() const
{
    const auto &sample = session_.basicState().game;
    const auto *value = fresh(sample);
    if (!value) return unavailable(sample);
    QString summary = QStringLiteral("局号 %1 / %2  ·  比分 红 %3 : 蓝 %4\n"
                                     "剩余 %5 秒  ·  已过 %6 秒  ·  暂停 %7")
        .arg(number(value->current_round), number(value->total_rounds), number(value->red_score),
             number(value->blue_score), number(value->stage_countdown_sec),
             number(value->stage_elapsed_sec), number(value->is_paused));
    if (value->current_stage == 5) {
        summary += QStringLiteral("\n结果 %1  ·  结束原因 %2")
            .arg(enumeration(value->game_result, {QStringLiteral("平局"), QStringLiteral("红方胜"), QStringLiteral("蓝方胜")}),
                 enumeration(value->end_reason, {QStringLiteral("未知值 0"), QStringLiteral("基地"), QStringLiteral("控制度"),
                   QStringLiteral("总攻击伤害"), QStringLiteral("总剩余血量"), QStringLiteral("平局"),
                   QStringLiteral("异常终止"), QStringLiteral("主裁判判定")}));
    } else {
        summary += QStringLiteral("\n结算结果仅在收到结算阶段时展示；时间与比分按报文显示。");
    }
    return summary;
}

QString ClientViewModel::economyText() const
{
    const auto *value = fresh(session_.basicState().logistics);
    return value ? number(value->remaining_economy) : missing;
}

QString ClientViewModel::logisticsSummary() const
{
    const auto &sample = session_.basicState().logistics;
    const auto *value = fresh(sample);
    if (!value) return unavailable(sample);
    return QStringLiteral("累计经济 %1\n重装成功最高装配难度 %2  ·  雷达加密等级 %3")
        .arg(number(value->total_economy_obtained), number(value->tech_level), number(value->encryption_level));
}

QString ClientViewModel::unitsSummary() const
{
    const auto &sample = session_.basicState().units;
    const auto *value = fresh(sample);
    if (!value) return unavailable(sample);
    const auto identity = domain::identifyRobot(static_cast<std::uint32_t>(session_.robotId()));
    if (!identity) return QStringLiteral("配置身份未知，无法确定己敌数组归属。");
    const bool blue = identity->team == domain::Team::Blue;
    return QStringLiteral("己方基地 %1  ·  敌方基地 %2\n固定 R 前哨 %3  ·  固定 B 前哨 %4\n"
                          "机器人 ID: 血量（前四项己方，后四项敌方）\n%5\n"
                          "己方 ID: 剩余累计发弹量（P-002 六槽；2/102 为保留槽）\n%6\n"
                          "总伤害 己 %7 / 敌 %8  ·  累计控制度 己 %9 / 敌 %10")
        .arg(number(value->base_health), number(value->enemy_base_health),
             number(value->outpost_R_health), number(value->outpost_B_health),
             formattedSlots(value->robot_health, domain::healthRobotIds(blue)),
             formattedSlots(value->robot_bullets, domain::bulletRobotIds(blue)),
             number(value->total_damage_ally), number(value->total_damage_enemy),
             number(value->total_CP_ally))
        .arg(number(value->total_CP_enemy));
}

QVariantList ClientViewModel::topicStates() const
{
    const auto &state = session_.basicState();
    return {topicEntry(QStringLiteral("GameStatus"), state.game),
            topicEntry(QStringLiteral("GlobalUnitStatus"), state.units),
            topicEntry(QStringLiteral("GlobalLogisticsStatus"), state.logistics),
            topicEntry(QStringLiteral("RobotStaticStatus"), state.robotStatic),
            topicEntry(QStringLiteral("RobotDynamicStatus"), state.robotDynamic)};
}

QVariantMap ClientViewModel::basicEvidence() const
{
    return {{QStringLiteral("mode"), modeText()}, {QStringLiteral("source"), sourceText()},
            {QStringLiteral("connection"), connectionText()}, {QStringLiteral("active"), active()},
            {QStringLiteral("health"), healthText()}, {QStringLiteral("dynamic"), dynamicSummary()},
            {QStringLiteral("identity"), robotIdentityText()}, {QStringLiteral("static"), staticSummary()},
            {QStringLiteral("game"), gameText()}, {QStringLiteral("gameSummary"), gameSummary()},
            {QStringLiteral("economy"), economyText()}, {QStringLiteral("logistics"), logisticsSummary()},
            {QStringLiteral("units"), unitsSummary()}, {QStringLiteral("topics"), topicStates()},
            {QStringLiteral("diagnostic"), diagnosticText()}};
}

QString ClientViewModel::startupError() const { return startupError_; }
QString ClientViewModel::logPath() const { return logPath_; }

void ClientViewModel::start()
{
    if (canStart()) session_.start();
}

void ClientViewModel::stop() { session_.stop(); }

void ClientViewModel::requestBusinessAction() { session_.requestBusinessAction(); }

} // namespace rm27::presentation
