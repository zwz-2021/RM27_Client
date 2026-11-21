#include "LinkDiagnostics.h"

#include "application/ClientSession.h"
#include "video/UdpVideoStatus.h"
#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QSaveFile>
#include <cmath>

namespace rm27::client {
namespace {

QString connectionName(domain::ConnectionState state)
{
    switch (state) {
    case domain::ConnectionState::Disconnected: return QStringLiteral("disconnected");
    case domain::ConnectionState::Connecting: return QStringLiteral("connecting");
    case domain::ConnectionState::Subscribing: return QStringLiteral("subscribing");
    case domain::ConnectionState::Connected: return QStringLiteral("connected");
    case domain::ConnectionState::RetryWaiting: return QStringLiteral("retry_waiting");
    case domain::ConnectionState::Unavailable: return QStringLiteral("unavailable");
    }
    return QStringLiteral("unavailable");
}

QString udpStateName(video::UdpVideoState state)
{
    switch (state) {
    case video::UdpVideoState::Stopped: return QStringLiteral("stopped");
    case video::UdpVideoState::Bound: return QStringLiteral("bound");
    case video::UdpVideoState::BindFailed: return QStringLiteral("bind_failed");
    case video::UdpVideoState::ReadFailed: return QStringLiteral("read_failed");
    }
    return QStringLiteral("not_available");
}

QString modeName(std::optional<domain::RunMode> mode)
{
    if (!mode) return QStringLiteral("unavailable");
    switch (*mode) {
    case domain::RunMode::Official: return QStringLiteral("official");
    case domain::RunMode::Simulation: return QStringLiteral("simulation");
    case domain::RunMode::Preview: return QStringLiteral("preview");
    }
    return QStringLiteral("unavailable");
}

QJsonValue count(quint64 value, bool available = true)
{
    // JSON consumers often parse numbers as IEEE754 doubles. Decimal strings
    // preserve all 64 bits, including on a long running receiver.
    return available ? QJsonValue(QString::number(value)) : QJsonValue(QJsonValue::Null);
}

template<class T> QJsonObject sampleState(const domain::BasicSample<T> &sample)
{
    return {{"received", sample.value.has_value()},
            {"stale", sample.value ? QJsonValue(sample.stale) : QJsonValue(QJsonValue::Null)}};
}

QJsonObject decodeFields(const QJsonObject &input)
{
    QJsonObject result;
    const QStringList states{"not_available", "stopped", "waiting", "playing", "stale", "error"};
    const QString state = input.value("state").toString();
    result.insert("state", states.contains(state) ? state : QStringLiteral("not_available"));
    const QStringList phases{"idle", "waiting_for_picture", "decoding"};
    const QString phase = input.value("phase").toString();
    result.insert("phase", phases.contains(phase) ? QJsonValue(phase) : QJsonValue(QJsonValue::Null));
    for (const auto &key : {"decoded_frames_total", "decoded_frames_last_second",
                           "presented_frames_last_second", "dropped_frames_total", "other_source_frames_total"}) {
        const auto value = input.value(QLatin1String(key));
        const auto digits = value.toString();
        bool valid = value.isString() && !digits.isEmpty() && digits.size() <= 20;
        for (const auto ch : digits) valid = valid && ch >= u'0' && ch <= u'9';
        bool inRange = false;
        if (valid) digits.toULongLong(&inRange);
        result.insert(QLatin1String(key), valid && inRange ? value : QJsonValue(QJsonValue::Null));
    }
    for (const auto &key : {"pending_frames", "pending_bytes", "width", "height"}) {
        const auto value = input.value(QLatin1String(key));
        const double number = value.toDouble(-1);
        result.insert(QLatin1String(key), value.isDouble() && std::isfinite(number)
            && number >= 0 && number <= 2147483647 && std::floor(number) == number
                ? value : QJsonValue(QJsonValue::Null));
    }
    for (const auto &key : {"has_frame", "frame_stale", "sink_attached", "error_present", "diagnostic_present"}) {
        const auto value = input.value(QLatin1String(key));
        result.insert(QLatin1String(key), value.isBool() ? value : QJsonValue(QJsonValue::Null));
    }
    return result;
}

} // namespace

QJsonObject captureLinkDiagnostics(const application::ClientSession &session,
    std::optional<domain::RunMode> mode, const video::UdpVideoStatus &udp,
    const QJsonObject &decode)
{
    const auto sampled = QDateTime::currentDateTime();
    const bool mqttAvailable = mode && *mode != domain::RunMode::Preview;
    const bool udpAvailable = mqttAvailable && session.seat() == domain::OperatorSeat::Infantry;
    const bool bound = udpAvailable && udp.state == video::UdpVideoState::Bound;
    const bool assemblyAvailable = udpAvailable && mode == domain::RunMode::Simulation;
    const auto &samples = session.basicState();
    const auto &stats = udp.assembly;
    const QJsonObject topics{
        {"GameStatus", sampleState(samples.game)},
        {"GlobalUnitStatus", sampleState(samples.units)},
        {"GlobalLogisticsStatus", sampleState(samples.logistics)},
        {"RobotStaticStatus", sampleState(samples.robotStatic)},
        {"RobotDynamicStatus", sampleState(samples.robotDynamic)},
        {"RobotModuleStatus", sampleState(samples.robotModule)}
    };
    const QJsonObject header = udp.lastHeader ? QJsonObject{
        {"frame_id", udp.lastHeader->frameId}, {"fragment_index", udp.lastHeader->fragmentIndex},
        {"frame_bytes", static_cast<qint64>(udp.lastHeader->frameBytes)}} : QJsonObject{};
    const QJsonObject frame = udp.lastFrame ? QJsonObject{
        {"frame_id", udp.lastFrame->frameId}, {"bytes", static_cast<qint64>(udp.lastFrame->bytes)}} : QJsonObject{};
    return {
        {"schema_version", 1},
        {"sampled_at_local", sampled.toOffsetFromUtc(sampled.offsetFromUtc()).toString(Qt::ISODateWithMs)},
        {"sampled_at_utc", sampled.toUTC().toString(Qt::ISODateWithMs)},
        {"semantics", QJsonObject{
            {"scope", "single_local_status_snapshot"},
            {"sampling", "owner-thread capture; decoder status is a thread-safe sample, not an atomic cross-thread event"},
            {"clock", "local wall clock for sample time; local monotonic clocks for ages and rates"},
            {"rate_window_ms", 1000},
            {"rate_window", "events in the preceding 1000 ms; events aged 1000 ms are excluded"},
            {"counts", "unsigned 64-bit counts use decimal strings; session counters reset on stop/start"},
            {"units", "packet counts, frame counts, bytes, milliseconds, pixel dimensions"},
            {"null", "not received or unavailable; see state and received fields; zero is a measured count"},
            {"mqtt_samples", "accepted samples in this session; stale uses the existing local freshness policy"},
            {"presentation", "first delivery of a new valid frame to the video sink; not screen refresh or end-to-end latency"},
            {"contents", "status only; no images, payloads, addresses, identity IDs, paths or free text errors"}}},
        {"session", QJsonObject{{"active", session.active()}, {"mode", modeName(mode)},
            {"seat", session.seat() == domain::OperatorSeat::Infantry ? "infantry" : "unspecified"}}},
        {"mqtt", QJsonObject{
            {"state", mqttAvailable ? connectionName(session.connectionState()) : QStringLiteral("not_available")},
            {"diagnostic_present", mqttAvailable && !session.diagnostic().isEmpty()}, {"topics", topics}}},
        {"udp", QJsonObject{
            {"state", udpAvailable ? udpStateName(udp.state) : QStringLiteral("not_available")},
            {"error_present", udpAvailable && !udp.error.isEmpty()},
            {"valid_packets_total", count(udp.validPackets, udpAvailable)},
            {"valid_packets_last_second", count(udp.validPacketsLastSecond, bound)},
            {"short_packets_total", count(udp.shortPackets, udpAvailable)},
            {"oversized_packets_total", count(udp.oversizedPackets, udpAvailable)},
            {"empty_payload_packets_total", count(udp.emptyPayloadPackets, udpAvailable)},
            {"inconsistent_frame_packets_total", count(udp.inconsistentFramePackets, udpAvailable)},
            {"last_valid_packet_age_ms", udpAvailable && udp.lastValidPacketAt.isValid()
                ? QJsonValue(udp.lastValidPacketAt.elapsed()) : QJsonValue(QJsonValue::Null)},
            {"last_packet_bytes", udpAvailable && udp.lastHeader ? QJsonValue(udp.lastPacketBytes) : QJsonValue(QJsonValue::Null)},
            {"last_header", udpAvailable && udp.lastHeader ? QJsonValue(header) : QJsonValue(QJsonValue::Null)}}},
        {"assembly", QJsonObject{
            {"state", assemblyAvailable ? udpStateName(udp.state) : QStringLiteral("not_available")},
            {"completed_frames_total", count(stats.completedFrames, assemblyAvailable)},
            {"completed_frames_last_second", count(udp.completedFramesLastSecond, assemblyAvailable && bound)},
            {"timeout_frames_total", count(stats.timeoutFrames, assemblyAvailable)},
            {"conflict_frames_total", count(stats.conflictFrames, assemblyAvailable)},
            {"limit_frames_total", count(stats.limitFrames, assemblyAvailable)},
            {"duplicate_fragments_total", count(stats.duplicateFragments, assemblyAvailable)},
            {"ignored_late_fragments_total", count(stats.ignoredLateFragments, assemblyAvailable)},
            {"pending_frames", assemblyAvailable ? QJsonValue(stats.pendingFrames) : QJsonValue(QJsonValue::Null)},
            {"buffered_bytes", assemblyAvailable ? QJsonValue(stats.bufferedBytes) : QJsonValue(QJsonValue::Null)},
            {"buffered_fragments", assemblyAvailable ? QJsonValue(stats.bufferedFragments) : QJsonValue(QJsonValue::Null)},
            {"last_frame", assemblyAvailable && udp.lastFrame ? QJsonValue(frame) : QJsonValue(QJsonValue::Null)}}},
        {"decode", decodeFields(assemblyAvailable ? decode : QJsonObject{})}
    };
}

SnapshotSaveResult saveLinkDiagnostics(const QString &path, const QJsonObject &snapshot)
{
    const auto target = QFileInfo(path).absoluteFilePath();
    const auto failure = [&](const QString &error) { return SnapshotSaveResult{false, target, error}; };
    const auto contents = QJsonDocument(snapshot).toJson(QJsonDocument::Indented);
    if (contents.size() > MaxLinkSnapshotBytes)
        return failure(QStringLiteral("快照超过 32 KiB 上限，未写入。"));
    if (path.isEmpty() || !QDir().mkpath(QFileInfo(target).absolutePath()))
        return failure(QStringLiteral("无法创建快照目录，请检查路径和写入权限。"));
    QSaveFile file(target);
    file.setDirectWriteFallback(false);
    if (!file.open(QIODevice::WriteOnly))
        return failure(QStringLiteral("无法打开快照文件：%1").arg(file.errorString()));
    if (file.write(contents) != contents.size()) {
        const auto error = file.errorString();
        file.cancelWriting();
        return failure(QStringLiteral("无法完整写入快照：%1").arg(error));
    }
    if (!file.commit())
        return failure(QStringLiteral("无法保存快照，原文件保持不变：%1").arg(file.errorString()));
    return {true, target, {}};
}

} // namespace rm27::client
