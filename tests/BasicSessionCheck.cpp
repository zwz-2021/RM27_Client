#include "application/ClientSession.h"
#include "config/AppConfig.h"
#include <QCoreApplication>
#include <QEventLoop>
#include <QFile>
#include <QTemporaryDir>
#include <QTimer>
#include <iostream>
#include <stdexcept>

using namespace rm27;
void require(bool ok, const char *reason) { if (!ok) throw std::runtime_error(reason); }
class Source : public application::IDataSource {
public:
    int starts = 0;
    void start() override {
        ++starts;
        emit connectionChanged(domain::ConnectionState::Connected, "ready");
    }
    void stop() override { emit basicMessageReceived(domain::RobotDynamicData{}); }
    void send(const domain::BasicMessage &message, qint64 ageMs = 0) { emit basicMessageReceived(message, ageMs); }
};

static void checkReadOnlySeat()
{
    using domain::ConnectionState;
    using domain::OperatorSeat;
    Source source;
    application::ClientSession session(source);
    session.configureIdentity(3, "local");
    require(session.seat() == OperatorSeat::Unspecified && !session.requestBusinessAction()
                && session.actionFeedback().contains(QStringLiteral("未指定")),
            "a robot ID must not select a seat");

    session.configureIdentity(1, "local", OperatorSeat::Infantry);
    require(session.seat() == OperatorSeat::Infantry && session.robotId() == 1
                && session.actionFeedback().isEmpty(), "seat must be independent of the robot");
    const auto denied = [&] {
        require(!session.requestBusinessAction() && session.actionFeedback().contains(QStringLiteral("只读")),
                "read-only request must be denied with a reason");
    };
    denied();
    session.start();
    require(session.actionFeedback().isEmpty(), "request crossed into a started session");
    session.configureIdentity(103, "other");
    require(session.seat() == OperatorSeat::Infantry && session.robotId() == 1,
            "live receive identity changed");
    for (auto phase : {ConnectionState::Connected, ConnectionState::RetryWaiting,
                       ConnectionState::Connecting, ConnectionState::Subscribing,
                       ConnectionState::Connected}) {
        emit source.connectionChanged(phase, "test phase");
        emit source.diagnosticReceived("receive diagnostic");
        denied();
        denied();
        require(session.connectionState() == phase && session.active()
                    && session.diagnostic() == "receive diagnostic",
                "a denied intent disturbed reception");
    }
    session.stop();
    require(!session.active() && session.actionFeedback().isEmpty() && source.starts == 1,
            "stop did not clear feedback or rejection started another connection");
    denied();
    session.stop();
    require(session.actionFeedback().isEmpty(), "repeated stop left offline feedback behind");
}

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    try {
        checkReadOnlySeat();
        Source source;
        application::ClientSession session(source);
        session.configureIdentity(103, "test");
        session.start();
        domain::RobotDynamicData dynamic;
        dynamic.current_health = 321;
        source.send(dynamic);
        require(!session.basicState().robotDynamic.value, "unbound dynamic accepted");
        domain::RobotStaticData identity;
        identity.robot_id = 103;
        identity.robot_type = 3;
        source.send(identity);
        source.send(dynamic);
        require(session.basicState().robotDynamic.value->current_health == 321, "HP not applied");
        domain::GameData game;
        game.stage_countdown_sec = -3;
        source.send(game);
        require(session.basicState().robotDynamic.value->current_health == 321, "other topic erased HP");
        game.stage_countdown_sec = 42;
        game.red_score = 0;
        source.send(game);
        require(session.basicState().game.value->stage_countdown_sec == 42, "correction refused");
        dynamic.current_health = 0;
        source.send(dynamic);
        require(session.basicState().robotDynamic.value->current_health == 0, "zero lost");
        source.send(domain::RobotDynamicData{});
        require(!session.basicState().robotDynamic.value->current_health, "missing optional retains old HP");
        dynamic.current_health = 321;
        source.send(dynamic);
        QEventLoop loop;
        QTimer::singleShot(1300, &loop, &QEventLoop::quit);
        loop.exec();
        require(session.basicState().robotDynamic.stale && !session.basicState().robotStatic.stale,
                "freshness must be per-topic");
        source.send(dynamic);
        require(!session.basicState().robotDynamic.stale, "fresh packet did not recover");
        source.send(dynamic, 1100);
        require(session.basicState().robotDynamic.stale, "queued old sample was made fresh");

        source.send(domain::GlobalUnitData{});
        source.send(domain::LogisticsData{});
        source.send(dynamic);
        const auto &state = session.basicState();
        require(state.game.value && state.units.value && state.logistics.value
                    && state.robotStatic.value && state.robotDynamic.value, "five-topic setup failed");
        emit source.connectionChanged(domain::ConnectionState::RetryWaiting, "lost");
        require(session.active() && !state.game.value && !state.units.value && !state.logistics.value
                    && !state.robotStatic.value && !state.robotDynamic.value,
                "retry must clear all topics and keep the session stoppable");
        for (auto phase : {domain::ConnectionState::RetryWaiting, domain::ConnectionState::Connecting,
                           domain::ConnectionState::Subscribing}) {
            emit source.connectionChanged(phase, "recovering");
            source.send(game);
            source.send(identity);
            source.send(dynamic);
            require(!state.game.value && !state.robotStatic.value && !state.robotDynamic.value,
                    "message accepted before restored subscriptions");
        }
        emit source.connectionChanged(domain::ConnectionState::Connected, "ready again");
        source.send(domain::GlobalUnitData{});
        source.send(domain::LogisticsData{});
        source.send(dynamic);
        require(!state.units.value && !state.logistics.value && !state.robotDynamic.value,
                "identity from the lost connection was reused");
        source.send(identity);
        require(!state.robotDynamic.value, "pre-identity HP was replayed");
        source.send(dynamic);
        require(state.robotDynamic.value && !state.robotDynamic.stale
                    && state.robotDynamic.value->current_health == 321, "fresh recovery failed");
        identity.robot_id = 3;
        source.send(identity);
        require(!session.basicState().robotDynamic.value && !session.diagnostic().isEmpty(),
                "wrong robot retained own HP");
        emit source.connectionChanged(domain::ConnectionState::RetryWaiting, "lost again");
        session.stop();
        emit source.connectionChanged(domain::ConnectionState::Connected, "late callback");
        source.send(identity);
        source.send(game);
        require(!session.active() && session.connectionState() == domain::ConnectionState::Disconnected
                    && !state.game.value && !state.robotStatic.value, "stopped retry accepted callbacks");
        const auto beforeStarts = source.starts;
        QObject::connect(&session, &application::ClientSession::basicStateChanged, &session, [&] {
            session.stop();
            session.start();
        }, Qt::SingleShotConnection);
        session.start();
        require(source.starts == beforeStarts + 1 && session.active()
                    && session.connectionState() == domain::ConnectionState::Connected,
                "replaced start opened the data source twice");
        emit source.connectionChanged(domain::ConnectionState::RetryWaiting, "retry before stop");
        QObject::connect(&session, &application::ClientSession::basicStateChanged, &session, [&] {
            session.start();
            source.send(game);
        }, Qt::SingleShotConnection);
        session.stop();
        require(source.starts == beforeStarts + 2 && session.active() && state.game.value
                    && session.connectionState() == domain::ConnectionState::Connected,
                "finishing stop overwrote the new session");
        for (int i=0; i<100; ++i) {
            session.stop();
            source.send(dynamic);
            require(!session.basicState().robotDynamic.value, "stopped callback applied");
            session.start();
            require(!session.basicState().robotStatic.value, "identity crossed sessions");
        }
        session.stop();
        QTemporaryDir directory;
        const auto load = [&](const QByteArray &json) {
            const auto path = directory.filePath("config.json");
            QFile file(path);
            require(file.open(QIODevice::WriteOnly), "temporary config open failed");
            require(file.write(json) == json.size(), "temporary config write failed");
            file.close();
            return config::loadConfig(path);
        };
        require(load(R"({"mode":"simulation"})").config->mqtt.host == "127.0.0.1", "simulation host");
        require(load(R"({"mode":"official"})").config->mqtt.host == "192.168.12.1", "official host");
        require(bool(load(R"({"mode":"preview"})").config), "preview mode rejected");
        for (const auto json : {R"({"mode":"official","mqtt":{"robotId":3}})",
                                R"({"mode":"simulation","seat":"unspecified","mqtt":{"robotId":103}})"}) {
            const auto result = load(json);
            require(result.config && result.config->seat == domain::OperatorSeat::Unspecified,
                    "unspecified seat compatibility");
        }
        const auto infantry = load(R"({"mode":"simulation","seat":"infantry","mqtt":{"robotId":1}})");
        require(infantry.config && infantry.config->seat == domain::OperatorSeat::Infantry
                    && infantry.config->mqtt.robotId == 1, "seat was derived from the robot ID");
        for (const auto json : {R"({"mode":"official","seat":"Infantry"})",
                                R"({"mode":"official","seat":"commander"})",
                                R"({"mode":"simulation","seat":null})",
                                R"({"mode":"simulation","seat":3})",
                                R"({"mode":"simulation","seat":""})"}) {
            const auto result = load(json);
            require(!result.config && result.error.contains("seat"), "invalid seat silently accepted");
        }
        for (const auto &json : {R"({"mode":"simulation","mqtt":{"port":0}})",
                                R"({"mode":"simulation","mqtt":{"robotId":102}})",
                                R"({"mode":"simulation","mqtt":{"port":1.5}})",
                                R"({"mode":"simulation","mqtt":{"host":"tcp://bad"}})",
                                R"({"mode":"simulation","mqtt":{"unexpected":1}})",
                                R"({"mode":"simulation","mqtt":{"connectTimeoutMs":0}})"})
            require(!load(json).config, "invalid config accepted");
        std::cout << "PASS: state identity, correction, optional/zero, freshness, retry reset, "
                     "reentrant stop/start, 100 stops, config, independent read-only seat and rejected requests\n";
        return 0;
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
