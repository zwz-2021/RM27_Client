# 模拟器脚本命令说明

本目录提供独立裁判模拟器的 Windows 安装、启动、检查和停止命令，兼容 Windows PowerShell 5.1 与 PowerShell 7。以下示例均从 **RM27_Client 仓库根目录**执行。

脚本根据自己的位置定位项目，因此也可以从其他目录通过脚本的绝对路径调用。命令中的 `-ExecutionPolicy Bypass` 只作用于本次 PowerShell 进程，不修改系统执行策略。

## 脚本分工

| 文件 | 用途 |
| --- | --- |
| `start.ps1` | 安装 Python 环境，或准备 Broker 并在后台启动模拟器、可选视频发送器 |
| `check.ps1` | 检查 Python/资源和环境可用性；可选检查运行中的 MQTT 与 HTTP |
| `stop.ps1` | 按归属记录停止本项目脚本创建的进程和 Broker |
| `common.ps1` | 供上述脚本调用的公共函数，不作为日常命令入口 |
| `process_host.py` | 后台 Python 进程宿主，负责脱离调用终端并管理自己的 Windows 子进程，不作为日常命令入口 |

Python 依赖安装在 `simulator/.venv/`。独立 Broker 配置位于 `simulator/docker/docker-compose.yml`，只有 Mosquitto 服务，默认映射 `127.0.0.1:3333 → 容器1883/TCP`。

## 首次安装和检查

需要 Python 3.11 或以上。没有现成 Broker 时，启动流程还需要可用的 Docker Desktop 与 Compose；真实视频发送需要 FFmpeg。

```powershell
# 创建专用虚拟环境并安装 Python 依赖；安装完成后退出，不启动服务。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -Install

# Python 不在 PATH 时，在首次创建虚拟环境时指定解释器。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -Install -Python "C:\Python311\python.exe"

# 离线检查 Python 依赖与资源，报告 Docker、FFmpeg 的可用情况。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1
```

`-Install` 是独立安装操作，即使同时传入其他启动参数，也会在安装后退出。已有 `.venv` 时沿用该环境，`-Python` 只用于创建缺失的环境，不替换已有解释器。无需手动激活虚拟环境。

**离线检查成功不表示 Docker、FFmpeg 或通信链路全部就绪。** 当前 `check.ps1` 在缺少 Docker、Docker daemon、Compose 或 FFmpeg 时会输出提示；这些提示本身不让离线检查返回失败。缺少模拟器 Python 环境、依赖或必要资源会返回失败。

## 四类启动模式

### 1. 只有 Broker

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -BrokerOnly
```

只准备或复用 Broker，不启动 Python 模拟器、Web 页面或视频发送器；此模式不要求先安装模拟器虚拟环境。

### 2. Broker + 模拟器

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1
```

