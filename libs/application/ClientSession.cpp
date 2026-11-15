#include "ClientSession.h"
#include <type_traits>

namespace rm27::application {

ClientSession::ClientSession(IDataSource &source, QObject *parent)
    : QObject(parent), source_(source)
{
    qRegisterMetaType<domain::ClientSnapshot>();
    qRegisterMetaType<domain::ConnectionState>();
    qRegisterMetaType<domain::BasicMessage>();
    freshnessTimer_.setInterval(250);
    connect(&freshnessTimer_, &QTimer::timeout, this, &ClientSession::refreshFreshness);
    connect(&source_, &IDataSource::basicMessageReceived,
            this, &ClientSession::acceptBasicMessage);
    connect(&source_, &IDataSource::diagnosticReceived, this, [this](const QString &detail) {
        if (active_) setDiagnostic(detail);
    });

    connect(&source_, &IDataSource::connectionChanged, this,
            [this](domain::ConnectionState state, const QString &detail) {
        if (!active_) {
            return;
        }
        connectionState_ = state;
        connectionDetail_ = detail;
        if (state == domain::ConnectionState::RetryWaiting) {
            // The operator's session stays active, but the failed connection's
            // identity, data and packet diagnostics do not cross to its successor.
            clearSessionData();
        } else if (state == domain::ConnectionState::Unavailable
            || state == domain::ConnectionState::Disconnected) {
            active_ = false;
            freshnessTimer_.stop();
            clearSessionData();
        } else if (state == domain::ConnectionState::Connecting) {
            setActionFeedback({});
        }
        emit stateChanged();
    });
    connect(&source_, &IDataSource::snapshotReceived, this,
            [this](const domain::ClientSnapshot &snapshot) {
        if (!active_ || connectionState_ != domain::ConnectionState::Connected) {
            return;
        }
        snapshot_ = snapshot;
        hasSnapshot_ = true;
        emit snapshotChanged();
    });
}

ClientSession::~ClientSession()
{
    stop();
}

void ClientSession::start()
{
    if (active_) {
        return;
    }
    const auto generation = ++startGeneration_;
    receiveClock_.start();
    freshnessTimer_.start();
    active_ = true;
    connectionState_ = domain::ConnectionState::Connecting;
    connectionDetail_ = QStringLiteral("正在启动数据源……");
    clearSessionData();
    emit stateChanged();
    // A direct signal handler can stop or replace this start before it returns.
    if (active_ && generation == startGeneration_) source_.start();
}

void ClientSession::stop()
{
    if (!active_ && connectionState_ == domain::ConnectionState::Disconnected
        && !hasSnapshot_) {
        setActionFeedback({});
        return;
    }

    // 先关闭接收入口，避免 stop() 期间的数据回写。
    active_ = false;
    freshnessTimer_.stop();
    connectionState_ = domain::ConnectionState::Disconnected;
    connectionDetail_ = QStringLiteral("数据源已停止。");
    source_.stop();
    clearSessionData();
    emit stateChanged();
}

void ClientSession::clearSessionData()
{
    // Finish every state change before notifying synchronous observers.
    const bool notifySnapshot = hasSnapshot_;
    const bool notifyDiagnostic = !diagnostic_.isEmpty();
    const bool notifyAction = !actionFeedback_.isEmpty();
    hasSnapshot_ = false;
    snapshot_ = {};
    basicState_ = {};
    diagnostic_.clear();
    actionFeedback_.clear();
    emit basicStateChanged();
    if (notifySnapshot) emit snapshotChanged();
    if (notifyDiagnostic) emit diagnosticChanged();
    if (notifyAction) emit actionFeedbackChanged();
}

void ClientSession::configureIdentity(int robotId, const QString &description, domain::OperatorSeat seat)
{
    if (active_) return;
    if (robotId_ == robotId && sourceDescription_ == description && seat_ == seat) return;
    robotId_ = robotId;
    sourceDescription_ = description;
    seat_ = seat;
    setActionFeedback({});
    emit identityChanged();
}

bool ClientSession::requestBusinessAction()
{
    // Evaluate the seat even while disconnected. A denied intent has no payload
    // or pending work that could cross a stop, identity change or reconnection.
    setActionFeedback(seat_ == domain::OperatorSeat::Infantry
        ? QStringLiteral("步兵席只读，请在官方操作端执行赛事操作。")
        : QStringLiteral("尚未指定操作席位，当前只允许接收数据。"));
    return false;
}

void ClientSession::setActionFeedback(const QString &detail)
{
    if (actionFeedback_ == detail) return;
    actionFeedback_ = detail;
    emit actionFeedbackChanged();
}

void ClientSession::setDiagnostic(const QString &detail)
{
    if (diagnostic_ == detail) return;
    diagnostic_ = detail;
    emit diagnosticChanged();
}

void ClientSession::acceptBasicMessage(const domain::BasicMessage &message, qint64 ageMs)
{
    if (!active_ || connectionState_ != domain::ConnectionState::Connected) return;
    ageMs = qMax<qint64>(0, ageMs);
    const auto now = receiveClock_.elapsed() - ageMs;
    const auto &identity = basicState_.robotStatic;
    const bool identityReady = identity.value && !identity.stale
        && receiveClock_.elapsed() - identity.receivedAtMs < 3000
        && identity.value->robot_id == static_cast<std::uint32_t>(robotId_);
    std::visit([&](const auto &data) {
        using T = std::decay_t<decltype(data)>;
        const qint64 threshold = std::is_same_v<T, domain::GameData>
            || std::is_same_v<T, domain::RobotDynamicData> ? 1000 : 3000;
        const auto save = [&](auto &sample) { sample = {data, ageMs >= threshold, now}; };
        if constexpr (std::is_same_v<T, domain::GameData>) {
            save(basicState_.game);
        } else if constexpr (std::is_same_v<T, domain::RobotStaticData>) {
            // Dynamic/global messages have no robot ID. Bind them only after a
            // matching static identity in this session, never infer identity from HP.
            if (data.robot_id != static_cast<std::uint32_t>(robotId_)) {
                basicState_.units = {};
                basicState_.logistics = {};
                basicState_.robotDynamic = {};
                basicState_.robotStatic = {};
                setDiagnostic(QStringLiteral("静态身份未提供或不匹配：配置机器人 %1，收到 %2；等待身份一致的数据。")
                    .arg(robotId_).arg(data.robot_id ? QString::number(*data.robot_id) : QStringLiteral("未提供")));
            } else {
                save(basicState_.robotStatic);
                if (diagnostic_.startsWith(QStringLiteral("静态身份"))) setDiagnostic({});
            }
        } else if (identityReady) {
            if constexpr (std::is_same_v<T, domain::GlobalUnitData>) save(basicState_.units);
            if constexpr (std::is_same_v<T, domain::LogisticsData>) save(basicState_.logistics);
            if constexpr (std::is_same_v<T, domain::RobotDynamicData>) save(basicState_.robotDynamic);
        }
    }, message);
    emit basicStateChanged();
}

void ClientSession::refreshFreshness()
{
    if (!active_) return;
    const auto now = receiveClock_.elapsed();
    bool changed = false;
    const auto refresh = [&](auto &sample, qint64 timeout) {
        const bool stale = sample.value && now - sample.receivedAtMs >= timeout;
        if (stale != sample.stale) { sample.stale = stale; changed = true; }
    };
    // Engineering diagnostics: 1s for 5/10Hz, 3s for 1Hz. These are not rules.
    refresh(basicState_.game, 1000);
    refresh(basicState_.units, 3000);
    refresh(basicState_.logistics, 3000);
    refresh(basicState_.robotStatic, 3000);
    refresh(basicState_.robotDynamic, 1000);
    if (changed) emit basicStateChanged();
}

} // namespace rm27::application
