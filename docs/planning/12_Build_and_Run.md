# 12 构建、启动与排查

2026-11-03 初次整理，2026-11-15 新增步兵只读席位的启动与检查说明。本页集中维护客户端和独立模拟器的本地使用方法。模块职责、协议文件和生成约定见 [11 架构](11_Architecture.md)，实际完成范围见 [13 进度记录](13_Progress_Log.md)，规则疑问和用户处理说明见 [09 问题记录](09_Open_Questions.md)。

开发遵守根目录 [AGENTS.md](../../AGENTS.md)，固定使用 `docs/rules/` 的现有文档。

## 1. 先分清要运行哪一部分

| 要观察的内容 | 入口 | 当前应该看到什么 |
| --- | --- | --- |
| Qt 客户端正式模式 | `scripts/run.ps1` | 默认连接 `192.168.12.1:3333`、clientID 为机器人 ID；展示五类基础接收状态，不发送业务指令；官方设备未验证 |
| Qt 客户端外部模拟器模式 | `scripts/run.ps1 -Mode simulation` | 连接默认 `127.0.0.1:3333`，展示外部模拟器五类基础数据；不自动启动 Python 服务或 Broker |
| 本地步兵只读席位 | `scripts/run.ps1 -ConfigFile configs/infantry.example.json` | 默认连接本地模拟器红方 3 号。在“运行信息”看 UDP 包头、收齐的压缩帧、解出的像素帧数与尺寸 |
| 步兵个人接收配置 | `scripts/run.ps1 -ConfigFile configs/local-infantry.json` | 首次按第 4 节复制示例。停止后可在工作台选择接收机器人，保存后用同一文件重开 |
| Qt 客户端内置心跳预览 | `scripts/run.ps1 -Mode preview` | 内部定时器产生演示心跳；不连接 Broker、不写五类基础比赛状态 |
| 本地 HEVC 软件解码 | `scripts/run.ps1 -HevcFile <本地 .hevc 文件>` | 在终端逐帧输出序号、尺寸及 SHA-256，末行汇总完整帧数。需要 PATH 中的 FFmpeg |
| 独立 Python 模拟器网页 | `simulator.server.main` 或模拟器启动脚本 | 浏览器出现控制台；顶部是第 1 步基础输入，其他保留工具仍有未迁移范围 |
| 模拟器与 Broker 的运行状态 | `simulator/scripts/check.ps1 -Runtime` | 检查 MQTT 握手和 HTTP 健康接口；不能据此判断 Qt 已收到数据或视频已播放 |

独立模拟器不依赖 Qt 客户端进程、客户端编译产物或 Qt 的 `MockDataSource`，可以单独安装和启动。`simulation` 从本轮起表示真实外部 MQTT；旧内置心跳入口改为 `preview`。五类接收之外的 UDP 视频和比赛功能状态以[13 进度记录](13_Progress_Log.md)为准。

除特别注明外，以下命令在 **RM27_Client 仓库根目录**执行。Windows 脚本按自身位置定位仓库，也支持从其他工作目录通过脚本绝对路径调用。示例中的 `-ExecutionPolicy Bypass` 只作用于新启动的这次 PowerShell 进程，不修改系统执行策略。允许直接执行脚本的终端，也可以使用 `./scripts/build.ps1` 等短写。

## 2. 客户端依赖与首次配置

客户端使用 Qt Quick / C++17，Windows 共享预设面向 Qt MinGW，需要：

- Qt **6.8 或以上**，包含 Core、Network、Gui、Qml、Quick、QuickControls2。默认开启 `BUILD_TESTING`，构建界面检查器还需 Qt Test。MQTT 使用下文的 Paho 库。
- 与该 Qt 套件匹配的 MinGW、CMake **3.21 或以上**、Ninja。
- Windows PowerShell **5.1** 或 PowerShell **7**。

基础编解码和 MQTT 使用 **Protobuf v29.3**、**Abseil 20240722.0**、**Eclipse Paho C 1.3.15**。CMake 按固定版本和 SHA256 下载源归档，用客户端同套工具链构建静态库及 `protoc`，不需要系统另装 Protobuf 或 MQTT 库。Paho 使用不带 TLS 的异步 MQTT 3.1.1 接口；项目本轮的官方地址与本地 Broker 均为 TCP。首次构建需取得归档；Debug/Release 共用 `build/dependency-downloads/` 缓存，各自保留源码和编译目录。客户端本身不需要 FFmpeg 或 Docker，外部模拟器的 Broker 部署另见后文。

首次在一台电脑配置时：

1. 将 `CMakeUserPresets.json.example` 复制为 `CMakeUserPresets.json`。已有本机用户预设时直接检查，不覆盖原文件。
2. 修改 `local-debug`、`local-release` 中下面四项绝对路径，保持模板的预设名称和继承关系。
3. 使用下节脚本，或 VS Code 的构建、运行按钮。

| 变量 | 应指向的位置 | 模板示例 |
| --- | --- | --- |
| `RM27_QT_ROOT` | Qt MinGW 套件根目录，含 `bin/Qt6Core.dll` | `D:/Qt6/6.11.2/mingw_64` |
| `RM27_MINGW_ROOT` | MinGW 根目录，含同套 `bin/g++.exe`、`bin/gcc.exe` | `D:/Qt6/Tools/mingw1310_64` |
| `RM27_NINJA_ROOT` | 含 `ninja.exe` 的目录 | `D:/Qt6/Tools/Ninja` |
| `RM27_CMAKE_ROOT` | CMake 根目录，含 `bin/cmake.exe` | `D:/Qt6/Tools/CMake_64` |

无需额外设置系统环境变量。脚本读取所选用户预设中的工具路径，CMake 负责继承公共规则。`CMakePresets.json` 保存共享构建规则，`CMakeUserPresets.json.example` 是可提交模板；实际的 `CMakeUserPresets.json` 已被 Git 忽略，只保存本机路径。

## 3. 客户端构建与运行

```powershell
# 配置并构建，默认 Debug。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Configuration Release

# 先增量构建再运行，默认 Debug / official。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Mode simulation
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Configuration Release -Mode simulation
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Mode preview

# 已构建时跳过编译，指定个人配置和日志目录。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -SkipBuild -ConfigFile configs/local.json -LogDirectory logs
```

