#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QtTest>

class ClientUiTest : public QObject {
    Q_OBJECT

private slots:
    void startupWindow_data()
    {
        QTest::addColumn<QString>("mode");
        QTest::addColumn<QString>("error");
        QTest::newRow("official") << QStringLiteral("正式") << QString{};
        QTest::newRow("simulation") << QStringLiteral("模拟") << QString{};
        QTest::newRow("configuration-error") << QStringLiteral("未确定（配置错误）")
                                            << QStringLiteral("D:/配置/missing.json\n无法读取配置");
    }

    void startupWindow()
    {
        QFETCH(QString, mode);
        QFETCH(QString, error);
        QQmlApplicationEngine engine;
        engine.setInitialProperties({{"modeText", mode}, {"startupError", error}});
        engine.load(QUrl(QStringLiteral("qrc:/RM27/Client/Main.qml")));
        QCOMPARE(engine.rootObjects().size(), 1);
        QObject *root = engine.rootObjects().first();
        auto *window = qobject_cast<QQuickWindow *>(root);
        QVERIFY(window);
        QVERIFY(window->isVisible());
        auto *modeLabel = root->findChild<QObject *>("modeLabel");
        auto *connectionLabel = root->findChild<QObject *>("connectionLabel");
        auto *replayButton = root->findChild<QObject *>("replayButton");
        auto *errorLabel = root->findChild<QObject *>("startupErrorLabel");
        QVERIFY(modeLabel && connectionLabel && replayButton && errorLabel);
        QVERIFY(modeLabel->property("text").toString().contains(mode));
        QCOMPARE(connectionLabel->property("text").toString(), QStringLiteral("未连接"));
        QVERIFY(!replayButton->property("enabled").toBool());
        QCOMPARE(errorLabel->property("visible").toBool(), !error.isEmpty());
        if (!error.isEmpty()) {
            QVERIFY(errorLabel->property("text").toString().contains(error));
        }
        window->close();
    }
};

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    ClientUiTest test;
    return QTest::qExec(&test, argc, argv);
}

#include "test_client_ui.moc"

