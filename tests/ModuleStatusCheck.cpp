#include "application/ClientSession.h"
#include "presentation/ClientViewModel.h"
#include "protocol/BasicCodec.h"

#include <QCoreApplication>
#include <QEventLoop>
#include <QTimer>
#include <iostream>
#include <stdexcept>

using namespace rm27;

namespace {
void require(bool ok, const char *reason)
{
    if (!ok) throw std::runtime_error(reason);
}

class Source final : public application::IDataSource {
public:
    void start() override { emit connectionChanged(domain::ConnectionState::Connected, "ready"); }
    void stop() override { emit basicMessageReceived(domain::RobotModuleData{}); }
    void send(const domain::BasicMessage &value, qint64 age = 0) { emit basicMessageReceived(value, age); }
};

QVariantMap row(const presentation::ClientViewModel &view, const QString &field)
{
    for (const auto &value : view.moduleRows()) {
        const auto item = value.toMap();
        if (item.value("field") == field) return item;
    }
    throw std::runtime_error("missing module row");
}

void checkState()
{
    Source source;
    application::ClientSession session(source);
    session.configureIdentity(3, "test", domain::OperatorSeat::Infantry);
    presentation::ClientViewModel view(session, domain::RunMode::Simulation, {}, {});
    require(view.moduleRows().size() == 11 && row(view, "armor").value("state") == "waiting_identity",
            "unknown identity must not show healthy modules");
    session.start();
    domain::RobotModuleData modules;
    modules.power_manager = 0; modules.rfid = 1; modules.light_strip = 2;
    modules.small_shooter = 1; modules.big_shooter = 0; modules.uwb = 1;
    modules.armor = 2; modules.video_transmission = 1; modules.capacitor = 0;
    modules.main_controller = 1; modules.modular_42mm = 1;
    source.send(modules);
    require(!session.basicState().robotModule.value, "unbound module accepted");
    domain::RobotStaticData identity;
    identity.robot_id = 3;
    source.send(identity);
    require(row(view, "armor").value("state") == "missing", "pre-identity module replayed");
    require(row(view, "big_shooter").value("state") == "not_applicable",
            "known inapplicable module was reported missing/offline");
    source.send(modules);
    require(row(view, "power_manager").value("state") == "offline"
        && row(view, "rfid").value("state") == "online"
        && row(view, "light_strip").value("state") == "installation_invalid"
        && row(view, "armor").value("value").toUInt() == 2,
        "module zero/one/two or independent fields lost");
    require(row(view, "modular_42mm").value("state") == "not_applicable"
        && row(view, "modular_42mm").value("value").toUInt() == 1,
        "non-heavy permission must remain raw evidence, not a granted action");
    source.send(domain::RobotModuleData{});
    require(session.basicState().robotModule.value
        && !session.basicState().robotModule.value->armor
        && row(view, "armor").value("state") == "missing",
        "empty valid sample retained previous module fields");
    source.send(modules, 3000);
    require(session.basicState().robotModule.stale && row(view, "armor").value("state") == "stale",
            "old mailbox sample made modules fresh");
    source.send(modules);
    require(!session.basicState().robotModule.stale, "fresh module failed to recover");
    // Keep only the identity fresh while module input is silent. This checks
    // elapsed-time expiration rather than merely the decoder's age metadata.
    QTimer identityRefresh;
    QObject::connect(&identityRefresh, &QTimer::timeout, [&] { source.send(identity); });
    identityRefresh.start(400);
    QEventLoop wait;
    QTimer::singleShot(3300, &wait, &QEventLoop::quit);
    wait.exec();
    identityRefresh.stop();
    require(session.basicState().robotModule.stale && !session.basicState().robotStatic.stale
        && row(view, "armor").value("state") == "stale", "module silence not independently expired");
    source.send(modules);
    identity.robot_id = 103;
    source.send(identity);
    require(!session.basicState().robotModule.value && row(view, "armor").value("state") == "waiting_identity",
            "mismatching static identity retained modules");
    identity.robot_id = 3;
    source.send(identity);
    require(!session.basicState().robotModule.value, "identity recovery revived old modules");
    source.send(modules);
    source.connectionChanged(domain::ConnectionState::RetryWaiting, "lost");
    require(session.active() && !session.basicState().robotModule.value, "retry retained old modules");
    source.connectionChanged(domain::ConnectionState::Connected, "reconnected");
    source.send(modules);
    require(!session.basicState().robotModule.value, "reconnect reused previous identity");
    source.send(identity);
    source.send(modules);
    require(session.basicState().robotModule.value.has_value(), "reconnect with new identity/module failed");
    session.stop();
    require(!session.basicState().robotModule.value, "stop callback retained module state");
    session.start();
    require(!session.basicState().robotModule.value, "restart retained old modules");
    source.send(identity, 3000);
    source.send(modules);
    require(!session.basicState().robotModule.value, "expired identity bound new module data");
    session.stop();
}

void checkRoles()
{
    // Independent rows from fabrication table 3-3, PDF 47-48, plus COM PDF63 #11.
    // Order: power, RFID, light, 17mm, 42mm, UWB, armor, video, capacitor, main, permission.
    const std::array<std::array<bool, 11>, 6> expected{{
        {{1,1,1,0,1,1,1,1,1,1,1}}, // heavy
        {{1,1,1,1,0,1,1,1,1,1,0}}, // infantry
        {{1,0,0,0,0,0,0,1,0,1,0}}, // aerial
        {{1,1,1,1,0,1,1,1,1,1,0}}, // sentry
        {{1,0,0,0,0,0,0,0,0,1,0}}, // dart
        {{1,0,0,0,0,0,0,0,0,1,0}}  // radar
    }};
    const std::array<int, 6> ids{1,3,6,7,8,9};
    for (std::size_t type = 0; type < ids.size(); ++type) {
        for (const auto teamOffset : {0, 100}) {
            Source source;
            application::ClientSession session(source);
            session.configureIdentity(ids[type] + teamOffset, "test");
            presentation::ClientViewModel view(session, domain::RunMode::Simulation, {}, {});
            session.start();
            domain::RobotStaticData identity;
            identity.robot_id = ids[type] + teamOffset;
            source.send(identity);
            const auto rows = view.moduleRows();
            require(rows.size() == 11, "role row count");
            for (qsizetype field = 0; field < rows.size(); ++field) {
                const auto item = rows[field].toMap();
                require(item.value("applicable").toBool() == expected[type][field], "role applicability mismatch");
                require(item.value("state") == (expected[type][field] ? "missing" : "not_applicable"),
                        "missing vs inapplicable conflated");
            }
            domain::RobotModuleData permission;
            permission.modular_42mm = 0;
            source.send(permission);
            require(row(view, "modular_42mm").value("state") == (type == 0 ? "permission_denied" : "not_applicable"),
                    "permission zero not distinct from missing");
            permission.modular_42mm = 1;
            source.send(permission);
            require(row(view, "modular_42mm").value("state") == (type == 0 ? "permission_granted" : "not_applicable"),
                    "permission one interpreted as installation or non-heavy grant");
            session.stop();
        }
    }
}
} // namespace

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    try {
        checkState();
        checkRoles();
        std::cout << "PASS: eleven module states, optional values, role applicability, identity, expiry and restart\n";
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