| 脚本/参数 | 默认值 | 实际作用 |
| --- | --- | --- |
| `build.ps1 -Configuration Debug\|Release` | `Debug` | 配置并编译 `local-debug` 或 `local-release` |
| `build.ps1 -Jobs <整数>` | 处理器数与 8 的较小值 | 并行编译任务数，可取 1～256，例如 `-Jobs 4` |
| `run.ps1 -Configuration Debug\|Release` | `Debug` | 选择对应构建；默认先调用构建脚本 |
| `run.ps1 -Mode official\|simulation\|preview` | `official` | 没有指定 `-ConfigFile` 时，分别选择内嵌默认配置、`configs/simulation.example.json`、`configs/preview.example.json` |
| `run.ps1 -ConfigFile <文件>` | 未指定 | 使用指定 JSON；优先于 `-Mode`，实际模式由文件中的 `mode` 决定 |
| `run.ps1 -LogDirectory <目录>` | 未指定 | 覆盖配置中的日志目录 |
| `run.ps1 -SkipBuild` | 关闭 | 不编译，但仍需要对应 exe 和完整 `CMakeCache.txt` |

构建产物在 `build/local-debug/bin/` 或 `build/local-release/bin/`。构建、配置或客户端异常退出会返回非零退出码。运行脚本从构建缓存读取实际 Qt 和编译器位置，临时补齐当前进程的运行时 PATH；关闭客户端窗口后脚本结束并恢复 PATH，不永久修改系统环境。

构建前关闭同一构建目录中的客户端，避免 Windows 锁定 exe 导致链接失败；不要同时启动多个相同版本的构建任务。更换 Qt 或编译器时使用新构建目录，不复用旧工具链缓存。

希望直接使用 CMake 时，先保证 `cmake.exe` 可从 PATH 找到，再执行：

```powershell
cmake --preset local-debug
cmake --build --preset local-debug
```

Qt Creator 也可直接打开根目录 `CMakeLists.txt` 并选择匹配的 Kit。直接调用 exe 可使用 `--help`、`--version`、`--config <文件>`、`--log-dir <目录>`；直接启动时仍需提供 Qt/MinGW 运行依赖，开发脚本会自动处理本机开发环境中的对应路径。

## 4. 客户端个人配置、日志和路径规则

程序不传 `--config` 时读取编入资源的 `configs/defaults.json`，默认 `official`；`simulation` 连接外部模拟器，`preview` 才是内部演示心跳。外部个人配置可以保存在已被 Git 忽略的 `configs/local.json`：

```json
{
  "mode": "simulation",
  "mqtt": { "host": "127.0.0.1", "port": 3333, "robotId": 1, "connectTimeoutMs": 5000 },
  "window": { "title": "RM27 Client", "width": 1280, "height": 800 },
  "simulation": { "intervalMs": 500 },
  "logging": { "directory": "../logs" }
}
```

`mode` 必填，支持 `official`、`simulation`、`preview`，回放尚未实现；其他节可省略。窗口标题须非空，宽度 640～7680、高度 480～4320；`simulation.intervalMs` 是 preview 心跳间隔，须为 100～60000 毫秒整数，不控制外部消息频率。未知字段、类型错误或越界值会显示配置错误，不启动数据源。用文本编辑器修改配置后重开程序；内嵌默认配置修改后须重编译。

**在工作台保存步兵接收配置。** 从仓库根目录运行以下命令。第一次创建个人文件，之后保留自己的设置。

```powershell
if (!(Test-Path -LiteralPath .\configs\local-infantry.json)) {
    Copy-Item .\configs\infantry.example.json .\configs\local-infantry.json
}
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -ConfigFile configs/local-infantry.json
```

在工作台点“停止”，选择“接收机器人”，点“保存步兵只读配置”。看到保存成功后，点“启动数据源”或用同一条命令重开。顶部显示步兵只读，连接卡显示新 clientID，收到新机器人的静态状态后才会显示其血量。接模拟器时，在网页顶部选择相同的机器人。若文件被占用且保存失败，原身份可继续启动，解除占用后再保存。若提示配置已被其他窗口修改，重开该文件后再选。省略 `seat` 的旧 JSON 可直接打开，点保存才写入席位。程序资源、`defaults.json`、`*.example.json` 及预览模式不提供个人接收编辑。

| MQTT 字段 | 默认值/范围 | 作用 |
| --- | --- | --- |
| `host` | official 为 `192.168.12.1`，simulation 为 `127.0.0.1` | 非空主机名/IP，不含空白或 `tcp://` 等协议前缀；域名异步解析 |
| `port` | `3333`；整数 1～65535 | Broker TCP 端口 |
| `robotId` | `1`；1、3～9 及蓝方 +100 | 转为 MQTT clientID；2/102 保留，基地/前哨不作机器人连接身份 |
| `connectTimeoutMs` | `5000`；整数 100～60000 | 连接和订阅确认各自使用的本地超时，不是比赛规则时长 |

官方步兵配置默认在 `192.168.12.2:3334/UDP` 监听，网卡地址须由系统配置。模拟模式的步兵席默认在 `127.0.0.1:3334/UDP` 监听。本机隔离测试可在 JSON 的 `video` 对象设置 `bindAddress`（本地 IPv4 字面地址）和 `port`（1～65535 整数），并把模拟器的目标设为该端点。省略 `video` 使用上述默认值。预览和未指定席位不会绑定 UDP。本地选择机器人 ID 的现场权限见 P-007，模拟器当前提供 12 台机器人。

| 路径或选择 | 基准与优先级 |
| --- | --- |
| 脚本的 `-ConfigFile`、`-LogDirectory` 相对路径 | 以仓库根目录为基准，与调用脚本时的工作目录无关 |
| 配置选择 | `-ConfigFile` 优先于 `-Mode`；无外部文件时 simulation/preview 使用各自示例，official 使用内嵌默认配置 |
| 外部 JSON 的 `logging.directory` 相对路径 | 以该 JSON 文件所在目录为基准，例如上例从 `configs/` 指向仓库 `logs/` |
| 内嵌配置中的日志相对路径 | 以进程工作目录为基准；运行脚本会将工作目录设为仓库根目录 |
| 日志位置优先级 | 命令行 `--log-dir`（脚本 `-LogDirectory`）→ 配置 `logging.directory` → 系统应用本地数据目录中的 `logs/` |
| 直接启动 exe 的 `--config`、`--log-dir` 相对路径 | 以进程工作目录为基准 |

`logging.directory` 省略或为空时才使用系统目录。**当前仓库的 `configs/defaults.json` 和 `configs/simulation.example.json` 都显式写了 `D:/Competition/RM/RM27/code/RM27_Client/logs`**；换电脑时可使用个人配置或 `-LogDirectory` 指定可写位置。新增 preview 示例使用相对目录 `../logs`。

