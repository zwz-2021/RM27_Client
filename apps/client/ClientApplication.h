#pragma once

class QGuiApplication;

namespace rm27::client {

// 应用组合根：配置、对象生命周期、日志与 QML 接线集中在此处。
class ClientApplication {
public:
    static int run(QGuiApplication &app);
};

} // namespace rm27::client
