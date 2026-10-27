#include "UnavailableDataSource.h"

namespace rm27::transport {

void UnavailableDataSource::start()
{
    emit connectionChanged(domain::ConnectionState::Unavailable,
                           QStringLiteral("正式通信协议尚未接入；当前不会连接设备或发送指令。"));
}

void UnavailableDataSource::stop()
{
    emit connectionChanged(domain::ConnectionState::Disconnected,
                           QStringLiteral("正式数据源未连接。"));
}

} // namespace rm27::transport