日志是 JSONL，文件名为包含 UTC 时间和进程 ID 的 `client-*.jsonl`。界面的“运行信息”页显示实际日志路径；日志记录启动、会话状态、接收诊断和退出。目录创建、打开或写入失败会有错误提示。

### 五类接收的手动闭环

观察步兵席位时，在仓库根目录执行下面两条命令，分别启动独立模拟器和 Qt 客户端。模拟器脚本会按原有规则复用 Broker 或通过 Docker 启动本地 Broker。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -CurrentRobotId 3
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -ConfigFile configs/infantry.example.json
```

客户端 JSON 顶层的 `"seat": "infantry"` 选择本地步兵只读席位。省略 `seat` 或填写 `"unspecified"` 会显示“本地席位 · 未指定（只读）”。其他值会在连接前提示配置错误。机器人 ID 单独取自 `mqtt.robotId`，工作台的来源卡会显示配置的 clientID，静态状态卡则等待收到机器人身份后再显示。修改配置后重新启动客户端。

在步兵工作台点“赛事操作 (F6)”或按 F6，界面应提示前往官方操作端。该按键只是本地快捷键。收包、停止和自动重连仍沿用原入口。只读席位与界面权限检查可运行 `scripts/check-mqtt-receive.ps1` 自动复现，使用临时本机端口和 Qt Test。

使用原有默认身份时，按下面命令启动。

```powershell
# 先启动独立模拟器与 Broker，再单独启动客户端。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Mode simulation
```

打开 [模拟器网页](http://127.0.0.1:8000)，保持当前机器人与客户端 `robotId` 一致（默认红方1号）。在基础动态输入将自身血量设为 **321** 并发送，Qt 工作台应显示 **321**、收到的机器人身份及“外部模拟器”来源；其余四类可分别观察比赛、单位、经济和静态卡片。

连接中、Broker 已连接正在订阅、五类订阅就绪、每类未收到/已收到/已过期分别显示。未收到或字段缺失显示 `—`；错误身份会提示并清空相关数据。Game/Dynamic 超过1秒、其余三类超过3秒无更新会标过期并隐藏旧值，250ms检测一次。这些是本地诊断阈值。订阅就绪不表示机器人在线或比赛就绪。

保持客户端开启。首次连不上、连接中断或订阅失败时，工作台显示“等待重连”、具体原因和下次尝试间隔，五类旧值清空。客户端按 0.5、1、2、4 秒重试，随后保持 4 秒。Broker 恢复后自动确认五条订阅。比赛状态可独立更新，血量、单位和经济要等新的匹配身份及对应实时消息。仅收到保留报文时，数值继续显示 `—`。坏包会显示诊断。

点“停止”或关闭窗口会取消后续重试。手动停止后，点“启动数据源”才会重新连接。只想复现断线和恢复时，可运行下方的自动检查，脚本会在独立端口停启自己的 Broker。

## 5. 独立模拟器依赖与安装

模拟器使用自己的 `simulator/.venv/`，需要 Python **3.11+**。生产依赖保留 FastAPI、Uvicorn、Socket.IO、上传支持、OpenCV、NumPy、Paho MQTT 以及 `protobuf>=6.33.2,<7`，见 `simulator/pyproject.toml` 与兼容入口 `requirements.txt`。不安装到 Qt 环境，不把模拟器加入 CMake。

没有现成可用 Broker 时，Windows 管理脚本需要 **Docker Desktop 和 Compose v2** 来启动独立 Mosquitto；真实 HEVC/H.264 视频需要 **FFmpeg**。Docker 和 FFmpeg 命令应能从当前进程 PATH 找到，模拟器安装、运行不会永久修改系统 PATH。协议重新生成和兼容检查还需相应 `protoc`。这些条件分别检查，不能用 Python 导入成功替代容器、视频或通信验证。

```powershell
# 只创建专用虚拟环境并安装 Python 依赖，完成后退出，不启动服务。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -Install

# Python 不在 PATH 时，首次创建环境可指定解释器。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -Install -Python "C:\Python311\python.exe"

# 检查 Python 依赖、必要资源，并报告 Docker / FFmpeg 可用性。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1
```

无需手动激活环境。`-Install` 优先于其他启动参数和组合校验，安装后立即退出。已有 `.venv` 时沿用它；`-Python` 仅用于创建缺失环境，不替换已有解释器。

`check.ps1` 不自动安装依赖，也不启动或停止服务。缺少 Python 环境、依赖或必要资源会失败；缺 Docker、Compose、Docker daemon 或 FFmpeg 时会报告提示，提示本身不使离线检查返回失败。因此返回 `0` 不能写成 Docker 部署、FFmpeg 编解码或端到端通信已经通过。

## 6. 模拟器 Windows 启动方式与全部参数

```powershell
# 只有 Broker，不要求先安装模拟器虚拟环境。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -BrokerOnly

# Broker + 模拟器网页、状态、MQTT 及保留的赛事引擎。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1

# 同时发送兼容 UDP 状态；需要兼容控制帧接收时才加 -EnableReceiver。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -EnableUdpSender
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -EnableUdpSender -EnableReceiver

# 模拟器加独立 HEVC 视频发送器；文件须已存在，需 FFmpeg。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -VideoFile resources/videos/testdemo.mp4

