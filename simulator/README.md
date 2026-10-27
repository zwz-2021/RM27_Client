# 独立模拟器

这里是独立 Python 模拟器的入口骨架，要求 Python 3.10 或以上，仅使用标准库。当前只实现命令行、日志和退出流程，没有比赛逻辑、网络端口或客户端通信。

从仓库根目录运行：

```sh
python -m simulator.server.main --check
python -m simulator.server.main
```

`--check` 检查入口后立即退出；不带参数时等待，按 Ctrl+C 正常退出。

## 与客户端模拟模式的关系

客户端 `mode: "simulation"` 使用 `libs/transport/MockDataSource` 的 Qt 定时器生成进程内演示快照，可以直接开发界面，无须运行本目录程序。

本目录将来承担 RM26 `sim/` 那样的独立协议对端。只有真实传输适配器及模拟器通信逻辑都接入后，两者才会通信。当前运行 Python 入口不会驱动客户端数据变化。

## 后续扩展

- 将比赛状态生成与 MQTT、UDP 等发送实现分开。
- 采用与客户端相同的协议契约；如引入 schema，统一保存在 `libs/protocol/`，不要各自手写不一致的定义。
- 将本地地址、端口和刷新周期放入模拟器自己的配置。
- 在独立入口中管理 socket、定时任务和线程的启动、停止，不让客户端链接或导入模拟器实现。
- 引入第三方 Python 包后再增加依赖声明；当前无需创建虚拟环境或安装额外包。

客户端构建方式见 [本地开发](../docs/development.md)。
