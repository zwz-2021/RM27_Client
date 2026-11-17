# 第 1 步：2027 基础数据

`rm27_protocol` 是可构建的离线编解码库。只支持 `GameStatus`、`GlobalUnitStatus`、`GlobalLogisticsStatus`、`RobotStaticStatus`、`RobotDynamicStatus`，不建立 MQTT 连接，不发送操作指令。字段、单位、频率、数组顺序和原文页号见 [契约](CONTRACT.md)。

- 唯一维护的基础 schema：`proto/rm27_base.proto`。C++ 在构建目录自动生成，Python 生成文件为 `simulator/protocol/rm27_base_pb2.py`；不手工修改生成代码。
- `BasicCodec` 将原始 topic/payload 转成 `domain/BasicData.h` 的类型，领域层不依赖 Protobuf。零值、false 和 optional 未提供各自保留；未知数字枚举保留原值。空 Protobuf 只表示未提供数据，不能据此宣告已收到有效比赛状态。
- 官方血量数组为八项，P-002 指定的弹量数组为六项；非空的错误长度会被拒绝。全局累计弹量保留 int32，自身剩余允许发弹量保留 uint32，不互相强制转换。
- 客户端内存防护上限为单条 1 MiB，浮点热量/射速/冷却值必须有限。这是本地程序保护，不是官方消息定长或官方字段范围。负数 int32 时间和未知枚举均不擅自改值。
- `robot_type` 按 2026-11-01 用户指定的 P-003 基准解释：1 重装、2 保留、3/4/5 步兵、6 空中、7 哨兵、8 飞镖、9 雷达。`RobotStaticData::role()` 优先有效机器人 ID，类型作后备；缺失、零和未知原值继续分别保留，不补造 ID/阵营，不把保留位当工程。来源及边界见 [契约](CONTRACT.md#p-003-采用的实际基准)。

## 构建和依赖

沿用根目录 `scripts/build.ps1`、`scripts/run.ps1` 及原来的 VS Code 按钮。`cmake/Protobuf.cmake` 固定下载并校验 Protobuf v29.3 与 Abseil 20240722.0 的 SHA256，随后用客户端的同一套 Qt MinGW 工具链编译静态库和 protoc，不依赖系统安装的 protoc 或 MSVC 二进制。

首次构建需要访问 GitHub 下载源归档并编译，耗时比原骨架长；后续使用 `build/dependency-downloads/` 缓存。离线构建可用 `FETCHCONTENT_SOURCE_DIR_ABSEIL`、`FETCHCONTENT_SOURCE_DIR_PROTOBUF` 指向同版本已解压源码。源代码许可证分别保留在下载源码中的 `LICENSE` 文件，发行依赖清单在第 6 步整理。Python 保留现有 `protobuf>=6.33.2,<7`，兼容新基础消息与保留的旧工具生成文件。

## 可重复的离线检查

从仓库根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-basic-data.ps1
```

已构建时加 `-SkipBuild`。需要先按 `simulator/scripts/start.ps1 -Install` 安装模拟器 Python 环境；检查不需要 Broker、Docker、视频或真实设备。

检查包括独立按 PDF 抄录的字段契约、人工核对的固定字节样本、C++ 编解码、Python → C++ 全字段/零值/缺失值，以及 C++ → Python 样本；随后检查模拟器实际基础负载、周期、输入校验和网页事件。覆盖 uint64 最大经济、负 int32 时间/弹量、浮点热量、未知枚举/附加字段、截断数据和错误数组长度。

构建出的 `build/local-debug/bin/RM27_ProtocolCheck.exe` 也可单独用于 `--decode TOPIC FILE`、`--decode-role RobotStaticStatus FILE` 或 `--emit-fixtures DIR`。`--decode-role` 在诊断 JSON 中显示解释出的角色，绝不把诊断字段加进通信报文。检查脚本还会把模拟器实际编码的 12 台机器人静态消息交给 C++ 检查类型和角色对应。运行时需要与客户端相同的 Qt/MinGW PATH，推荐使用上述脚本。

## 本步边界

客户端运行界面仍使用原有内部演示心跳，外部数据收取、状态合并、过期判断和指令闭环留到第 2 步。旧 `simulator/protocol/robomaster.proto` 只供未迁移工具使用，不是本批基础消息依据，也不是全套 RM27 兼容声明。