# 仅 Broker + 独立视频发送器，跳过 Web/状态服务。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -VideoOnly -VideoFile resources/videos/testdemo.mp4
```

正常启动会先对所选地址执行 MQTT CONNECT/CONNACK 握手；已有 Broker 能握手就复用，没有取得它的停止权。需要新建 Broker 时，只使用本仓库独立 Compose 服务。远程 Broker 不能握手会直接失败，不替换为本地 Broker；本地端口被非 MQTT 程序占用也会失败。已运行的 Compose Broker 不会为了本次参数被重建或换端口。

普通启动在服务就绪后返回，服务继续在后台运行。浏览器打开 [Web 控制台](http://127.0.0.1:8000)。顶部是“第 1 步：2027 基础数据准备”及静态、动态、经济输入；自动赛事演示默认空闲，视频默认不推流。自动赛事启动、暂停、恢复、速度、红蓝视角及其余手动工具仍保留旧版语义，未迁移部分不能当作已符合 RM27。

| `start.ps1` 参数 | 默认值 | 作用与边界 |
| --- | --- | --- |
| `-Install` | 关闭 | 只创建/安装 `.venv`，完成后退出 |
| `-Python <路径或命令>` | `python` | 创建缺失环境时使用的 Python 3.11+ 解释器 |
| `-BrokerOnly` | 关闭 | 只准备或复用 Broker，不启动模拟器、网页和视频 |
| `-WebPort <端口>` | `8000` | 本机 Web/Socket.IO 端口，1～65535，脚本固定绑定 `127.0.0.1` |
| `-MqttHost <地址>` | `127.0.0.1` | 要连接或复用的 Broker 地址 |
| `-MqttPort <端口>` | `3333` | Broker 宿主端口，1～65535；本次 Compose 调用使用同值 |
| `-TargetIP <地址>` | `127.0.0.1` | UDP 状态、网页内置 HEVC 及独立 HEVC 视频发送目标，不改变 Web/Broker 监听地址 |
| `-CurrentRobotId <ID>` | `1` | 接受 1/3/4/5/6/7 及蓝方对应 +100，共 12 台；2/102 为保留，不接受 |
| `-EnableUdpSender` | 关闭 | 在 MQTT 之外同时发送兼容 UDP 状态，不是视频开关 |
| `-EnableReceiver` | 关闭 | 启用兼容 UDP 控制帧接收，默认绑定本地 `127.0.0.1:3333/UDP` |
| `-VideoFile <文件>` | 未指定 | 额外启动独立 HEVC 视频发送器，相对路径以 `simulator/` 为基准，也接受带引号的绝对路径 |
| `-VideoOnly` | 关闭 | 不启动 Web/状态服务，必须同时指定 `-VideoFile`；仍准备或复用 Broker |

`-BrokerOnly` 不能与 `-VideoOnly`、`-VideoFile`、`-EnableUdpSender`、`-EnableReceiver` 组合。`-VideoOnly` 下没有状态服务供两个 UDP 状态/接收开关作用，不应混用。UDP 接收默认关闭；如果测试客户端也要绑定同一本地 UDP 端口，先调整安排，不能把接收器开关当作客户端连接开关。

```powershell
# 自定义端口及蓝方当前机器人。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -WebPort 8001 -MqttPort 1883 -CurrentRobotId 101

# 复用远程 Broker，向指定客户端发送兼容 UDP 状态。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -MqttHost 192.168.1.20 -MqttPort 1883 -TargetIP 192.168.1.30 -EnableUdpSender
```

同一工作区已有脚本归属的模拟器/视频进程时，普通启动不重复创建；切换端口或发送模式前先使用停止脚本。同一工作区的启动/停止由锁协调。

## 7. 视频文件、上传与发送入口

手动联测时，按[模拟器与 Qt 客户端手动联测](../../simulator/scripts/README.md)依次检查网页血量、本机录屏经 UDP 组帧和后台解码，以及客户端停止、重开后的计数。指南同时给出复用已运行服务和从零启动的路径。

### 步兵 UDP 诊断

在仓库根目录运行以下命令启动步兵只读客户端。打开“运行信息”，应看到本地 UDP 端点和零计数。选用本节下方的一条 HEVC 发送入口后，有效包计数随收包增长，最近有效包显示来源地址、源端口、整包字节数、帧号、片号和整帧字节数。

```powershell
.\scripts\run.ps1 -Configuration Debug -ConfigFile configs/infantry.example.json
```

UDP 绑定失败可查看系统错误，检查本地地址、关闭占用端口的程序或在个人模拟配置中换端口，然后在工作台停止并重新启动。MQTT 等待重连期间可以继续观察 UDP。短包、超长、只有头、帧长小于本包净数据分别计数。

用本机回环地址发送时，“本机模拟组帧”的完整帧计数会增长，最近完整帧显示帧号、字节数及来源。缺片等到首片抵达后 250 ms 计入超时，长度或同片内容矛盾计入冲突，超过工程限额计入超出预算。停止并重新启动会清空包头、最近完整帧、计数及缓存。官方模式和非回环来源只统计原始包头。

在本机步兵模拟配置中，从网页选一段本机录屏并推流。在“运行信息”找到“本机模拟解码”，查看已解码帧数、尺寸、排队和输入丢弃。使用 `demo-1080p60-hevc.mp4` 时，帧数应增长，尺寸应为 1920×1080。网页停止推流后等尾部排空，计数保持稳定。在客户端点“停止”再点“启动数据源”，未重新推流时应看到零帧，重新推流会再次显示尺寸和计数。只选一个发送入口。若完整帧增长但解码一直为零，可查看解码提示、确认已切换到有效视频及 PATH 中有 FFmpeg。若提示 FFmpeg 无法启动，配好 PATH 后重新打开客户端。

如需手动对照像素，在上述启动命令末尾加 `-TraceSimulatedVideo`。在客户端“工作台”点“停止”后，打开“运行信息”显示的本次日志文件；`video.decode_frame` 记录本次会话前 32 帧以内的序号、尺寸和像素 SHA-256，`video.decode_summary` 给出累计统计。通常手测直接看界面读数即可。工作台画面按 T-055 另验。

在根目录先用 `.\scripts\build.ps1 -Configuration Debug` 构建，再运行下列检查。第一条核对两个模拟器发送入口的真实数据报，第二条在产品窗口核对组帧和错误计数，第三条对比本机模拟视频解出的像素、顺序和末帧。窗口检查使用临时端口。三项均需能从 PATH 调用带所需编码器的 FFmpeg。

```powershell
.\simulator\.venv\Scripts\python.exe -m simulator.tools.check_video_datagrams
.\simulator\.venv\Scripts\python.exe tests/check_udp_receive.py --configuration Debug
.\simulator\.venv\Scripts\python.exe tests/check_simulated_video_decode.py --configuration Debug
```

### 本地 HEVC 文件解码

对本机已经转换的录屏，可在仓库根目录手动查看头三帧或整段解码结果。第一条运行命令会单独构建解码检查工具，可以与已打开的客户端窗口共存。

```powershell
$clip = 'simulator/resources/videos/demo-1080p60.hevc'
.\scripts\run.ps1 -Configuration Release -HevcFile $clip -StopAfter 3
.\scripts\run.ps1 -Configuration Release -SkipBuild -HevcFile $clip | Select-Object -Last 1
```

第一条解码命令应输出 3 行 `frame` 和一行 `stopped` 汇总。整段录屏应看到 `completed`、3762 帧。有帧且带解码错误读到末尾时，工具报告 `completed_with_errors`。无法解码的文件报告 `error`。两者均保留原因并返回 1。`-HevcFile` 接受文件路径数组，可连续打开多段短片。每个文件的序号从 1 开始。

小样输入是 Annex B 裸视频。对已经是 HEVC 的 MP4，可无损取出视频轨。以下命令仅在需要新建样本时运行，FFmpeg 的 `-n` 会保留已有文件。

```powershell
ffmpeg -n -i simulator/resources/videos/demo-1080p60-hevc.mp4 -map 0:v:0 -c:v copy -bsf:v hevc_mp4toannexb -f hevc simulator/resources/videos/demo-1080p60.hevc
```

在其他机器复验，先用 `.\scripts\build.ps1 -Configuration Release -HevcProbe` 构建工具，再运行 `python tests/check_hevc_decode.py --configuration Release`。脚本使用标准库、FFmpeg（含 libx265）和 ffprobe，自动生成独立的已知像素短片，在终端打印证据目录和通过项。工作台的实时视频显示仍待开发。

后台解码工具收到实际 YUV420p 像素后计算摘要。读完或停止后，汇总中的 `firstFrameAfterClose` 给出重新读取首帧的结果。传入两个文件时，第二次汇总中的 `previousFirstFrameAfterClose` 可与第一段首帧对照。[两个不同尺寸短片的操作步骤](../../libs/video/README.md#手动核对后台交付的像素帧)给出了具体命令和预期。

同一次回归还会生成前段损坏、后段完整的单文件样本。第二段从关键帧开始的全部 12 帧应通过独立像素核对。打开该样本、查看汇总和异常对照的步骤见[离线恢复手测](../../libs/video/README.md#手动核对同一文件损坏后恢复)。

### 启动 HEVC 发送器

视频放在 `simulator/resources/videos/`，或通过网页上传、选择。该目录中的视频不进入 Git，上游也未随公开源码提供测试录像。可以准备自己的文件，或用 FFmpeg 生成不含外部素材的片段：

```powershell
.\simulator\.venv\Scripts\python.exe -m simulator.tools.create_test_video
```

默认生成 `simulator/resources/videos/testdemo.mp4`，3 秒、640×360、30 帧/秒、H.264、无音轨。可用 `--duration 1..60` 调整秒数，`--output <文件>` 指定输出；自定义相对输出路径以当前工作目录为基准。工具不会覆盖已存在的文件。

普通启动后可在网页开启内置 **HEVC 图传**。启动脚本的 `-VideoFile` 可另外运行独立的 `simulator.tools.video_sender` 进程。同一目标选择一个 HEVC 发送入口，两者都按每包最多 1392 净字节分片，并继承输入视频的尺寸和帧率。网页上的 H.264 工业相机另走 MQTT `CustomByteBlock`。HEVC 解码和画面验收见 T-054/055。

独立工具也可从仓库根目录直接运行：

```powershell
.\simulator\.venv\Scripts\python.exe -m simulator.tools.video_sender resources/videos/testdemo.mp4 127.0.0.1 3334
```

其位置参数为 `<视频文件> [目标IP] [目标端口]`，默认目标 `127.0.0.1:3334/UDP`，默认循环播放，命令行没有关闭循环的选项；前台运行用 `Ctrl+C` 退出，脚本管理的发送器用停止脚本退出。相对视频路径先按 `simulator/` 查找，再回退到 `simulator/resources/videos/` 下查找；所以文件参数可写 `resources/videos/testdemo.mp4` 或其中的文件名。不要在相对参数前重复添加 `simulator/`。Windows 启动脚本自己的 `-VideoFile` 直接按 `simulator/` 解析，不使用文件名回退规则。

## 8. 模拟器检查、停止和运行日志

```powershell
# 离线检查。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1

