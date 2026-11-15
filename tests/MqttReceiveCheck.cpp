// Test-only observer: uses the product transport/session/view model and actual QML.
// No test injection or control endpoint is compiled into RM27_Client.
#include "application/ClientSession.h"
#include "config/AppConfig.h"
#include "presentation/ClientViewModel.h"
#include "transport/MqttDataSource.h"
#include <QCommandLineParser>
#include <QElapsedTimer>
#include <QFile>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QKeyEvent>
#include <QQmlApplicationEngine>
#include <QQuickStyle>
#include <QQuickItem>
#include <QQuickWindow>
#include <QTest>
#include <QTimer>

using namespace rm27;
template<class T> QJsonValue number(const std::optional<T> &v)
{
    return v ? QJsonValue(QString::number(*v)) : QJsonValue(QJsonValue::Null);
}
template<class T> QJsonArray array(const std::vector<T> &values)
{
    QJsonArray result;
    for (const auto value : values) result.append(qint64(value));
    return result;
}

class WindowInputs : public QObject {
public:
    int presses = 0;
    int releases = 0;
    int moves = 0;
protected:
    bool eventFilter(QObject *, QEvent *event) override
    {
        if (event->type() == QEvent::MouseMove) ++moves;
        if (event->type() == QEvent::KeyPress || event->type() == QEvent::KeyRelease) {
            if (static_cast<QKeyEvent *>(event)->key() == Qt::Key_W) {
                if (event->type() == QEvent::KeyPress) ++presses;
                else ++releases;
            }
        }
        return false;
    }
};

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    QQuickStyle::setStyle("Basic");
    QCommandLineParser parser;
    parser.addHelpOption();
    for (const auto *name : {"config", "output", "control", "screenshot"})
        parser.addOption({QString::fromLatin1(name), QString::fromLatin1(name), "value"});
    parser.process(app);
    QFile output(parser.value("output"));
    if (!output.open(QIODevice::WriteOnly | QIODevice::Truncate)) return 2;
    const auto result = config::loadConfig(parser.value("config"));
    if (!result.config) { qCritical().noquote() << result.error; return 5; }
    const auto &settings = *result.config;
    const auto &mqtt = settings.mqtt;
    const int robotId = mqtt.robotId;
    transport::MqttDataSource source(mqtt.host, mqtt.port, robotId, mqtt.connectTimeoutMs);
    application::ClientSession session(source);
    session.configureIdentity(robotId, QStringLiteral("MQTT %1:%2 · clientID %3")
        .arg(mqtt.host).arg(mqtt.port).arg(robotId), settings.seat);
    presentation::ClientViewModel model(session, settings.mode, {}, {});
    qmlRegisterUncreatableType<presentation::ClientViewModel>("RM27.Client",1,0,"ClientViewModel","test composition");
    QQmlApplicationEngine engine;
    QQmlEngine::setObjectOwnership(&model, QQmlEngine::CppOwnership);
    engine.setInitialProperties({{"viewModel", QVariant::fromValue(&model)}, {"title", "RM27 MQTT receive check"}});
    engine.load(QUrl("qrc:/RM27/Client/Main.qml"));
    if (engine.rootObjects().isEmpty()) return 3;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
    if (!window) return 4;
    QWindow focusPeer;
    focusPeer.setTitle(QStringLiteral("RM27 focus check"));
    focusPeer.resize(160, 80);
    WindowInputs inputs;
    window->installEventFilter(&inputs);
    focusPeer.installEventFilter(&inputs);
    const auto click = [&](const char *name) {
        auto *item = window->findChild<QQuickItem *>(name);
        if (item && item->isEnabled() && item->isVisible()) {
            const auto center = item->mapToScene(item->boundingRect().center()).toPoint();
            QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, center);
        }
    };
    int commandSeq = 0;
    bool captured = false;
    QByteArray previous;
    QElapsedTimer clock;
    clock.start();
    QTimer tick;
    tick.setInterval(50);
    const auto observe = [&] {
        const auto &s = session.basicState();
        QJsonArray topics, stale;
        const auto topic = [&](const char *name, const auto &sample) {
            if (sample.value) topics.append(name);
            if (sample.stale) stale.append(name);
        };
        topic("GameStatus", s.game); topic("GlobalUnitStatus", s.units);
        topic("GlobalLogisticsStatus", s.logistics); topic("RobotStaticStatus", s.robotStatic);
        topic("RobotDynamicStatus", s.robotDynamic);
        QJsonObject row{{"commandSeq", commandSeq}, {"running", session.active()},
            {"connected", session.connectionState() == domain::ConnectionState::Connected
                || session.connectionState() == domain::ConnectionState::Subscribing},
            {"subscriptionsReady", session.connectionState() == domain::ConnectionState::Connected},
            {"retryWaiting", session.connectionState() == domain::ConnectionState::RetryWaiting},
            {"connectionDetail", session.connectionDetail()},
            {"error", (session.connectionState() == domain::ConnectionState::RetryWaiting
                    || session.connectionState() == domain::ConnectionState::Unavailable)
                ? session.connectionDetail() : session.diagnostic()}, {"robotId", robotId},
            {"receivedRobotId", s.robotStatic.value && s.robotStatic.value->robot_id
                ? QJsonValue(int(*s.robotStatic.value->robot_id)) : QJsonValue(QJsonValue::Null)},
            {"health", s.robotDynamic.value ? number(s.robotDynamic.value->current_health) : QJsonValue(QJsonValue::Null)},
            {"heat", s.robotDynamic.value ? number(s.robotDynamic.value->current_heat) : QJsonValue(QJsonValue::Null)},
            {"totalEconomy", s.logistics.value ? number(s.logistics.value->total_economy_obtained) : QJsonValue(QJsonValue::Null)},
            {"gameCountdown", s.game.value ? number(s.game.value->stage_countdown_sec) : QJsonValue(QJsonValue::Null)},
            {"paused", s.game.value && s.game.value->is_paused ? QJsonValue(*s.game.value->is_paused) : QJsonValue(QJsonValue::Null)},
            {"unitHealth", s.units.value ? array(s.units.value->robot_health) : QJsonArray()},
            {"unitBullets", s.units.value ? array(s.units.value->robot_bullets) : QJsonArray()},
            {"topics", topics}, {"staleTopics", stale}, {"qmlLoaded", true},
            {"windowFocused", QGuiApplication::focusWindow() == window},
            {"peerFocused", QGuiApplication::focusWindow() == &focusPeer},
            {"wPresses", inputs.presses}, {"wReleases", inputs.releases}, {"mouseMoves", inputs.moves},
            {"source", session.sourceDescription()}, {"ui", QJsonObject::fromVariantMap(model.basicEvidence())}};
        if (auto *health = window->findChild<QObject *>("healthValue"))
            row.insert("qmlHealth", health->property("text").toString());
        if (auto *connection = window->findChild<QObject *>("connectionValue"))
            row.insert("qmlConnection", connection->property("text").toString());
        if (auto *seat = window->findChild<QQuickItem *>("seatLabel"))
            row.insert("qmlSeat", seat->isVisible() ? seat->property("text").toString() : QString());
        if (auto *action = window->findChild<QQuickItem *>("competitionActionButton"))
            row.insert("actionAvailable", action->isVisible() && action->isEnabled());
        if (auto *label = window->findChild<QQuickItem *>("actionFeedbackLabel"))
            row.insert("qmlActionFeedback", label->isVisible() ? label->property("text").toString() : QString());
        if (!captured && parser.isSet("screenshot") && row.value("health").toString() == "321"
            && !s.robotDynamic.stale) {
            const auto grab = window->grabWindow();
            if (!grab.isNull()) captured = grab.save(parser.value("screenshot"));
        }
        row.insert("screenshotSaved", captured);
        const auto bytes = QJsonDocument(row).toJson(QJsonDocument::Compact);
        if (bytes != previous) {
            row.insert("elapsedMs", clock.elapsed());
            output.write(QJsonDocument(row).toJson(QJsonDocument::Compact) + '\n');
            output.flush();
            previous = bytes;
        }
    };
    QObject::connect(&tick, &QTimer::timeout, &app, [&] {
        QFile control(parser.value("control"));
        if (control.open(QIODevice::ReadOnly)) {
            const auto parts = QString::fromUtf8(control.readAll()).trimmed().split(' ', Qt::SkipEmptyParts);
            control.close(); // Allow the Windows driver to atomically replace the command file.
            if (parts.size() >= 2 && parts[0].toInt() > commandSeq) {
                commandSeq = parts[0].toInt();
                if (parts[1] == "quit") app.quit();
                else if (parts[1] == "stop") click("stopButton");
                else if (parts[1] == "start") click("startButton");
                else if (parts[1] == "click-action") click("competitionActionButton");
                else if (parts[1] == "shortcut") QTest::keyClick(window, Qt::Key_F6);
                else if (parts[1] == "held-input") {
                    QTest::keyPress(window, Qt::Key_W);
                    QTest::mouseMove(window, QPoint(15, 15));
                } else if (parts[1] == "blur") {
                    focusPeer.show();
                    focusPeer.requestActivate();
                } else if (parts[1] == "focus") {
                    focusPeer.hide();
                    window->requestActivate();
                } else if (parts[1] == "release" && QGuiApplication::focusWindow()) {
                    QTest::keyRelease(QGuiApplication::focusWindow(), Qt::Key_W);
                } else if (parts[1] == "resize" && parts.size() == 4) {
                    window->resize(parts[2].toInt(), parts[3].toInt());
                }
            }
        }
        observe();
    });
    QObject::connect(&session, &application::ClientSession::basicStateChanged, &app, [&] {
        if (session.active()) observe();
    });
    QObject::connect(&session, &application::ClientSession::stateChanged, &app, observe);
    QObject::connect(&app, &QCoreApplication::aboutToQuit, &session, &application::ClientSession::stop);
    session.start(); tick.start();
    const int exitCode = app.exec();
    session.stop();
    return exitCode;
}