启动后访问 [Web 控制台](http://127.0.0.1:8000)。命令在服务就绪后返回，服务继续在后台运行。自动赛事演示默认空闲，视频也不会随服务启动而自动推流，可在 Web 控制台中操作。

### 3. Broker + 模拟器 + UDP 状态发送

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -EnableUdpSender
```

同时使用 MQTT 与 UDP 状态发送。UDP 状态默认发往 `127.0.0.1:3333/UDP`，不是视频。需要同时接收兼容 UDP 控制帧时，再传入 `-EnableReceiver`：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -EnableUdpSender -EnableReceiver
```

UDP 接收默认绑定本地 `127.0.0.1:3333/UDP`。测试客户端若也绑定该本地 UDP 端口，应先调整测试安排，不能把接收器开关当作客户端连接开关。

### 4. Broker + 模拟器 + HEVC UDP 视频发送

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -VideoFile resources/videos/testdemo.mp4
```

`-VideoFile` 会额外启动独立的 `simulator.tools.video_sender`，将文件编码为 HEVC 并发送到目标 `3334/UDP`。它需要 FFmpeg，输入文件必须已存在。

**视频相对路径以 `simulator/` 为基准**，因此上例对应 `simulator/resources/videos/testdemo.mp4`；也接受带引号的绝对路径。上游没有随公开源码提供实际测试录像，可放入自己的测试文件，或按模拟器主 README 使用测试视频生成工具。

普通启动后，也可以通过 Web 上传、选择视频，再开启内置 HEVC 图传或 H.264 工业相机。`-VideoFile` 是独立 HEVC 进程入口；同一目标的 HEVC 测试请选择一个发送入口，避免混合两路帧号。H.264 工业相机通过 MQTT `CustomByteBlock` 发送，不占 UDP 视频端口。

仅启动独立视频发送器及 Broker、跳过 Web 服务时使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -VideoOnly -VideoFile resources/videos/testdemo.mp4
```

`-VideoOnly` 必须和 `-VideoFile` 一起使用。这种模式仍会准备或复用 Broker，但不启动状态服务，因此 `-EnableUdpSender`、`-EnableReceiver` 没有可作用的状态服务，不应与此模式混用。

## start.ps1 参数

| 参数 | 默认值 | 实际作用 |
| --- | --- | --- |
| `-Install` | 关闭 | 只创建/安装 `.venv`，完成后退出 |
| `-Python <路径或命令>` | `python` | 创建缺失虚拟环境时使用的 Python 3.11+ 解释器 |
| `-BrokerOnly` | 关闭 | 只准备 Broker，不启动模拟器/视频 |
| `-WebPort <端口>` | `8000` | 本地 Web/Socket.IO 服务端口，范围1～65535 |
| `-MqttHost <地址>` | `127.0.0.1` | 要连接或复用的 Broker 地址 |
| `-MqttPort <端口>` | `3333` | Broker 的宿主端口，范围1～65535；本次 Compose 调用使用同值 |
| `-TargetIP <地址>` | `127.0.0.1` | UDP 状态和 HEVC 视频的发送目标，不改变 Web 或 Broker 的监听地址 |
| `-CurrentRobotId <ID>` | `1` | 当前机器人视角；接受1～7及101～107，后者为蓝方视角 |
| `-EnableUdpSender` | 关闭 | 在 MQTT 之外同时发送兼容 UDP 状态 |
| `-EnableReceiver` | 关闭 | 启用兼容 UDP 控制帧接收 |
| `-VideoFile <文件>` | 未指定 | 开启独立 HEVC UDP 视频发送；相对路径以 `simulator/` 为基准 |
| `-VideoOnly` | 关闭 | 不启动 Web/状态服务；必须同时指定视频文件 |

`-BrokerOnly` 不能与 `-VideoOnly`、`-VideoFile`、`-EnableUdpSender`、`-EnableReceiver` 组合。安装操作优先于这些启动组合校验。

更改 Web/Broker 端口及机器人视角：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -WebPort 8001 -MqttPort 1883 -CurrentRobotId 101
```

复用指定的远程 Broker，并向指定测试客户端发送 UDP 状态：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -MqttHost 192.168.1.20 -MqttPort 1883 -TargetIP 192.168.1.30 -EnableUdpSender
```

启动前会执行真正的 MQTT CONNECT/CONNACK 握手。能握手的已有 Broker 会被复用，不会取得其停止权。远程 Broker 无法握手时直接失败，不会用本地 Broker 替代；本地端口被非 MQTT 程序占用时也直接失败。已运行的 Compose Broker 不会为了本次参数被重建或改端口。

## check.ps1：检查环境与正在运行的服务

```powershell
# 离线检查，不启动模拟器或 Broker。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1

# 检查默认 Broker 的 MQTT 握手与 Web HTTP 健康接口。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1 -Runtime

# 只有 Broker 时，跳过 Python/资源和 HTTP 检查，只检查相应环境信息与 MQTT。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1 -Runtime -BrokerOnly

# 与前面的自定义端口启动参数对应。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1 -Runtime -WebPort 8001 -MqttPort 1883
```

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `-Runtime` | 关闭 | 额外检查真实 MQTT 握手；非 BrokerOnly 模式还检查HTTP健康接口 |
| `-BrokerOnly` | 关闭 | 跳过模拟器 Python/资源检查和HTTP健康接口 |
| `-WebPort <端口>` | `8000` | 要检查的本地HTTP端口 |
| `-MqttHost <地址>` | `127.0.0.1` | 要检查的Broker地址 |
| `-MqttPort <端口>` | `3333` | 要检查的Broker端口 |

成功返回 `0`；Python/资源检查失败，或启用 `-Runtime` 后 MQTT/HTTP 检查失败，返回 `1`。参数无效、脚本异常也会返回非零。脚本不自动安装依赖，也不启动或停止服务。

运行检查验证的是 Broker 可握手和HTTP健康接口可访问，不检查每个topic的业务内容、视频解码画面或Qt客户端显示。只开 Broker 时应加 `-BrokerOnly`，否则缺少HTTP服务会让运行检查失败。

## stop.ps1：停止本项目管理的服务

```powershell
# 停止本项目记录的模拟器/视频进程，并停止自己新建和记录的Broker。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\stop.ps1

# 只停止模拟器/视频，保留Broker。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\stop.ps1 -KeepBroker
```

`-KeepBroker` 是此脚本唯一的自定义参数。成功返回 `0`；无法停止某个归属资源时返回非零并保留必要记录，供后续重试。

停止前会核对进程的 PID、启动时间和可执行文件路径；对于 Web 服务，还会核对HTTP实例标识并优先使用本机令牌请求正常退出。必要时只结束再次核对过的归属 PID。Windows JobObject 负责回收该宿主的 FFmpeg 等后代，不按进程名或端口扫描并结束程序。

Broker 停止前核对具体容器ID及Compose项目、服务、配置文件标签。复用的外部Broker和预先存在而未取得归属的容器保持运行；脚本停止自己的Broker后释放归属。Docker状态无法确认时会报错并保留记录，不假报已停止。停止不会执行Compose `down`或删除镜像。

同一工作区已有归属模拟器进程时，普通 `start.ps1` 不会重复启动；切换端口或发送模式前，先运行停止命令。

## 日志与运行记录

运行文件位于 `simulator/.runtime/`，已被Git忽略：

- `state.json`：进程、实例、启动时间、Broker容器等归属信息；也包含本机停止令牌。
- `server-*.log`、`server-*.error.log`：模拟器标准输出和错误输出。
- `video-*.log`、`video-*.error.log`：独立视频发送器输出。
- `host-*.json`：实际Python宿主的身份握手记录。
- `lifecycle.lock`：协调启动/停止操作，防止两个操作同时改写归属状态。

运行时应保留 `state.json`，停止脚本需要据此识别自己的服务。启动失败时先查看命令输出中指向的日志文件；失败回滚只处理本次已创建的资源，无法确认已停止的资源会保留记录。

## VS Code Task Buttons

VS Code 状态栏的“裁判模拟器”按钮组提供安装依赖、只启Broker、普通启动、启动加UDP、启动加视频、离线检查、运行检查、停止、停止并保留Broker共9个入口。视频入口会要求输入文件路径，路径仍以 `simulator/` 为基准。

原有客户端“构建”和“运行”按钮继续使用原来的任务。按钮只负责调用本目录脚本，不会把模拟器加入Qt编译。若没有显示按钮，可通过 VS Code 的“Tasks: Run Task”执行对应模拟器任务，并检查项目所用Task Buttons扩展是否启用。