# 检查真正运行中的 MQTT 握手和 HTTP 健康接口。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1 -Runtime

# 只启动了 Broker 时，跳过 Python/资源及 HTTP 检查。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1 -Runtime -BrokerOnly

# 对应自定义端口。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1 -Runtime -WebPort 8001 -MqttPort 1883

# 停止本项目记录的模拟器/视频及自己创建并记录的 Broker。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\stop.ps1

# 停止模拟器/视频，保留 Broker。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\stop.ps1 -KeepBroker
```

| `check.ps1` 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `-Runtime` | 关闭 | 额外检查真实 MQTT 握手；非 BrokerOnly 模式还检查 HTTP |
| `-BrokerOnly` | 关闭 | 跳过模拟器 Python/资源及 HTTP 检查 |
| `-WebPort <端口>` | `8000` | 要检查的本地 HTTP 端口，1～65535 |
| `-MqttHost <地址>` | `127.0.0.1` | 要检查的 Broker 地址 |
| `-MqttPort <端口>` | `3333` | 要检查的 Broker 端口，1～65535 |

检查成功返回 `0`；Python/资源失败，或启用 Runtime 后 MQTT/HTTP 失败，返回 `1`。参数错误和脚本异常也返回非零。Runtime 只验证 Broker 可握手、HTTP 健康接口可访问，不检查每个 topic 的业务内容、视频解码画面或 Qt 显示。只有 Broker 时漏加 `-BrokerOnly`，会因没有 HTTP 服务而检查失败。

`stop.ps1` 唯一自定义参数为 `-KeepBroker`。它停止前核对 PID、启动时间和可执行文件路径；Web 服务还核对 HTTP 实例标识，优先用本机令牌正常退出，必要时只结束再次核对过的归属 PID。Windows 进程宿主通过 JobObject 管理自己的 FFmpeg 等后代，不按端口或进程名查杀其他程序。

停止 Broker 前会核对具体容器 ID、Compose 项目、服务和配置路径标签。复用的外部 Broker、未取得归属的预存容器保持运行；停止不执行 Compose `down`，不删除镜像。无法停止或无法确认 Docker 状态时会报错并保留必要记录，不能假报停止成功；可在原因排除后重试。启动失败回滚也只处理本次创建的资源。

运行文件位于已被 Git 忽略的 `simulator/.runtime/`：

| 文件 | 用途 |
| --- | --- |
| `state.json` | 进程、实例、启动时间、Broker 容器等归属记录，含本机停止令牌；运行时应保留，停止脚本依赖它 |
| `server-*.log` / `server-*.error.log` | 模拟器标准输出 / 错误输出 |
| `video-*.log` / `video-*.error.log` | 独立视频发送器标准输出 / 错误输出 |
| `host-*.json` | Python 后台宿主身份握手记录 |
| `lifecycle.lock` | 协调启动和停止，避免并发改写归属状态 |

日常入口只有 `start.ps1`、`check.ps1`、`stop.ps1`；`common.ps1` 和 `process_host.py` 是内部支撑，不需直接操作。启动失败先查看命令输出指向的日志，不删除归属记录来绕过检查。

## 9. 地址、健康接口与独立 Broker

| 链路 | 默认地址 | 当前用途 |
| --- | --- | --- |
| Web / Socket.IO | `127.0.0.1:8000/TCP` | 网页、状态、上传及保留的赛事操作 |
| MQTT | `127.0.0.1:3333/TCP` | 五类已迁移基础消息及保留的旧版上行工具 |
| UDP 状态发送 | 目标 `127.0.0.1:3333/UDP` | 保留的简化 CmdID/Length 状态帧，显式开启 |
| UDP 控制接收 | 本地 `127.0.0.1:3333/UDP` | 保留的 CRC8/CRC16 控制帧，显式开启 |
| UDP 视频 | 目标 `127.0.0.1:3334/UDP` | HEVC、8 字节大端帧号/分片/长度头，整包最多 1400 字节。步兵只读客户端可查看收包诊断 |
| 工业相机 | 同一 MQTT Broker | H.264 Annex-B 分片及 packetId，经 `CustomByteBlock` 发送 |

MQTT 使用 TCP3333，兼容状态使用 UDP3333，图传使用 UDP3334。步兵只读会话独立监听标准图传端口，其他席位当前只接 MQTT。模拟器的兼容 UDP 状态发送仍需显式开启。

浏览器访问 [健康接口](http://127.0.0.1:8000/api/health) 可查看协议模式 `rm27-base-v1.0.0+legacy-tools`、五类基础 topic、`mqttConnected`、当前机器人、实例 ID 和链路设置。`status: ok` 是 HTTP 健康状态；另看 `mqttConnected` 才知道模拟器 MQTT 连接状态。网页“链路在线”只表示浏览器 Socket.IO 已连到本机服务。[完整状态接口](http://127.0.0.1:8000/api/state) 返回控制台状态，`POST /upload` 是上传入口。端口有更改时同步替换地址。

`simulator/server/config.json` 保存模拟器自己的视频目录设置，当前为 `resources/videos`，相对 `simulator/`；它不是 Qt 客户端的 JSON 配置。

`simulator/docker/docker-compose.yml` 只有 Mosquitto 服务，不包含 Qt、图形、音频或客户端构建。容器内部监听 `1883`，宿主默认只映射 `127.0.0.1:3333 → 1883/TCP`；配置在 `simulator/docker/mosquitto.conf`，是本地匿名测试 Broker，不开放局域网。

不用 Windows 管理脚本时，可以手工管理：

```powershell
docker compose -f simulator/docker/docker-compose.yml -p rm27-simulator up -d broker
docker compose -f simulator/docker/docker-compose.yml -p rm27-simulator ps
# 手工启动的服务由调用者管理。
docker compose -f simulator/docker/docker-compose.yml -p rm27-simulator stop broker
```

环境变量 `RM_SIM_MQTT_PORT` 可覆盖宿主端口，容器仍为 1883，绑定地址仍固定 loopback。Windows 启动器的 `-MqttPort` 只为本次 Compose 调用临时设置该变量，随后恢复。

## 10. Python 直接入口与仅观察网页

已安装模拟器依赖后，可从根目录直接运行：

```powershell
.\simulator\.venv\Scripts\python.exe -m simulator.server.main --check
.\simulator\.venv\Scripts\python.exe -m simulator.server.main --mqtt-host 127.0.0.1 --mqtt-port 3333
.\simulator\.venv\Scripts\python.exe -m simulator.server.main --enable-udp-sender
```

激活虚拟环境后可将解释器路径简写为 `python`；Linux/macOS 使用相应环境中的 Python。模块入口不部署 Broker，也不由 Windows 后台归属脚本管理，前台运行可用 `Ctrl+C` 退出。仅编辑第 1 步场景时可直接运行 `python -m simulator.server.main`，不要求先启 Broker 或 Docker：MQTT 不可用会有日志，网页仍可编辑，不代表报文已送达客户端。

| 模块参数 | 默认值 / 环境变量 | 作用 |
| --- | --- | --- |
| `--check` | 关闭 | 仅检查依赖、资源和配置，不启动监听或工作线程；报告 FFmpeg/Docker 路径 |
| `--probe-mqtt HOST PORT` | 未指定 | 执行 MQTT 3.1.1 CONNECT/CONNACK 探测并退出，成功 0、失败 1 |
| `--target-ip` | `127.0.0.1` / `RM_SIM_TARGET_IP` | 兼容 UDP 状态及网页内置 HEVC 的目标 |
| `--mqtt-host` | `127.0.0.1` / `RM_SIM_MQTT_HOST` | Broker 地址 |
| `--mqtt-port` | `3333` / `RM_SIM_MQTT_PORT` | Broker 端口，1～65535 |
| `--web-host` | `127.0.0.1` / `RM_SIM_WEB_HOST` | Web 绑定地址 |
| `--web-port` | `8000` / `RM_SIM_WEB_PORT` | Web 端口，1～65535 |
| `--current-robot-id` | `1` / `RM_SIM_CURRENT_ROBOT_ID` | 与 Windows 脚本相同的 12 个当前机器人 ID |
| `--enable-receiver` | 关闭 | 兼容 UDP 控制帧接收 |
| `--enable-udp-sender` | 关闭 | 额外发送兼容 UDP 状态 |

显式模块参数优先于对应环境默认值。Windows 管理脚本会显式传入自己的地址/端口参数；不要用模块环境变量替代脚本参数来推断其启动结果。

观察网页时，基础表改值后离开输入框应用；自身弹量、静态/动态等表单点击对应发送按钮保存。切换机器人后应显示该机器人的状态。P-003 类型展示和 P-002 数组含义按[09 问题记录](09_Open_Questions.md)及[11 架构](11_Architecture.md)中的限定约定，不因网页工具仍存在而扩大实现范围。

## 11. 离线检查、冒烟检查与协议生成

### 客户端和模拟器共用基础数据

第 1 步使用 CTest 离线协议检查，不依赖 Qt Test，也不要求 CI/CD。

```powershell
# 默认先构建 Debug，再做本步检查；需已安装模拟器 Python 依赖。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-basic-data.ps1

