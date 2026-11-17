#include "ClientApplication.h"
#include "SimulationVideoDecode.h"

#include "application/ClientSession.h"
#include "config/AppConfig.h"
#include "diagnostics/JsonlLogger.h"
#include "presentation/ClientViewModel.h"
#include "transport/MockDataSource.h"
#include "transport/MqttDataSource.h"
#include "transport/UdpVideoReceiver.h"
#include "transport/UnavailableDataSource.h"

#include <QCommandLineParser>
#include <QDateTime>
#include <QDebug>
#include <QDir>
#include <QFileInfo>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickStyle>
#include <QStandardPaths>
#include <memory>

namespace rm27::client {
namespace {

QString logDirectory(const QCommandLineParser &parser, const config::AppConfig &settings,
                     const QString &configPath)
{
    // 命令行相对路径基于当前工作目录；配置中的相对路径基于配置文件目录。
    if (parser.isSet(QStringLiteral("log-dir"))) {
        return QDir(parser.value(QStringLiteral("log-dir"))).absolutePath();
    }
    if (!settings.logging.directory.isEmpty()) {
        const QDir base = configPath.startsWith(":/")
            ? QDir::current() : QFileInfo(configPath).absoluteDir();
        return QDir::cleanPath(base.absoluteFilePath(settings.logging.directory));
    }
    return QDir(QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation))
        .filePath(QStringLiteral("logs"));
}

void appendError(QString &errors, const QString &message)
{
    if (!errors.isEmpty()) {
        errors += '\n';
    }
    errors += message;
}

void configureIdentity(application::ClientSession &session, const config::AppConfig &settings)
{
    const auto &mqtt = settings.mqtt;
    const QString source = settings.mode == domain::RunMode::Preview
        ? QStringLiteral("内置演示心跳（不连接 MQTT）")
        : QStringLiteral("MQTT %1:%2 · 连接机器人 clientID %3 · 终端 IP 由系统配置")
              .arg(mqtt.host).arg(mqtt.port).arg(mqtt.robotId);
    session.configureIdentity(mqtt.robotId, source, settings.seat);
}

} // namespace

