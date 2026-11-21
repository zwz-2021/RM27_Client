#include "LinkDiagnostics.h"
#include "application/ClientSession.h"
#include "presentation/ClientViewModel.h"
#include "video/UdpVideoStatus.h"

#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QTemporaryDir>
#include <iostream>
#include <limits>
#include <stdexcept>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif

using namespace rm27;

namespace {

void require(bool ok, const char *message)
{
    if (!ok) throw std::runtime_error(message);
}

class Source final : public application::IDataSource {
public:
    void start() override {}
    void stop() override {}
};

QByteArray get(const QString &path)
{
    QFile file(path);
    require(file.open(QIODevice::ReadOnly), "read saved snapshot");
    return file.readAll();
}

QJsonObject child(const QJsonObject &root, const char *name)
{
    return root.value(QLatin1String(name)).toObject();
}

void checkCapture()
{
    Source source;
    application::ClientSession session(source);
    session.configureIdentity(3, "private-host.example:3333 secret=do-not-export", domain::OperatorSeat::Infantry);
    video::UdpVideoStatus udp;
    auto capture = [&] { return client::captureLinkDiagnostics(session, domain::RunMode::Simulation, udp, {}); };
    auto snapshot = capture();
    require(snapshot.value("schema_version").toInt() == 1 && snapshot.size() == 9, "schema version or top-level contract");
    const auto local = QDateTime::fromString(snapshot.value("sampled_at_local").toString(), Qt::ISODateWithMs);
    const auto utc = QDateTime::fromString(snapshot.value("sampled_at_utc").toString(), Qt::ISODateWithMs);
    require(local.isValid() && utc.isValid() && local.toMSecsSinceEpoch() == utc.toMSecsSinceEpoch(),
            "sample timestamps disagree");
    require(snapshot.value("sampled_at_utc").toString().endsWith('Z'), "UTC timestamp not explicit");
    require(child(snapshot, "udp").value("state") == "stopped"
        && child(snapshot, "udp").value("valid_packets_last_second").isNull()
        && child(snapshot, "udp").value("last_valid_packet_age_ms").isNull()
        && child(snapshot, "assembly").value("completed_frames_last_second").isNull(), "stopped or missing data look measured");
    const auto missing = child(child(snapshot, "mqtt"), "topics");
    require(missing.size() == 6, "MQTT topic set");
    for (auto it = missing.begin(); it != missing.end(); ++it)
        require(!it.value().toObject().value("received").toBool() && it.value().toObject().value("stale").isNull(), "missing MQTT sample");
    require(child(snapshot, "decode").value("state") == "not_available"
        && child(snapshot, "decode").value("has_frame").isNull(), "no decoder represented as measured output");

    session.start();
    udp.state = video::UdpVideoState::Bound;
    snapshot = capture();
    require(child(snapshot, "mqtt").value("state") == "connecting"
        && child(snapshot, "session").value("active").toBool()
        && child(snapshot, "udp").value("valid_packets_last_second") == "0"
        && child(snapshot, "assembly").value("completed_frames_last_second") == "0", "bound no-data state");
    source.connectionChanged(domain::ConnectionState::Subscribing, "private connection detail");
    require(child(capture(), "mqtt").value("state") == "subscribing", "subscribing state lost");
    source.connectionChanged(domain::ConnectionState::Connected, "private connection detail");
    domain::RobotStaticData identity;
    identity.robot_id = 3;
    source.basicMessageReceived(identity);
    domain::RobotDynamicData dynamic;
    dynamic.current_health = 987654321;
    source.basicMessageReceived(dynamic, 1000);
    source.basicMessageReceived(domain::RobotModuleData{}, 3000);
    source.basicMessageReceived(domain::GameData{}, 0);
    source.diagnosticReceived("do-not-export-raw-diagnostic");
    udp.validPackets = std::numeric_limits<quint64>::max();
    udp.validPacketsLastSecond = 4;
    udp.shortPackets = 2;
    udp.completedFramesLastSecond = 1;
    udp.assembly.completedFrames = 12;
    udp.assembly.timeoutFrames = 1;
    udp.assembly.bufferedBytes = 1234;
    udp.bindAddress = "192.168.12.2";
    udp.bindPort = 3334;
    udp.lastSourceAddress = "192.168.12.1";
    udp.lastSourcePort = 44321;
    udp.lastValidPacketAt.start();
    udp.lastPacketBytes = 11;
    udp.lastHeader = video::UdpVideoHeader{65535, 2, 128};
    udp.lastFrame = video::UdpFrameInfo{65534, 1234, "private-sender", 5555};
    const QJsonObject decode{
        {"state", "playing"}, {"phase", "decoding"}, {"decoded_frames_total", "18446744073709551615"},
        {"decoded_frames_last_second", "3"}, {"presented_frames_last_second", "2"},
        {"dropped_frames_total", "1"}, {"other_source_frames_total", "0"},
        {"pending_frames", 2}, {"pending_bytes", 1234}, {"width", 1920}, {"height", 1080},
        {"has_frame", true}, {"frame_stale", false}, {"sink_attached", true},
        {"error_present", false}, {"diagnostic_present", true},
        {"private_key", "do-not-export-private-key"}, {"error", "C:/private/file.mp4"}};
    snapshot = client::captureLinkDiagnostics(session, domain::RunMode::Simulation, udp, decode);
    const auto mqtt = child(snapshot, "mqtt");
    const auto topics = child(mqtt, "topics");
    require(mqtt.value("state") == "connected" && mqtt.value("diagnostic_present").toBool()
        && child(topics, "RobotDynamicStatus").value("received").toBool()
        && child(topics, "RobotDynamicStatus").value("stale").toBool()
        && child(topics, "RobotModuleStatus").value("received").toBool()
        && child(topics, "RobotModuleStatus").value("stale").toBool()
        && !child(topics, "GameStatus").value("stale").toBool(), "MQTT accepted/stale state lost");
    const auto wire = child(snapshot, "udp");
    require(wire.value("valid_packets_total") == "18446744073709551615"
        && wire.value("valid_packets_last_second") == "4" && wire.value("short_packets_total") == "2"
        && wire.value("last_valid_packet_age_ms").toInteger(-1) >= 0
        && child(wire, "last_header").value("frame_id").toInt() == 65535, "UDP counts or packet metadata");
    const auto assembly = child(snapshot, "assembly");
    require(assembly.value("completed_frames_total") == "12"
        && assembly.value("completed_frames_last_second") == "1"
        && assembly.value("buffered_bytes").toInt() == 1234
        && child(assembly, "last_frame").value("bytes").toInt() == 1234, "assembly counts");
    auto decoded = child(snapshot, "decode");
    require(decoded.size() == 16 && decoded.value("state") == "playing"
        && decoded.value("decoded_frames_total") == "18446744073709551615"
        && decoded.value("width").toInt() == 1920 && decoded.value("presented_frames_last_second") == "2",
        "decode whitelist or counts");
    const auto bytes = QJsonDocument(snapshot).toJson();
    for (const auto secret : {"private-host", "do-not-export", "192.168.12", "44321", "private-sender", "C:/private", "987654321"})
        require(!bytes.contains(secret), "private configuration, payload or free-text escaped whitelist");
    require(bytes.size() < client::MaxLinkSnapshotBytes, "normal snapshot exceeds file budget");

    // Active official reception has no local simulation assembly/decoding contract.
    const auto official = client::captureLinkDiagnostics(session, domain::RunMode::Official, udp, decode);
    require(child(official, "udp").value("state") == "bound"
        && child(official, "assembly").value("state") == "not_available"
        && child(official, "assembly").value("completed_frames_total").isNull()
        && child(official, "decode").value("decoded_frames_total").isNull(), "official source falsely claims simulation decode");
    for (const auto mode : {std::optional<domain::RunMode>{domain::RunMode::Preview}, std::optional<domain::RunMode>{}}) {
        const auto unavailable = client::captureLinkDiagnostics(session, mode, udp, decode);
        require(child(unavailable, "mqtt").value("state") == "not_available"
            && child(unavailable, "udp").value("valid_packets_total").isNull()
            && child(unavailable, "decode").value("state") == "not_available", "unavailable source marked live");
    }
    // No decode string or nested value can become a free-text export channel.
    const auto invalidDecode = client::captureLinkDiagnostics(session, domain::RunMode::Simulation, udp,
        {{"state", "secret"}, {"phase", "secret"}, {"decoded_frames_total", "secret"},
         {"pending_bytes", "secret"}, {"error_present", QJsonObject{{"private", "secret"}}}});
    require(!QJsonDocument(invalidDecode).toJson().contains("secret"), "invalid decode values escaped schema");

    for (const auto state : {video::UdpVideoState::BindFailed, video::UdpVideoState::ReadFailed}) {
        udp.state = state;
        udp.error = "private-path-and-socket-address";
        const auto failed = capture();
        require(child(failed, "udp").value("error_present").toBool()
            && child(failed, "udp").value("valid_packets_last_second").isNull()
            && child(failed, "assembly").value("completed_frames_last_second").isNull()
            && !QJsonDocument(failed).toJson().contains("private-path"), "UDP failure absent or leaked detail");
    }
    source.connectionChanged(domain::ConnectionState::RetryWaiting, "retry detail");
    require(child(capture(), "mqtt").value("state") == "retry_waiting"
        && !child(child(child(capture(), "mqtt"), "topics"), "RobotDynamicStatus").value("received").toBool(),
        "retry retained stale connection data");
    source.connectionChanged(domain::ConnectionState::Unavailable, "unavailable detail");
    require(child(capture(), "mqtt").value("state") == "unavailable", "unavailable MQTT state");
    session.stop();
    udp = {};
    require(!child(capture(), "session").value("active").toBool()
        && child(capture(), "udp").value("valid_packets_total") == "0", "stop reset");
    session.start();
    udp.state = video::UdpVideoState::Bound;
    require(child(capture(), "udp").value("valid_packets_last_second") == "0"
        && child(capture(), "udp").value("last_header").isNull(), "restart retained old UDP state");
    session.stop();
    session.configureIdentity(1, "private", domain::OperatorSeat::Unspecified);
    require(child(capture(), "udp").value("state") == "not_available", "unconfigured seat claims UDP");
}

void checkSave()
{
    QTemporaryDir directory;
    require(directory.isValid(), "temporary directory");
    const auto path = directory.filePath(QStringLiteral("中文 目录/link-snapshot.json"));
    const QJsonObject first{{"schema_version", 1}, {"sequence", 1}};
    const auto saved = client::saveLinkDiagnostics(path, first);
    require(saved.success && saved.path == path && saved.error.isEmpty(), "initial save in Unicode directory");
    QJsonParseError parseError;
    require(QJsonDocument::fromJson(get(path), &parseError).object() == first
        && parseError.error == QJsonParseError::NoError, "invalid saved JSON");
    const QJsonObject second{{"schema_version", 1}, {"sequence", 2}};
    require(client::saveLinkDiagnostics(path, second).success
        && QJsonDocument::fromJson(get(path)).object() == second, "replace existing snapshot");
    const auto good = get(path);
    const auto tooLarge = client::saveLinkDiagnostics(path,
        {{"too_large", QString(client::MaxLinkSnapshotBytes, QChar('x'))}});
    require(!tooLarge.success && !tooLarge.error.isEmpty() && get(path) == good, "oversized snapshot altered previous file");
    const auto noDirectory = client::saveLinkDiagnostics(path + "/child.json", first);
    require(!noDirectory.success && !noDirectory.error.isEmpty() && get(path) == good, "file used as parent directory");
    const auto directoryTarget = client::saveLinkDiagnostics(directory.path(), first);
    require(!directoryTarget.success && !directoryTarget.error.isEmpty(), "directory used as file");
    require(!client::saveLinkDiagnostics({}, first).success, "empty destination accepted");
#ifdef Q_OS_WIN
    // Keep the existing snapshot readable while denying atomic replacement.
    HANDLE held = CreateFileW(reinterpret_cast<LPCWSTR>(path.utf16()), GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    require(held != INVALID_HANDLE_VALUE, "hold snapshot without delete sharing");
    const auto blocked = client::saveLinkDiagnostics(path, first);
    CloseHandle(held);
    require(!blocked.success && !blocked.error.isEmpty() && get(path) == good, "failed atomic replacement damaged old snapshot");
#endif
    require(client::saveLinkDiagnostics(path, first).success
        && QJsonDocument::fromJson(get(path)).object() == first, "retry after failure");
    const auto files = QDir(QFileInfo(path).absolutePath()).entryList(QDir::Files | QDir::Hidden | QDir::System);
    require(files == QStringList{QStringLiteral("link-snapshot.json")}, "repeated/failed saves accumulated files");
}

void checkRepeatedRequests()
{
    Source source;
    application::ClientSession session(source);
    presentation::ClientViewModel view(session, domain::RunMode::Simulation, {}, {});
    int calls = 0;
    view.setDiagnosticSnapshotSaver([&] { ++calls; });
    view.saveDiagnosticSnapshot();
    require(view.snapshotSaving() && calls == 1, "first save request not started");
    view.saveDiagnosticSnapshot();
    view.saveDiagnosticSnapshot();
    require(view.snapshotSaving() && calls == 1, "busy save queued duplicate work");
    view.finishDiagnosticSnapshotSave(true, "saved");
    require(!view.snapshotSaving() && !view.snapshotSaveFeedback().isEmpty(), "success did not finish request");
    view.saveDiagnosticSnapshot();
    require(view.snapshotSaving() && calls == 2, "success prevented another save");
    view.finishDiagnosticSnapshotSave(false, "failure");
    require(!view.snapshotSaving() && !view.snapshotSaveFeedback().isEmpty(), "failure left request busy");
    view.saveDiagnosticSnapshot();
    require(view.snapshotSaving() && calls == 3, "failure prevented retry");
    view.finishDiagnosticSnapshotSave(true, "saved after failure");
}

} // namespace

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    try {
        checkCapture();
        checkSave();
        checkRepeatedRequests();
        std::cout << "PASS: typed snapshot states, private-data whitelist, 64-bit counts, bounded atomic save and failure recovery\n";
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
