#include "MqttDataSource.h"

#include "protocol/BasicCodec.h"
#include <MQTTAsync.h>
#include <QHostAddress>
#include <QHostInfo>
#include <QThread>
#include <algorithm>
#include <array>
#include <chrono>
#include <cstring>
#include <deque>
#include <mutex>
#include <optional>
#include <utility>
#include <vector>

namespace rm27::transport {
namespace {
constexpr std::array<const char *, 5> topics{
    "GameStatus", "GlobalUnitStatus", "GlobalLogisticsStatus",
    "RobotStaticStatus", "RobotDynamicStatus"};
// Engineering bounds, not official message lengths. Four latest-value slots,
// eight ordered static identity barriers and one diagnostic slot are bounded;
// there is no Qt per-packet event queue.
constexpr int maximumPayload = 1024 * 1024;
constexpr std::size_t maximumStaticBarriers = 8;
// Local retry policy, measured from the end of each failed attempt.
constexpr int initialRetryMs = 500;
constexpr int maximumRetryMs = 4000;

QString codeText(int code)
{
    const char *text = MQTTAsync_strerror(code);
    return QStringLiteral("%1 (%2)").arg(code).arg(QString::fromUtf8(text ? text : "unknown"));
}
}

struct MqttDataSource::Context {
    struct Subscription { Context *owner; std::size_t index; };
    struct Pending {
        QByteArray payload;
        quint64 arrival;
        std::chrono::steady_clock::time_point receivedAt;
    };
    std::mutex mutex;
    bool accepting = true;
    bool connected = false;
    std::array<bool, 5> accepted{};
    std::array<std::optional<Pending>, 5> latest;
    std::deque<Pending> staticBarriers;
    quint64 arrival = 0;
    std::array<Subscription, 5> subscriptions;
    QString failure;
    QString diagnostic;

    Context()
    {
        for (std::size_t i = 0; i < topics.size(); ++i) subscriptions[i] = {this, i};
    }