int ClientApplication::run(QGuiApplication &app)
{
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("RM27 Client development skeleton"));
    parser.addHelpOption();
    parser.addVersionOption();
    parser.addOption({QStringLiteral("config"), QStringLiteral("JSON configuration file"),
                      QStringLiteral("path"), QStringLiteral(":/RM27/Client/defaults.json")});
    parser.addOption({QStringLiteral("log-dir"), QStringLiteral("Override log directory"),
                      QStringLiteral("path")});
    parser.addOption({QStringLiteral("trace-simulated-video"),
                      QStringLiteral("Log pixel hashes for the first 32 decoded frames of each local simulation session")});
    parser.process(app);

    const QString configPath = parser.value(QStringLiteral("config"));
    const auto result = config::loadConfig(configPath);
    // 读取失败时只使用默认窗口尺寸显示错误，不启动任何数据源。
    const config::AppConfig settings = result.config.value_or(config::AppConfig{});
    QString startupError = result.error;
    const QString fileName = QStringLiteral("client-%1-%2.jsonl")
        .arg(QDateTime::currentDateTimeUtc().toString(QStringLiteral("yyyyMMdd-HHmmss-zzz")))
        .arg(QCoreApplication::applicationPid());
    const QString logPath = QDir(logDirectory(parser, settings, configPath)).filePath(fileName);
    diagnostics::JsonlLogger logger;
    const bool logOpen = logger.open(logPath);
    if (!logOpen) {
        appendError(startupError, logger.errorString());
    } else if (!logger.write(result.config ? QStringLiteral("info") : QStringLiteral("error"),
                             QStringLiteral("client.start"), result.error)) {
        appendError(startupError, logger.errorString());
    }

    // 对象按声明顺序构建、逆序销毁：数据源比会话活得更久，QML 最先销毁。
    std::unique_ptr<application::IDataSource> source;
    if (result.config && settings.mode == domain::RunMode::Preview) {
        source = std::make_unique<transport::MockDataSource>(settings.simulation.intervalMs);
    } else if (result.config) {
        source = std::make_unique<transport::MqttDataSource>(settings.mqtt.host,
            settings.mqtt.port, settings.mqtt.robotId, settings.mqtt.connectTimeoutMs);
    } else {
        source = std::make_unique<transport::UnavailableDataSource>();
    }
    transport::UdpVideoReceiver udp;
    application::ClientSession session(*source);
    if (result.config) configureIdentity(session, settings);
    QObject::connect(&session, &application::ClientSession::stateChanged, &session, [&] {
        if (logOpen && !logger.write(QStringLiteral("info"), QStringLiteral("session.state"),
                                     session.connectionDetail())) {
            qWarning().noquote() << logger.errorString();
        }
    });
    QObject::connect(&session, &application::ClientSession::diagnosticChanged, &session, [&] {
        if (logOpen && !logger.write(QStringLiteral("warning"), QStringLiteral("session.diagnostic"),
                                     session.diagnostic())) qWarning().noquote() << logger.errorString();
    });
    presentation::ClientViewModel viewModel(session,
        result.config ? std::optional<domain::RunMode>(settings.mode) : std::nullopt,
        startupError, logPath);
    const auto logVideo = [&](const QString &level, const QString &event, const QString &detail) {
        if (logOpen && !logger.write(level, event, detail)) qWarning().noquote() << logger.errorString();
    };
    using video::UdpVideoState;
    std::unique_ptr<SimulationVideoDecode> simulationDecode;
    // The active session checks the seat before binding UDP, including after personal config edits.
    if (result.config && settings.mode == domain::RunMode::Simulation) {
        simulationDecode = std::make_unique<SimulationVideoDecode>(udp, parser.isSet(QStringLiteral("trace-simulated-video")));
        QObject::connect(simulationDecode.get(), &SimulationVideoDecode::statusChanged,
                         &viewModel, &presentation::ClientViewModel::setVideoDecodeText);
        QObject::connect(simulationDecode.get(), &SimulationVideoDecode::logRecord, &viewModel, logVideo);
    }
    QObject::connect(&udp, &transport::UdpVideoReceiver::statusChanged, &viewModel, [&] {
        const auto &status = udp.status();
        viewModel.setUdpStatus(status);
        if (status.state == UdpVideoState::ReadFailed)
            logVideo(QStringLiteral("warning"), QStringLiteral("video.read_failed"), viewModel.udpBindingText());
    });
    // MQTT 重订阅仍属于同一次操作员会话；UDP 在每次会话开始时只绑定一次。
    QObject::connect(&session, &application::ClientSession::stateChanged, &viewModel, [&] {
        const auto &status = udp.status();
        if (session.active()) {
            if (session.seat() != domain::OperatorSeat::Infantry || settings.mode == domain::RunMode::Preview
                || status.state != UdpVideoState::Stopped) return;
            const bool bound = udp.start(settings.video.bindAddress, static_cast<quint16>(settings.video.port),
                                         settings.mode == domain::RunMode::Simulation);
            logVideo(bound ? QStringLiteral("info") : QStringLiteral("warning"),
                     bound ? QStringLiteral("video.bound") : QStringLiteral("video.bind_failed"),
                     viewModel.udpBindingText());
        } else if (status.state != UdpVideoState::Stopped) {
            if (settings.mode == domain::RunMode::Simulation && status.state != UdpVideoState::BindFailed) {
                // Capture the final counters even when stopping between batched UI notifications.
                viewModel.setUdpStatus(status);
                logVideo(QStringLiteral("info"), QStringLiteral("video.assembly_summary"),
                         viewModel.udpAssemblyText());
            }
            logVideo(QStringLiteral("info"), QStringLiteral("video.stopped"),
                     QStringLiteral("有效包 %1 · 丢弃 %2").arg(status.validPackets).arg(status.droppedPackets()));
            udp.stop();
        }
    });
    auto *mqttSource = qobject_cast<transport::MqttDataSource *>(source.get());
    if (mqttSource && config::isEditableConfigPath(configPath)) {
        viewModel.setPersonalConfigEditor(QFileInfo(configPath).absoluteFilePath(),
            [&, mqttSource, revision = result.revision](int robotId) mutable -> QString {
                const auto saved = config::saveInfantryConfig(configPath, robotId, revision);
                if (!saved.config) {
                    if (logOpen && !logger.write(QStringLiteral("warning"), QStringLiteral("config.save_failed"),
                                                  saved.error)) qWarning().noquote() << logger.errorString();
                    return saved.error;
                }
                revision = saved.revision;
                mqttSource->setRobotIdWhileStopped(robotId);
                configureIdentity(session, *saved.config);
                if (logOpen && !logger.write(QStringLiteral("info"), QStringLiteral("config.saved"),
                        QStringLiteral("步兵只读 · MQTT clientID %1").arg(robotId))) {
                    qWarning().noquote() << logger.errorString();
                }
                return {};
            });
    }

    qmlRegisterUncreatableType<presentation::ClientViewModel>(
        "RM27.Client", 1, 0, "ClientViewModel", QStringLiteral("由应用组合根创建"));
    QQmlApplicationEngine engine;
    QQmlEngine::setObjectOwnership(&viewModel, QQmlEngine::CppOwnership);
    engine.setInitialProperties({
        {QStringLiteral("viewModel"), QVariant::fromValue(&viewModel)},
        {QStringLiteral("title"), settings.window.title},
        {QStringLiteral("width"), settings.window.width},
        {QStringLiteral("height"), settings.window.height}
    });
    engine.load(QUrl(QStringLiteral("qrc:/RM27/Client/Main.qml")));
    if (engine.rootObjects().isEmpty()) {
        if (logOpen) {
            logger.write(QStringLiteral("error"), QStringLiteral("client.qml_failed"));
        }
        return 1;
    }

    QObject::connect(&app, &QCoreApplication::aboutToQuit,
                     &session, &application::ClientSession::stop);
    if (result.config) {
        session.start();
    }
    const int exitCode = app.exec();
    session.stop();
    if (logOpen && !logger.write(QStringLiteral("info"), QStringLiteral("client.stop"))) {
        qWarning().noquote() << logger.errorString();
    }
    return exitCode;
}

} // namespace rm27::client
