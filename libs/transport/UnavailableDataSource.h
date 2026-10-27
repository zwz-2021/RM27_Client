#pragma once

#include "application/IDataSource.h"

namespace rm27::transport {

// 正式模式的明确占位：接入当赛季协议后由真实传输适配器替换。
class UnavailableDataSource final : public application::IDataSource {
    Q_OBJECT

public:
    explicit UnavailableDataSource(QObject *parent = nullptr) : IDataSource(parent) {}

    void start() override;
    void stop() override;
};

} // namespace rm27::transport