    static void connectedCallback(void *data, MQTTAsync_successData *)
    {
        auto &self = *static_cast<Context *>(data);
        std::lock_guard lock(self.mutex);
        if (self.accepting) self.connected = true;
    }
    static void connectFailed(void *data, MQTTAsync_failureData *response)
    {
        auto &self = *static_cast<Context *>(data);
        std::lock_guard lock(self.mutex);
        if (self.accepting && self.failure.isEmpty()) self.failure = QStringLiteral("MQTT 连接失败：%1")
            .arg(codeText(response ? response->code : MQTTASYNC_FAILURE));
    }
    static void connectionLost(void *data, char *)
    {
        auto &self = *static_cast<Context *>(data);
        std::lock_guard lock(self.mutex);
        if (self.accepting && self.failure.isEmpty()) self.failure = QStringLiteral("MQTT 连接已断开。");
    }
    static void subscribed(void *data, MQTTAsync_successData *response)
    {
        auto &subscription = *static_cast<Subscription *>(data);
        auto &self = *subscription.owner;
        std::lock_guard lock(self.mutex);
        if (!self.accepting || !self.failure.isEmpty()) return;
        const int qos = response ? response->alt.qos : 128;
        if (qos >= 0 && qos <= 1) {
            self.accepted[subscription.index] = true;
        } else {
            self.failure = QStringLiteral("订阅被拒绝或 QoS 超过 1：%1（返回 %2）")
                .arg(QString::fromLatin1(topics[subscription.index])).arg(qos);
        }
    }
    static void subscribeFailed(void *data, MQTTAsync_failureData *response)
    {
        auto &subscription = *static_cast<Subscription *>(data);
        auto &self = *subscription.owner;
        std::lock_guard lock(self.mutex);
        if (!self.accepting || !self.failure.isEmpty()) return;
        const QString topic = QString::fromLatin1(topics[subscription.index]);
        const int code = response ? response->code : MQTTASYNC_FAILURE;
        // Paho 1.3.15 reports a refused MQTT 3.1.1 SUBACK via onFailure.
        if (code == MQTT_BAD_SUBSCRIBE) {
            self.failure = QStringLiteral("Broker 拒绝订阅 %1（SUBACK 0x80）。").arg(topic);
        } else {
            self.failure = QStringLiteral("订阅失败：%1，%2").arg(topic, codeText(code));
        }
    }
    static int messageArrived(void *data, char *name, int nameLength, MQTTAsync_message *message)
    {
        auto &self = *static_cast<Context *>(data);
        {
            std::lock_guard lock(self.mutex);
            if (self.accepting && self.failure.isEmpty()) {
                // Respect an explicit topic length (embedded NULs must not match).
                const int length = nameLength > 0 ? nameLength : static_cast<int>(std::strlen(name));
                std::optional<std::size_t> index;
                for (std::size_t i = 0; i < topics.size(); ++i) {
                    if (length == static_cast<int>(std::strlen(topics[i]))
                        && std::memcmp(name, topics[i], length) == 0) index = i;
                }
                if (!index) {
                    self.diagnostic = QStringLiteral("已丢弃不在本轮五类订阅中的 Topic。");
                } else if (message->retained) {
                    self.diagnostic = QStringLiteral("已忽略 %1 的保留报文，等待本次连接后的实时数据。")
                        .arg(QString::fromLatin1(topics[*index]));
                } else if (message->qos < 0 || message->qos > 1
                           || message->payloadlen < 0 || message->payloadlen > maximumPayload) {
                    self.diagnostic = QStringLiteral("已丢弃 %1：QoS 或负载长度超出接收边界。")
                        .arg(QString::fromLatin1(topics[*index]));
                } else {
                    Pending pending{
                        QByteArray(static_cast<const char *>(message->payload), message->payloadlen),
                        ++self.arrival, std::chrono::steady_clock::now()};
                    if (*index == 3) {
                        // Static identity is an ordering barrier. Coalescing A ->
                        // B -> A could otherwise assign B's ID-less data to A.
                        if (self.staticBarriers.size() >= maximumStaticBarriers) {
                            self.failure = QStringLiteral("静态身份报文积压超过接收上限，已丢弃本次连接的数据。");
                        } else self.staticBarriers.push_back(std::move(pending));
                    } else self.latest[*index] = std::move(pending);
                }
            }
        }
        // Returning success consumes even rejected packets, avoiding retry loops.
        MQTTAsync_freeMessage(&message);
        MQTTAsync_free(name);
        return 1;
    }
};

MqttDataSource::MqttDataSource(QString host, int port, int robotId, int connectTimeoutMs,
                             QObject *parent)
    : IDataSource(parent), host_(std::move(host)), port_(port), robotId_(robotId),
      timeoutMs_(connectTimeoutMs), poll_(this), retryTimer_(this)
{
    poll_.setInterval(20);
    connect(&poll_, &QTimer::timeout, this, &MqttDataSource::drain);
    retryTimer_.setSingleShot(true);
    retryTimer_.setTimerType(Qt::PreciseTimer);
    connect(&retryTimer_, &QTimer::timeout, this, &MqttDataSource::beginAttempt);
}

MqttDataSource::~MqttDataSource() { releaseAttempt(); }

void MqttDataSource::setRobotIdWhileStopped(int robotId)
{
    Q_ASSERT(QThread::currentThread() == thread() && !active_);
    if (!active_) robotId_ = robotId;
}

void MqttDataSource::start()
{
    Q_ASSERT(QThread::currentThread() == thread());
    if (active_) return;
    active_ = true;
    nextRetryMs_ = initialRetryMs;
    beginAttempt();
}

void MqttDataSource::beginAttempt()
{
    if (!active_ || context_) return;
    const auto generation = generation_;
    context_ = std::make_unique<Context>();
    phaseClock_.start();
    poll_.start();
    emit connectionChanged(domain::ConnectionState::Connecting,
        QStringLiteral("正在连接 MQTT %1:%2，clientID=%3……").arg(host_).arg(port_).arg(robotId_));
    if (!active_ || generation != generation_) return;
    QHostAddress address(host_);
    if (!address.isNull()) {
        connectAddress(address.toString());
    } else {
        // Paho's DNS lookup may block its own global lock. Resolve asynchronously
        // first so cancelling this phase never waits for OS DNS in destroy().
        lookupId_ = QHostInfo::lookupHost(host_, this, [this, generation](const QHostInfo &info) {
            if (!active_ || generation_ != generation) return;
            lookupId_ = -1;
            if (info.error() != QHostInfo::NoError || info.addresses().isEmpty()) {
                fail(QStringLiteral("MQTT 地址解析失败：%1").arg(info.errorString()));
                return;
            }
            QHostAddress address = info.addresses().first();
            for (const auto &candidate : info.addresses()) {
                if (candidate.protocol() == QAbstractSocket::IPv4Protocol) { address = candidate; break; }
            }
            connectAddress(address.toString());
        });
    }
}

void MqttDataSource::connectAddress(const QString &address)
{
    const QString host = address.contains(':') ? QStringLiteral("[%1]").arg(address) : address;
    const QByteArray uri = QStringLiteral("tcp://%1:%2").arg(host).arg(port_).toUtf8();
    const QByteArray id = QByteArray::number(robotId_);
    int result = MQTTAsync_create(&client_, uri.constData(), id.constData(), MQTTCLIENT_PERSISTENCE_NONE, nullptr);
    if (result == MQTTASYNC_SUCCESS) result = MQTTAsync_setCallbacks(client_, context_.get(),
        &Context::connectionLost, &Context::messageArrived, nullptr);
    if (result != MQTTASYNC_SUCCESS) {
        fail(QStringLiteral("无法创建 MQTT 接收器：%1").arg(codeText(result)));
        return;
    }
    MQTTAsync_connectOptions options = MQTTAsync_connectOptions_initializer;
    options.MQTTVersion = MQTTVERSION_3_1_1;
    options.cleansession = 1;
    options.keepAliveInterval = 10;
    options.connectTimeout = qMax(1, (timeoutMs_ + 999) / 1000);
    options.automaticReconnect = 0;
    options.onSuccess = &Context::connectedCallback;
    options.onFailure = &Context::connectFailed;
    options.context = context_.get();
    result = MQTTAsync_connect(client_, &options);
    if (result != MQTTASYNC_SUCCESS) fail(QStringLiteral("无法发起 MQTT 连接：%1").arg(codeText(result)));
}

void MqttDataSource::subscribe()
{
    const auto generation = generation_;
    subscribing_ = true;
    phaseClock_.restart();
    emit connectionChanged(domain::ConnectionState::Subscribing,
        QStringLiteral("MQTT 已连接，正在确认五类基础消息订阅……"));
    if (!active_ || generation != generation_) return;
    for (std::size_t i = 0; i < topics.size(); ++i) {
        MQTTAsync_responseOptions options = MQTTAsync_responseOptions_initializer;
        options.context = &context_->subscriptions[i];
        options.onSuccess = &Context::subscribed;
        options.onFailure = &Context::subscribeFailed;
        const int result = MQTTAsync_subscribe(client_, topics[i], 1, &options);
        if (result != MQTTASYNC_SUCCESS) {
            fail(QStringLiteral("无法发起订阅 %1：%2")
                .arg(QString::fromLatin1(topics[i]), codeText(result)));
            return;
        }
    }
}

void MqttDataSource::drain()
{
    if (!active_ || !context_) return;
    const auto generation = generation_;
    QString failure, diagnostic;
    bool connected = false, allAccepted = true;
    std::array<std::optional<Context::Pending>, 5> latest;
    std::deque<Context::Pending> staticBarriers;
    {
        std::lock_guard lock(context_->mutex);
        failure.swap(context_->failure);
        diagnostic.swap(context_->diagnostic);
        connected = context_->connected;
        for (bool accepted : context_->accepted) allAccepted = allAccepted && accepted;
        // Leave early arrivals in the bounded slots until every SUBACK succeeds.
        if (allAccepted) {
            latest.swap(context_->latest);
            staticBarriers.swap(context_->staticBarriers);
        }
    }
    if (!failure.isEmpty()) { fail(failure); return; }
    if (!diagnostic.isEmpty()) emit diagnosticReceived(diagnostic);
    if (!active_ || generation != generation_) return;
    if (connected && !subscribing_) { subscribe(); return; }
    if (!ready_ && allAccepted) {
        ready_ = true;
        nextRetryMs_ = initialRetryMs;
        emit connectionChanged(domain::ConnectionState::Connected,
            QStringLiteral("五类基础消息订阅就绪（QoS≤1）；收到报文后显示数据。"));
        if (!active_ || generation != generation_) return;
    }
    if (!ready_ && phaseClock_.elapsed() >= timeoutMs_) {
        fail(subscribing_ ? QStringLiteral("MQTT 订阅确认超时，请检查 Broker 权限。")
                          : QStringLiteral("MQTT 连接超时，请检查地址、端口及 Broker。"));
        return;
    }
    if (!ready_) return;
    // Preserve every static barrier as well as order across the remaining latest
    // values. An overwritten mismatching identity must still clear old data.
    std::vector<std::pair<std::size_t, Context::Pending>> packets;
    packets.reserve(4 + staticBarriers.size());
    for (std::size_t i = 0; i < latest.size(); ++i) {
        if (latest[i]) packets.emplace_back(i, std::move(*latest[i]));
    }
    for (auto &pending : staticBarriers) packets.emplace_back(3, std::move(pending));
    std::sort(packets.begin(), packets.end(), [](const auto &left, const auto &right) {
        return left.second.arrival < right.second.arrival;
    });
    for (const auto &[i, pending] : packets) {
        if (!active_ || generation != generation_) return;
        const auto decoded = protocol::decode(QString::fromLatin1(topics[i]), pending.payload);
        if (decoded.message) {
            const auto age = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - pending.receivedAt).count();
            emit basicMessageReceived(*decoded.message, static_cast<qint64>(age));
        }
        else emit diagnosticReceived(QStringLiteral("已丢弃 %1 坏包：%2")
            .arg(QString::fromLatin1(topics[i]), decoded.error));
    }
}

