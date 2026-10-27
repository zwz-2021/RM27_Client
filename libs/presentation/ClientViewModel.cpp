#include "ClientViewModel.h"

#include <utility>

namespace rm27::presentation {

ClientViewModel::ClientViewModel(application::ClientSession &session,
                               std::optional<domain::RunMode> mode,
                               QString startupError, QString logPath, QObject *parent)
    : QObject(parent), session_(session), mode_(mode),
      startupError_(std::move(startupError)), logPath_(std::move(logPath))
{
    connect(&session_, &application::ClientSession::stateChanged,
            this, &ClientViewModel::stateChanged);
    connect(&session_, &application::ClientSession::snapshotChanged,
            this, &ClientViewModel::snapshotChanged);
}

QString ClientViewModel::modeText() const
{
    if (!mode_) {
        return QStringLiteral("未确定（配置错误）");
    }
    return *mode_ == domain::RunMode::Official
        ? QStringLiteral("正式接入（待实现）") : QStringLiteral("本地模拟预览");
}

QString ClientViewModel::connectionText() const
{
    switch (session_.connectionState()) {
    case domain::ConnectionState::Disconnected: return QStringLiteral("已停止");
    case domain::ConnectionState::Connecting: return QStringLiteral("启动中");
    case domain::ConnectionState::Connected: return QStringLiteral("运行中");
    case domain::ConnectionState::Unavailable: return QStringLiteral("尚未接入");
    }
    return QStringLiteral("未知状态");
}

QString ClientViewModel::connectionDetail() const { return session_.connectionDetail(); }
bool ClientViewModel::active() const { return session_.active(); }
bool ClientViewModel::canStart() const { return mode_.has_value() && !active(); }
bool ClientViewModel::hasSnapshot() const { return session_.hasSnapshot(); }

QString ClientViewModel::sequenceText() const
{
    return hasSnapshot() ? QString::number(session_.snapshot().sequence) : QStringLiteral("—");
}

QString ClientViewModel::elapsedText() const
{
    return hasSnapshot()
        ? QStringLiteral("%1 s").arg(session_.snapshot().elapsedSeconds) : QStringLiteral("—");
}

QString ClientViewModel::startupError() const { return startupError_; }
QString ClientViewModel::logPath() const { return logPath_; }

void ClientViewModel::start()
{
    if (canStart()) {
        session_.start();
    }
}

void ClientViewModel::stop() { session_.stop(); }

} // namespace rm27::presentation