# 已构建对应配置时可跳过构建。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-basic-data.ps1 -SkipBuild
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-basic-data.ps1 -Configuration Release -SkipBuild

# 只检查模拟器基础负载及网页事件处理。
.\simulator\.venv\Scripts\python.exe -m simulator.tools.check_base_data
```

`check-basic-data.ps1` 参数只有 `-Configuration Debug|Release`（默认 Debug）和 `-SkipBuild`。它依次运行 CTest 的 `protocol_basic`、`tests/check_basic_data.py` 的 Python/C++ 双向检查和模拟器基础检查，使用对应缓存中的 Qt、编译器、CTest 路径及 `RM27_ProtocolCheck.exe`，成功返回 0，失败返回 1。

检查覆盖五类消息的离线编码/解码、存在性和边界、红蓝映射、P-002 顺序、P-003 类型及角色、模拟器实际编码负载、机器人切换、5/10/1 Hz 周期和网页事件回执；不建立 Qt MQTT 连接，不要求 Broker。完整范围与历史实际结果见[13 进度记录](13_Progress_Log.md)，不能据此记为客户端网络接收或官方设备验证。

### Qt 五类 MQTT 接收检查

```powershell
# 可选检查依赖，仅供隔离测试，不改变生产 Broker 部署。
.\simulator\.venv\Scripts\python.exe -m pip install -e "simulator[test]"

