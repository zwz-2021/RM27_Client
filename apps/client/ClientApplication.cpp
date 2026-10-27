#include "ClientApplication.h"

#include "application/ClientSession.h"
#include "config/AppConfig.h"
#include "diagnostics/JsonlLogger.h"
#include "presentation/ClientViewModel.h"
#include "transport/MockDataSource.h"
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
    if (result.config && settings.mode == domain::RunMode::Simulation) {
        source = std::make_unique<transport::MockDataSource>(settings.simulation.intervalMs);
    } else {
        source = std::make_unique<transport::UnavailableDataSource>();
    }
    application::ClientSession session(*source);
    QObject::connect(&session, &application::ClientSession::stateChanged, &session, [&] {
        if (logOpen && !logger.write(QStringLiteral("info"), QStringLiteral("session.state"),
                                     session.connectionDetail())) {
            qWarning().noquote() << logger.errorString();
        }
    });
    presentation::ClientViewModel viewModel(session,
        result.config ? std::optional<domain::RunMode>(settings.mode) : std::nullopt,
        startupError, logPath);

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
