# 本次移植的验证记录

验证日期：2026-10-28（Asia/Shanghai）。这是实际执行记录；实现存在不等于环境链路已验收。

## 环境

- Windows；Python 3.13.13，专用 `simulator/.venv`（项目最低要求3.11）。
- Protobuf生成文件6.33.2，安装运行时6.33.6。
- protoc 29.3：可生成descriptor做语义比对；不能用于覆盖当前6.33.2生成文件。
- JavaScript地图测试使用Codex本机附带Node.js 24.22.1。系统PATH的Node 12.22.12不支持 `--test`，复跑应使用Node18+。
- Windows脚本通过 `powershell.exe` 实跑；Bash契约通过Windows Git Bash实跑，不是仅做静态语法检查。
- 当前PATH没有Docker、FFmpeg，因此未执行真实Mosquitto容器或真实视频编码/画面检查。

## 已执行并通过

| 验证 | 实际结果与范围 |
| --- | --- |
| Python完整单元发现 | 67项通过，0失败、0错误、0跳过；包括原sim/tests及两个相关release工具测试模块、移植新增测试 |
| 原Bash启动契约 | 原6项全部通过，Windows Git Bash实际执行，无跳过 |
| JavaScript地图几何 | 原3项全部通过 |
| Protobuf兼容检查 | gencode/runtime范围、requirements与pyproject声明、真实pb2导入、canonical descriptor语义比对通过 |
| 旧protoc防覆盖 | 实际调用29.3生成被预期拒绝；原pb2字节未变 |
| 独立MQTT订阅冒烟 | 本机临时AMQTT Broker，独立Paho订阅端真实接收并解码GameStatus、GlobalUnitStatus、RobotDynamicStatus；上行RobotPerformanceSelectionCommand回写HTTP状态与下行Sync |
| UDP接收冒烟 | 实际UDP socket收到上游简化状态帧，验证CmdID/长度；构造CRC8/CRC16命令帧经UDPReceiver收到并记录，线程及socket回收 |
| Web / Socket.IO | HTTP与原静态资源、真实WebSocket连接、血量修改、自动赛事start/pause/resume/stop通过 |
| 视频上传 | 临时目录跨盘（C盘临时视频、D盘项目）实际上传、列出、清理通过；未把文本fixture当作可播放视频验收 |
| 组件生命周期 | State/MQTT/UDP/两类视频worker和socket正常回收；真实阻塞Python子进程模拟读取/探测退出，验证进程回收，不等同FFmpeg编码测试 |
| Windows脚本保护 | MQTT握手、占用端口、复用Broker、PID身份/过期记录、容器标签、Broker归属释放、运行中Broker不重建、未知Docker状态不假报停止、JobObject子进程回收测试通过 |
| 打包 | 独立wheel成功构建；检查schema/pb2、Web、vendor许可证、Docker配置、脚本和工具均随包保存 |
| 上游完整性 | 上游sim全部文件存在；schema、pb2、自动赛事引擎与固定提交原字节一致；地图为实际PNG，未复制LFS占位符 |
| Qt边界 | 原仓库47个受保护已跟踪文件SHA-256逐一相同，包括apps、libs、根CMake/presets、原scripts和VS Code配置 |

Windows真实后台启停另行实跑通过：复用临时AMQTT Broker，start.ps1后台返回、HTTP实例标识匹配、stop.ps1正常退出、归属记录清空，停止后外部Broker仍完成MQTT握手。实际测试了venv redirector与真实Python PID区分、后台调用管道脱离及JobObject后代回收。它验证Windows进程管理及Broker复用，不等同Docker部署。11项Windows脚本行为测试包含在完整Python发现中。

## 没有条件执行／尚未验收

1. **真正的Mosquitto Docker Compose部署与容器健康检查**：没有Docker命令/运行时。已检查仅一个Broker服务、localhost3333映射内部1883和配置结构，并用容器命令桩验证归属逻辑；这些不等同容器实跑。
2. **针对实际Mosquitto的独立订阅**：没有Mosquitto/Docker。当前独立订阅是AMQTT的真实协议收发，不声明已经验证Mosquitto。部署后运行下面的外部Broker冒烟命令。
3. **HEVC/H.264真实编码、发送及解码画面**：没有FFmpeg及媒体接收端；未生成真实测试视频，未声称图传画面通过。FFmpeg进程生命周期与分片工具有测试，业务编码参数保留上游。
4. **当前RM27 Qt客户端端到端显示**：客户端尚未实现外部通信数据源；本次按边界未修改客户端。独立模拟器可测试相同2026协议的接收端，不声明2027正式协议或现有Qt界面联通。

## 可复跑命令

从仓库根目录，使用模拟器自己的Python：

```powershell
.\simulator\.venv\Scripts\python.exe -m unittest discover -s simulator -t . -p "test_*.py" -v
node --test simulator/tests/test_map_geometry.js
.\simulator\.venv\Scripts\python.exe -m simulator.tools.release.check_sim_protobuf_runtime
.\simulator\.venv\Scripts\python.exe -m simulator.tools.smoke_test
.\simulator\.venv\Scripts\python.exe -m simulator.tools.smoke_test --udp-only
powershell.exe -NoProfile -ExecutionPolicy Bypass -File simulator/scripts/check.ps1
```

补齐Docker后：

```powershell
docker compose -f simulator/docker-compose.yml -p rm27-simulator up -d broker
.\simulator\.venv\Scripts\python.exe -m simulator.tools.smoke_test --mqtt-host 127.0.0.1 --mqtt-port 3333
docker compose -f simulator/docker-compose.yml -p rm27-simulator stop broker
```

补齐FFmpeg后，先运行 `python -m simulator.tools.create_test_video`，再按README的第四种模式启动；用匹配的UDP媒体接收器或未来客户端检查HEVC。H.264工业相机在Web单独启动，并检查MQTT CustomByteBlock及接收解码画面。