# 默认先构建，再执行会话状态检查、隔离 Broker/模拟器/真实 Qt-QML 检查。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-mqtt-receive.ps1

# 已构建时跳过编译；正式记录默认使用100次启停。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-mqtt-receive.ps1 -SkipBuild
```

参数为 `-Configuration Debug|Release`（默认 Debug）、`-SkipBuild`、`-Cycles 1..1000`（默认 100）。脚本先运行 CTest `basic_session` 和 `config_save`，再在本机随机端口启动临时 AMQTT、正常模拟器服务和真实 Qt/QML 检查进程。脚本通过网页同用的 Socket.IO 事件设置红蓝机器人血量，检查协议字节、缺失/零、身份、时效和重复启停。另一个隔离场景保持同一 Qt 进程，停启同端口 Broker，检查五值清空、连续退避、重订阅耗时、身份恢复、停止取消及该连接的业务发布数。

已构建后，在 Windows 桌面运行以下专项检查。它通过 `run.ps1` 打开实际产品窗口，操作下拉框和保存按钮，检查旧文件、保存失败、同窗启动与新进程重开。它使用隔离 Broker 和独立字节样本，输出 `logs/check-profile-时间/summary.json`、逐连接报文和窗口读数。Debug 构建可省略 `--configuration Release`。

```powershell
.\simulator\.venv\Scripts\python.exe .\tests\check_receiver_profile.py --configuration Release
```

输出证据保存在 `logs/check-mqtt-时间/`，包括 `summary.json`、Qt状态JSONL、MQTT负载、故障报文、服务日志和实际 QML 截图；失败时保留 `failure.txt`。脚本只关闭自身临时资源，不接管用户已有服务；AMQTT 结果不能代替生产 Mosquitto Docker 部署或官方设备验证。通过结论须读取实际退出码和证据，并写入13。

### 基础模块生成与漂移检查

```powershell
.\simulator\.venv\Scripts\python.exe -m simulator.tools.release.generate_base_protobuf --check

# 修改共享 schema 后才重新生成基础模块，需 protoc 29.3。
.\simulator\.venv\Scripts\python.exe -m simulator.tools.release.generate_base_protobuf
```

基础生成器要求完整源码中的 `libs/protocol/proto/rm27_base.proto`，输出 `simulator/protocol/rm27_base_pb2.py`，固定使用 `libprotoc 29.3`；支持 `--protoc <可执行文件>` 和 `--repo-root <仓库目录>`。`--check` 仅比较生成结果，不写文件；错误版本不会覆盖提交文件。发布 wheel 可使用已生成模块，重新生成或漂移检查仍需完整仓库。源码组织和唯一 schema 位置见[11 架构](11_Architecture.md)。

### 保留的旧版协议工具

```powershell
.\simulator\.venv\Scripts\python.exe -m unittest discover -s simulator/tools/release/tests -t . -p "test_*.py" -v
.\simulator\.venv\Scripts\python.exe -m simulator.tools.release.check_sim_protobuf_runtime

# 只在维护保留 schema 时使用，与基础模块生成器分开。
.\simulator\.venv\Scripts\python.exe -m simulator.tools.release.generate_sim_protobuf
.\simulator\.venv\Scripts\python.exe -m simulator.tools.release.check_sim_protobuf_runtime
```

兼容检查会检查生成版本、两份依赖声明、pb2 真实导入和重新编译后的 descriptor 语义，不只检查能否 import；需要匹配生成代码/依赖契约的 `protoc`。保留模块当前要求 Protobuf 从 6.33.2 起且同一 6.x 主版本。生成器先在临时目录生成并检查版本，旧 `protoc` 不覆盖提交的 pb2，输出直接写到 `simulator/protocol/robomaster_pb2.py`，不用手动移动。生成器和兼容检查均支持 `--project-root <独立模拟器目录>`，生成器还支持 `--protoc <可执行文件>`。这是保留 2026 工具的维护检查，不代表所有业务已符合 2027。

### 独立模拟器通信冒烟

```powershell
# 安装可选测试依赖；不改变生产 Broker 部署。
.\simulator\.venv\Scripts\python.exe -m pip install -e "simulator[test]"

# 默认使用临时 AMQTT 和随机 loopback 端口。
.\simulator\.venv\Scripts\python.exe -m simulator.tools.smoke_test

# 显式复用真正已启动的 Broker，例如本机 Mosquitto。
.\simulator\.venv\Scripts\python.exe -m simulator.tools.smoke_test --mqtt-host 127.0.0.1 --mqtt-port 3333