void MqttDataSource::releaseAttempt()
{
    ready_ = false;
    subscribing_ = false;
    ++generation_;
    poll_.stop();
    if (lookupId_ >= 0) { QHostInfo::abortHostLookup(lookupId_); lookupId_ = -1; }
    if (context_) {
        std::lock_guard lock(context_->mutex);
        context_->accepting = false;
        context_->latest = {};
        context_->staticBarriers.clear();
    }
    // No application mutex is held while joining Paho callbacks. destroy closes
    // the clean session, cancels outstanding operations and releases its socket.
    // Context remains alive until the library has finished all callbacks.
    if (client_) MQTTAsync_destroy(&client_);
    context_.reset();
    phaseClock_.invalidate();
}

void MqttDataSource::fail(const QString &detail)
{
    releaseAttempt();
    const int delay = nextRetryMs_;
    nextRetryMs_ = qMin(maximumRetryMs, delay * 2);
    // Arm first so a synchronous stop from a state observer can cancel it.
    retryTimer_.start(delay);
    emit connectionChanged(domain::ConnectionState::RetryWaiting,
        QStringLiteral("%1 %2 毫秒后自动重连，可点击“停止”取消。").arg(detail).arg(delay));
}

void MqttDataSource::stop()
{
    Q_ASSERT(QThread::currentThread() == thread());
    if (!active_) return;
    active_ = false;
    retryTimer_.stop();
    releaseAttempt();
    emit connectionChanged(domain::ConnectionState::Disconnected, QStringLiteral("MQTT 已停止，连接与接收数据已清理。"));
}

} // namespace rm27::transport
