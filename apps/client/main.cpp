#include "config/AppConfig.h"
#include "diagnostics/JsonlLogger.h"

#include <QCommandLineParser>
#include <QDebug>
#include <QDir>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickStyle>

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    app.setOrganizationName(QStringLiteral("RM27"));
    app.setApplicationName(QStringLiteral("RM27_Client"));
    app.setApplicationVersion(QStringLiteral("0.1.0"));
    QQuickStyle::setStyle(QStringLiteral("Basic")); //设置QML控件风格

    // 创建命令行解析器，解析启动exe时后面带的--help，--version等参数
    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("RM27 Client / T06 skeleton")); //设置帮助信息中的程序说明
    parser.addHelpOption();
    parser.addVersionOption();
    const QCommandLineOption configOption(QStringLiteral("config"),
        QStringLiteral("JSON configuration file"), QStringLiteral("path"),
        QStringLiteral(":/RM27/Client/defaults.json"));
    parser.addOption(configOption);
    parser.process(app);

    // 加载传入的配置
    const auto result = rm27::config::loadConfig(parser.value(configOption));
    QString startupError = result.error;
    const QString modeText = !result.config ? QStringLiteral("未确定（配置错误）")
        : result.config->mode == rm27::domain::RunMode::Official
            ? QStringLiteral("正式") : QStringLiteral("模拟");

    // 打开日志，并记录启动
    const QString logPath = QDir(QStringLiteral(RM27_PROJECT_ROOT))
                                .filePath(QStringLiteral("logs/client.jsonl"));
    rm27::diagnostics::JsonlLogger logger;
    if (!logger.open(logPath)
        || !logger.write(result.config ? QStringLiteral("info") : QStringLiteral("error"),
                         QStringLiteral("client.start"), modeText + " " + result.error)) {
        if (!startupError.isEmpty()) {
            startupError += '\n';
        }
        startupError += logger.errorString();
    }

    // 创建QML引擎
    QQmlApplicationEngine engine;
    engine.setInitialProperties({{"modeText", modeText}, {"startupError", startupError},
                                 {"logPath", logPath}});
    engine.load(QUrl(QStringLiteral("qrc:/RM27/Client/Main.qml")));
    if (engine.rootObjects().isEmpty()) {
        logger.write(QStringLiteral("error"), QStringLiteral("client.qml_failed"));
        return 1;
    }
    // 注册退出前执行的代码，信号和槽，[&logger]表示最后的匿名函数引用外部创建好的logger，只有收到信号是才执行里面的写日志的代码
    QObject::connect(&app, &QCoreApplication::aboutToQuit, [&logger] {
        if (!logger.write(QStringLiteral("info"), QStringLiteral("client.stop"))) {
            qWarning().noquote() << logger.errorString();
        }
    });
    // 进入事件循环
    return app.exec();
}