# 只运行标准库 UDP 检查。
.\simulator\.venv\Scripts\python.exe -m simulator.tools.smoke_test --udp-only
```

默认冒烟用真实 MQTT 协议收发，但临时 AMQTT 不是生产 Broker 替代，也不证明 Mosquitto Docker 部署通过。显式外部 Broker 模式才对该地址执行独立订阅、上行回写和 UDP/HTTP 冒烟。工具回收自己创建的临时服务并清理临时上传文件；这些仍是独立模拟器检查，不是 Qt 数据接收、实际视频解码或官方接口验证。

## 12. VS Code、其他平台和部署

VS Code Task Buttons 扩展 ID 为 `spencerwmiles.vscode-task-buttons`。`.vscode/settings.json` 定义按钮，`.vscode/tasks.json` 定义实际命令，均不保存本机 Qt/MinGW 安装路径。当前仓库没有 `.vscode/extensions.json`；其他电脑需要自行安装或启用该扩展，不以旧文档中的“已有推荐文件”为准。

打开仓库文件夹后，状态栏提供：

- **构建**：选择 Debug / Release，调用 `scripts/build.ps1`。
- **运行**：选择 Debug / Release 和正式 / 模拟模式，调用 `scripts/run.ps1`，自动先构建，不附加调试器。“模拟”现在连接外部 MQTT；`preview` 心跳通过命令行入口启动。
- **裁判模拟器**：安装依赖、只启 Broker、普通启动、启动加 UDP、启动加视频、离线检查、运行检查、停止、停止并保留 Broker，共 9 个入口。视频输入路径仍相对 `simulator/`。

`Ctrl+Shift+B` 默认构建 Debug；命令面板的 `Tasks: Run Task` 可选择具体任务。按钮未显示时检查扩展是否启用，执行 `Developer: Reload Window`，也可直接运行任务或本页脚本。按钮只调用原脚本，模拟器不加入 Qt 编译。

当前公共客户端预设针对 Windows MinGW。Linux/macOS 可直接使用 CMake，无须 PowerShell：

```sh
cmake -S . -B build/local -G Ninja -DCMAKE_BUILD_TYPE=Debug -DCMAKE_PREFIX_PATH=/path/to/Qt
cmake --build build/local
./build/local/bin/RM27_Client
```

这些是源码开发方法，本轮未在其他平台运行验证。复制客户端到其他电脑前，还要使用 Qt 平台部署工具收集 DLL、插件及 QML 依赖；运行脚本不代替部署，能在开发机打开也不等于发行包或目标电脑验收通过。后续部署和实车任务见[06 开发路线](06_Development_Roadmap.md)，已有结果见[13 进度记录](13_Progress_Log.md)。

## 13. 常见失败怎样排查

| 现象 | 先检查什么 |
| --- | --- |
| 客户端构建提示缺用户预设或找不到工具 | 检查 `CMakeUserPresets.json` 是否存在、两个 local 预设是否各唯一、四个绝对路径及所需文件是否真实存在 |
| 链接 exe 失败，或脚本提示客户端正在运行 | 关闭对应 Debug/Release 客户端窗口；避免同一版本并行构建 |
| 首次 CMake 配置下载失败 | 检查固定归档缓存和网络；不能改成其他版本凑过。离线使用精确版本源码可设置 `FETCHCONTENT_SOURCE_DIR_ABSEIL` / `FETCHCONTENT_SOURCE_DIR_PROTOBUF` / `FETCHCONTENT_SOURCE_DIR_PAHO_MQTT_C`，见 `cmake/Protobuf.cmake`、`cmake/PahoMqtt.cmake` |
| `-SkipBuild` 提示无构建、缓存缺项或缓存工具不存在 | 对应配置需要完整 exe/缓存；确认当前工具路径后重新构建，换工具链使用新构建目录 |
| 客户端配置报错 | 检查 JSON、必填 mode、字段名称、类型和数值范围；确认 `-ConfigFile` 会覆盖 `-Mode`，改文件后重启 |
| 日志路径错误或不可写 | 先看“运行信息”中的实际路径；检查显式绝对目录、相对路径基准和覆盖顺序，必要时用 `-LogDirectory logs` |
| 模拟器提示环境或资源缺失 | 先安装专用 `.venv`，再离线检查；已有环境不会因 `-Python` 自动更换 |
| Web 端口被占用 | 启动器直接报错，不结束其他程序；选择如 `-WebPort 8001`，运行检查和浏览器地址用相同端口 |
| 无法启动 Broker | 确认目标地址能完成 MQTT 握手；本地需要创建 Broker 时再检查 Docker/Compose/daemon，远程失败不会自动换成本地 |
| 运行检查失败但只有 Broker 在运行 | 使用 `check.ps1 -Runtime -BrokerOnly`，避免把缺 HTTP 服务当 Broker 故障 |
| 网页显示在线但客户端数字没跟着变 | 网页在线只代表 Socket.IO；检查 health 的 `mqttConnected`、客户端选择 simulation、双方 Broker 地址/端口与当前机器人 ID 相同；再看五类订阅和逐Topic状态。preview 心跳不读取外部模拟器 |
| 客户端一直显示“等待重连” | 按界面原因检查地址、端口和 Broker 的订阅授权，恢复服务后保持客户端开启。如果已手动停止，点“启动数据源” |
| 显示“连接配置未加载”并提示 seat 错误 | 核对顶层 `seat` 是否为字符串 `infantry` 或 `unspecified`，也可以省略该项。修正后重启。配置错误期间启动按钮禁用 |
| 五类订阅就绪却一直无数据 | 检查发布者是否发送实时消息。只收到保留包时继续等待。核对模拟器当前机器人与客户端配置 ID 是否一致，并确认新的静态身份已到达 |
| 停一个Topic后相关数字消失 | 这是逐消息过期提示；恢复对应新报文后恢复。其他Topic应保持自己的时效，不把整个Broker等同于某条消息在线 |
| MQTT检查脚本缺Python模块或没有检查产物 | 安装 `simulator[test]`；先构建对应配置生成 `RM27_MqttCheck.exe` 和会话检查器，再运行 `check-mqtt-receive.ps1 -SkipBuild`。查看打印的证据目录定位失败层次 |
| 视频发送器停止、有效包一直为 0 | 查看网页“图传控制”的停止原因或命令行错误，核对 FFmpeg、可读视频文件、目标地址与端口。源损坏或编码器无帧输出时发送停止，换有效文件后可重试。接收侧的“运行信息”可区分绑定失败、等待首包和已收包 |
| 工作区提示已有归属进程，或停止失败 | 先用停止脚本并查看 `.runtime` 日志；不要删除 `state.json`，不要按进程名或端口结束其他程序。无法确认状态时保留记录供重试 |
| 协议生成失败或版本不匹配 | 基础生成使用 protoc 29.3，保留旧模块遵守自己的生成/运行时契约；不要手工改 pb2 或复制另一模块顶替 |

排查后区分“命令成功”“独立模拟器业务检查通过”“Qt 端到端通过”“官方设备通过”。每次实际检查将版本、命令、观察结果和未验证范围写入[13 进度记录](13_Progress_Log.md)；若发现的是规则或协议原文缺失/冲突，更新[09 问题记录](09_Open_Questions.md)，不以运行说明中的成功示例覆盖未决状态。
