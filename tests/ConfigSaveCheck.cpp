#include "config/AppConfig.h"

#include <QCoreApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLockFile>
#include <QTemporaryDir>
#include <iostream>
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

void put(const QString &path, const QByteArray &contents)
{
    QFile file(path);
    require(file.open(QIODevice::WriteOnly) && file.write(contents) == contents.size(), "write fixture");
}

QByteArray get(const QString &path)
{
    QFile file(path);
    require(file.open(QIODevice::ReadOnly), "read fixture");
    return file.readAll();
}

void checkPersonalConfig(const QString &path)
{
    const QByteArray old = R"({
        "mode":"simulation","window":{"title":" 窗口 ","width":1150},
        "mqtt":{"host":"localhost","connectTimeoutMs":750,"port":15558},
        "logging":{"directory":"../log dir"},"simulation":{"intervalMs":215}
    })";
    put(path, old);
    const auto opened = config::loadConfig(path);
    require(opened.config && !opened.revision.isEmpty()
            && opened.config->seat == domain::OperatorSeat::Unspecified
            && opened.config->mqtt.robotId == 1, "legacy configuration");
    const auto saved = config::saveInfantryConfig(path, 103, opened.revision);
    require(saved.config && saved.config->seat == domain::OperatorSeat::Infantry
            && saved.config->mqtt.robotId == 103, "first save");
    QJsonObject expected = QJsonDocument::fromJson(old).object();
    expected.insert("seat", "infantry");
    auto mqtt = expected.value("mqtt").toObject();
    mqtt.insert("robotId", 103);
    expected.insert("mqtt", mqtt);
    require(QJsonDocument::fromJson(get(path)).object() == expected, "unrelated keys changed or inserted");
    const auto reopened = config::loadConfig(path);
    require(reopened.config && reopened.revision == saved.revision
            && reopened.config->seat == domain::OperatorSeat::Infantry
            && reopened.config->mqtt.robotId == 103 && reopened.config->mqtt.port == 15558,
            "reopened selection differs");
    const auto good = get(path);
    for (const int id : {0, 2, 10, 102, 111, 65536}) {
        const auto invalid = config::saveInfantryConfig(path, id, reopened.revision);
        require(!invalid.config && invalid.error.contains("mqtt.robotId") && get(path) == good,
                "invalid ID altered file");
    }
    const auto stale = config::saveInfantryConfig(path, 4, opened.revision);
    require(!stale.config && stale.error.contains(QStringLiteral("重开")) && get(path) == good,
            "stale client overwrote a newer configuration");
    {
        QLockFile lock(path + ".lock");
        require(lock.tryLock(0), "acquire test lock");
        const auto busy = config::saveInfantryConfig(path, 4, saved.revision);
        require(!busy.config && !busy.error.isEmpty() && get(path) == good, "concurrent writer ignored");
    }
#ifdef Q_OS_WIN
    // Allow reading and writing, but deny replacing the original until the other program closes it.
    HANDLE held = CreateFileW(reinterpret_cast<LPCWSTR>(path.utf16()), GENERIC_READ,
                              FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    require(held != INVALID_HANDLE_VALUE, "hold destination without delete sharing");
    const auto denied = config::saveInfantryConfig(path, 4, saved.revision);
    CloseHandle(held);
    require(!denied.config && denied.error.contains(QStringLiteral("无法保存"))
            && get(path) == good && config::loadConfig(path).revision == saved.revision,
            "failed replacement damaged the previous configuration");
#endif
    const auto retry = config::saveInfantryConfig(path, 4, saved.revision);
    const auto afterRetry = config::loadConfig(path);
    require(retry.config && afterRetry.config && afterRetry.config->mqtt.robotId == 4, "save retry failed");
}

void checkRejectedSources(const QTemporaryDir &dir)
{
    const QByteArray old = R"({"mode":"official"})";
    for (const QString &name : {QStringLiteral("defaults.json"), QStringLiteral("infantry.EXAMPLE.JSON")}) {
        const QString path = dir.filePath(name);
        put(path, old);
        const auto result = config::saveInfantryConfig(path, 3, config::loadConfig(path).revision);
        require(!config::isEditableConfigPath(path) && !result.config && get(path) == old,
                "template overwritten");
    }
    require(!config::isEditableConfigPath(":/RM27/Client/defaults.json"), "resource writable");
    const QString path = dir.filePath("local.json");
    put(path, old);
    const auto opened = config::loadConfig(path);
    const auto converted = config::saveInfantryConfig(path, 105, opened.revision);
    const auto reopened = config::loadConfig(path);
    require(converted.config && reopened.config && reopened.config->mode == domain::RunMode::Official
            && reopened.config->mqtt.robotId == 105, "legacy configuration without mqtt");
    for (const QByteArray &contents : {QByteArray("{"), QByteArray(R"({"mode":"official","extra":2})"),
                                       QByteArray(R"({"mode":"official","mqtt":{"port":0}})"),
                                       QByteArray(R"({"mode":"official","mqtt":{"extra":2}})")}) {
        put(path, contents);
        const auto invalid = config::saveInfantryConfig(path, 3, converted.revision);
        require(!invalid.config && !invalid.error.isEmpty() && get(path) == contents
                && !config::loadConfig(path).config, "invalid file was overwritten");
    }
    const QByteArray preview = R"({"mode":"preview"})";
    put(path, preview);
    require(!config::saveInfantryConfig(path, 3, config::loadConfig(path).revision).config
            && get(path) == preview, "preview profile overwritten");
}

} // namespace

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    try {
        QTemporaryDir dir;
        require(dir.isValid(), "temporary directory unavailable");
        checkPersonalConfig(dir.filePath("local.json"));
        checkRejectedSources(dir);
        std::cout << "PASS: old and new profiles, ID validation, atomic save/reopen, rejection and retry\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
