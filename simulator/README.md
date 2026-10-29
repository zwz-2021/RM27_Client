# 独立 RM26 裁判系统模拟器

从 [ClearWei/RM26_Client 的 sim/](https://github.com/ClearWei/RM26_Client/tree/e291f2f65f5a5924509e4e2fe1b148ff9d4b24af/sim) 完整移植，固定上游 commit **e291f2f65f5a5924509e4e2fe1b148ff9d4b24af**，上游 Python 项目版本 `0.1.0`。完整脚本参数、运行模式及按钮用法见 [脚本命令说明书](scripts/README.md)。

保留上游 Web 控制台、比赛状态管理、自动赛事演示、MQTT 发布及上行命令、UDP 状态/控制帧、HEVC UDP 图传、H.264 MQTT 工业相机、视频上传与选择、2026 Protobuf 及协议维护工具。这里运行的是上游独立模拟器业务，不使用 Qt 的 MockDataSource，不依赖客户端进程或构建产物。

**协议范围是 RM26/2026 兼容快照，不声明支持 2027 正式协议。** 当前 RM27 Qt 客户端还没有外部通信接收实现；本目录完整提供测试对端，客户端后续接入后可联调。客户端原有内置预览模式保持原行为。

## 环境及首次安装

Windows PowerShell 5.1 / PowerShell 7，Python **3.11+**。Docker Desktop（含 Compose v2）用于独立 Mosquitto；FFmpeg 用于真实 HEVC/H.264 视频。protoc用于协议生成和兼容检查。这些依赖仅属于模拟器，不加入 Qt 的 CMake。

从 RM27_Client 根目录执行（脚本也支持从其他工作目录以绝对路径调用）：

```powershell
# 只安装 Python 依赖到 simulator/.venv，完成后退出。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -Install
# 如 Python 不在 PATH，在安装命令后加 -Python C:\path\to\python.exe。

# 离线检查 Python/资源，并报告 Docker 和 FFmpeg 是否可用。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1
```

保留上游全部 Python 依赖（含 OpenCV/NumPy），见 `pyproject.toml` 与 `requirements.txt`。运行和安装均使用模拟器自己的 `.venv`，不安装到 Qt 环境或修改系统 PATH。缺少 Docker/FFmpeg 时检查会明确报告，Python/资源检查成功不代表容器或视频已验证。

## 四类运行模式

下面四类命令均默认使用 Broker `127.0.0.1:3333`。正常启动会复用能完成 MQTT 握手的已有 Broker；需要创建 Broker 时只使用本目录的独立 Compose 服务。

| 模式 | 启动命令（在项目根目录） | 实际启动内容 |
| --- | --- | --- |
| 只有 Broker | `powershell.exe -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -BrokerOnly` | Mosquitto，或复用已有 Broker |
| Broker + 模拟器 | `powershell.exe -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1` | Broker + Web/状态/MQTT/自动赛事引擎 |
| Broker + 模拟器 + UDP 状态 | `powershell.exe -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -EnableUdpSender` | 同时发布 MQTT 与 UDP 状态，不互相替代 |
| Broker + 模拟器 + 视频发送 | `powershell.exe -ExecutionPolicy Bypass -File .\simulator\scripts\start.ps1 -VideoFile resources/videos/testdemo.mp4` | Broker + 模拟器 + 独立上游 HEVC UDP 视频发送器 |

启动后访问 [Web 控制台](http://127.0.0.1:8000)。自动赛事演示默认空闲，在控制台点击启动；暂停、恢复、速度、红蓝视角和手动控制继续使用上游语义。

视频模式的文件相对路径以 `simulator/` 为基准。上游真实测试视频是 Git 忽略内容，未随公开源码提供，也没有从开发者本地复制赛事录像。可自行上传文件，或先用 FFmpeg 生成无外部素材的片段：

```powershell
.\simulator\.venv\Scripts\python.exe -m simulator.tools.create_test_video
```

也可以普通启动模拟器，再通过 Web 上传/选择视频并启动 **HEVC 图传** 或 **H.264 工业相机**。这是上游内置视频控制能力；`-VideoFile` 则另起保留的 `tools/video_sender.py`。同一目标的 HEVC 测试请选择一种发送入口，避免两路不同帧号混入同一 UDP 视频流。工业相机独立通过 MQTT `CustomByteBlock` 发送，不占 UDP 视频端口。

## 检查与停止

```powershell
# 检查运行中的 HTTP 与真实 MQTT 握手。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\check.ps1 -Runtime
# 只有 Broker 时：check.ps1 -Runtime -BrokerOnly

# 停止脚本自己创建的服务。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\simulator\scripts\stop.ps1
# 只停模拟器/视频，保留脚本创建的 Broker：stop.ps1 -KeepBroker
```

进程日志与归属记录在 `simulator/.runtime/`，已忽略。脚本记录 PID、启动时间和可执行文件身份，停止前重新核对；Web 服务先使用本机令牌请求正常退出。Windows 进程宿主管理自己的视频子进程。脚本只停止自己创建并记录的容器 ID，核对 Compose 项目、服务和配置路径；复用的外部 Broker 不停止。不会按端口或进程名扫描并结束其他程序。Web 端口被占用时直接报错，可用 `-WebPort 8001` 更换。

常用参数：`-MqttHost`、`-MqttPort`、`-WebPort`、`-TargetIP`、`-CurrentRobotId`、`-EnableUdpSender`、`-EnableReceiver`、`-VideoFile`。`-VideoOnly -VideoFile ...` 仅启动视频发送器及所需 Broker，不启动 Web 服务。UDP 接收默认关闭，避免与测试客户端同时绑定同一端口。

## 独立 Broker 部署

`docker/docker-compose.yml` **仅有 Mosquitto 服务**，不包含 Qt 客户端、图形显示、音频或客户端构建。容器内部只监听 `1883`，宿主机默认仅映射 **127.0.0.1:3333 → 1883/TCP**。配置在 `docker/mosquitto.conf`。

不使用 Windows 管理脚本时，可手动部署：

```powershell
docker compose -f simulator/docker/docker-compose.yml -p rm27-simulator up -d broker
docker compose -f simulator/docker/docker-compose.yml -p rm27-simulator ps
# 手工启动的服务由调用者管理：
docker compose -f simulator/docker/docker-compose.yml -p rm27-simulator stop broker
```

用 `RM_SIM_MQTT_PORT` 覆盖宿主端口（容器端口仍为1883）；Windows 启动器的 `-MqttPort` 会为本次 Compose 调用设置它。绑定地址固定为 loopback，不开放局域网。此 Broker 是本地匿名测试配置。

## 地址、协议及文件位置

| 链路 | 默认地址 | 数据 |
| --- | --- | --- |
| Web / Socket.IO | `127.0.0.1:8000` TCP | 控制台、状态、上传与自动赛事操作 |
| MQTT | `127.0.0.1:3333` TCP | RM26 topic + Protobuf，包括上行命令 |
| UDP **状态发送** | 目标 `127.0.0.1:3333` UDP | 上游简化 CmdID/Length 状态帧；显式开启 |
| UDP **控制接收** | 本地 `127.0.0.1:3333` UDP | 上游带 CRC8/CRC16 的控制帧；显式开启 |
| UDP **视频** | 目标 `127.0.0.1:3334` UDP | HEVC，8字节大端帧号/分片/长度头 |
| 工业相机 | 同一 MQTT Broker | H.264 Annex-B 分片 + packetId，封装 `CustomByteBlock` |

UDP状态3333与UDP视频3334是不同用途；MQTT使用TCP3333，不能按相同payload解析。默认只用MQTT，不因Broker不可用而偷偷开启UDP。

- `protocol/robomaster.proto`：唯一人工维护的2026 schema快照；`protocol/robomaster_pb2.py`：生成的Python消息，和schema统一放在协议包中，通过 `simulator.protocol.robomaster_pb2` 导入。原先空的 `server/proto/` 已移除；`server/protocol.py` 则仍用于UDP帧格式，两者职责不同。
- `server/config.json`：模拟器自己的视频目录配置；相对路径以 `simulator/` 为基准。
- `resources/videos/`：上传、本地视频及合成测试片段；不进入Git。
- `tools/video_sender.py`：保留的独立HEVC发送工具，已修复原 `sim.server.hevc_annexb` 导入。
- `GET /api/health`：协议模式、MQTT连接、当前视角和实例标识；Web“链路在线”只表示浏览器Socket.IO已连接。
- `GET /api/state`：完整控制台状态；`POST /upload`：保留上传入口。

## Python 入口

激活模拟器环境后，在仓库根目录运行：

```sh
python -m simulator.server.main --check
python -m simulator.server.main --mqtt-host 127.0.0.1 --mqtt-port 3333
python -m simulator.server.main --enable-udp-sender
python -m simulator.tools.video_sender simulator/resources/videos/testdemo.mp4 127.0.0.1 3334
```

模块入口不自动部署Broker，适合已单独部署的环境。Windows脚本会管理Broker及后台进程，脚本中的视频相对路径以模拟器目录为基准。

## 验证及协议维护

以下命令使用 `simulator/.venv` 的 Python，运行当前保留的协议生成/兼容检查测试及独立通信冒烟：

```powershell
.\simulator\.venv\Scripts\python.exe -m unittest discover -s simulator/tools/release/tests -t . -p "test_*.py" -v
.\simulator\.venv\Scripts\python.exe -m simulator.tools.release.check_sim_protobuf_runtime

# 安装可选测试依赖，不改变生产Broker部署：
.\simulator\.venv\Scripts\python.exe -m pip install -e "simulator[test]"
.\simulator\.venv\Scripts\python.exe -m simulator.tools.smoke_test
# 对真正启动的Mosquitto做独立订阅、上行回写及UDP/HTTP冒烟：
.\simulator\.venv\Scripts\python.exe -m simulator.tools.smoke_test --mqtt-host 127.0.0.1 --mqtt-port 3333
.\simulator\.venv\Scripts\python.exe -m simulator.tools.smoke_test --udp-only
```

默认冒烟临时使用 AMQTT + 随机loopback端口验证真实MQTT协议收发，不是Mosquitto Docker验证或生产替代。外部Broker模式才针对实际部署的Mosquitto；工具会停止自己创建的临时服务并清理临时上传文件。

兼容检查保留上游版本检查、两份依赖声明检查、pb2真实导入及重新编译descriptor语义比对，不仅检查能否import。需要改schema时，用与现有生成代码/依赖契约一致的protoc执行。生成器的输出目标已设为 `protocol/robomaster_pb2.py`，无需手动移动：

```powershell
.\simulator\.venv\Scripts\python.exe -m simulator.tools.release.generate_sim_protobuf
.\simulator\.venv\Scripts\python.exe -m simulator.tools.release.check_sim_protobuf_runtime
```

当前生成代码要求Protobuf `6.33.2` 起、同一6.x主版本。生成器先在临时目录生成并检查版本；旧protoc不会覆盖提交的pb2。本次保留上游pb2字节内容；2027协议变更必须另行确认。

## 许可证

源码保留上游 [MIT](LICENSE)；Vue和Socket.IO许可证保留于 `server/static/vendor/`。地图素材保留原文件及上游授权证据，见固定上游提交的 [素材来源](https://github.com/ClearWei/RM26_Client/blob/e291f2f65f5a5924509e4e2fe1b148ff9d4b24af/ASSET_LICENSES.md)、[第三方声明](https://github.com/ClearWei/RM26_Client/blob/e291f2f65f5a5924509e4e2fe1b148ff9d4b24af/THIRD_PARTY_NOTICES.md) 与本目录的 `licenses/upstream-public-assets.json`。代码的MIT许可不自动替代素材、商标各自的权利声明。
