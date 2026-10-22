#include "config/AppConfig.h"
#include "diagnostics/JsonlLogger.h"

#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>
#include <QtTest>

class StartupTest : public QObject {
    Q_OBJECT

private slots:
    void configuration_data()
    {
        QTest::addColumn<QByteArray>("json");
        QTest::addColumn<bool>("valid");
        QTest::addColumn<QString>("expected");
        QTest::newRow("official") << QByteArray(R"({"mode":"official"})") << true << "official";
        QTest::newRow("simulation") << QByteArray(R"({"mode":"simulation"})") << true << "simulation";
        QTest::newRow("broken-json") << QByteArray("{") << false << QStringLiteral("JSON");
        QTest::newRow("root-array") << QByteArray("[]") << false << QStringLiteral("根节点");
        QTest::newRow("missing-mode") << QByteArray("{}") << false << QStringLiteral("mode");
        QTest::newRow("wrong-type") << QByteArray(R"({"mode":1})") << false << QStringLiteral("mode");
        QTest::newRow("unsupported-replay") << QByteArray(R"({"mode":"replay"})") << false << QStringLiteral("mode");
        QTest::newRow("unknown-field") << QByteArray(R"({"mode":"official","server":"unused"})")
                                      << false << QStringLiteral("server");
    }

    void configuration()
    {
        QFETCH(QByteArray, json);
        QFETCH(bool, valid);
        QFETCH(QString, expected);
        QTemporaryDir directory(QDir::tempPath() + QStringLiteral("/RM27 配置 测试-XXXXXX"));
        QVERIFY(directory.isValid());
        const QString path = directory.filePath(QStringLiteral("config.json"));
        QFile file(path);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QCOMPARE(file.write(json), qint64(json.size()));
        file.close();

        const auto result = rm27::config::loadConfig(path);
        QCOMPARE(result.config.has_value(), valid);
        if (valid) {
            QVERIFY(result.error.isEmpty());
            const auto expectedMode = expected == "official"
                ? rm27::domain::RunMode::Official : rm27::domain::RunMode::Simulation;
            QCOMPARE(result.config->mode, expectedMode);
        } else {
            QVERIFY(result.error.contains(path));
            QVERIFY(result.error.contains(expected));
        }
    }

    void missingConfiguration()
    {
        QTemporaryDir directory;
        const QString path = directory.filePath("missing.json");
        const auto result = rm27::config::loadConfig(path);
        QVERIFY(!result.config);
        QVERIFY(result.error.contains(path));
        QVERIFY(!result.error.isEmpty());
    }

    void logWritesJsonLines()
    {
        QTemporaryDir directory;
        const QString path = directory.filePath("logs/client.jsonl");
        rm27::diagnostics::JsonlLogger logger;
        QVERIFY(logger.open(path));
        QVERIFY(logger.write("info", "client.start", QStringLiteral("正式\n未连接")));
        QVERIFY(logger.write("info", "client.stop"));
        QFile file(path);
        QVERIFY(file.open(QIODevice::ReadOnly));
        const auto first = QJsonDocument::fromJson(file.readLine()).object();
        QCOMPARE(first.value("event").toString(), QStringLiteral("client.start"));
        QCOMPARE(first.value("detail").toString(), QStringLiteral("正式\n未连接"));
        QVERIFY(!first.value("timestamp").toString().isEmpty());
        QCOMPARE(QJsonDocument::fromJson(file.readLine()).object().value("event").toString(),
                 QStringLiteral("client.stop"));
        QVERIFY(file.atEnd());
    }

    void logOpenFailureIsVisible()
    {
        QTemporaryDir directory;
        rm27::diagnostics::JsonlLogger logger;
        QVERIFY(!logger.open(directory.path()));
        QVERIFY(logger.errorString().contains(directory.path()));
    }
};

QTEST_GUILESS_MAIN(StartupTest)
#include "test_startup.moc"

