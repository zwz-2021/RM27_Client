# 移植清单及改动边界

## 固定来源

- 上游：[ClearWei/RM26_Client](https://github.com/ClearWei/RM26_Client)，`main` 于本次扫描时的 commit `e291f2f65f5a5924509e4e2fe1b148ff9d4b24af`。
- 从该提交的 Git 对象归档读取，不使用本地上游工作区中可能存在的未提交文件。逐文件原始 SHA-256、原位置与迁移位置见 `UPSTREAM.json`。
- 保留上游模拟器版本0.1.0及2026协议；未声明2027正式协议兼容。原 schema、pb2、比赛引擎与Web静态素材完整保留。

## 逐项清单

| 项目 | 迁移结果 |
| --- | --- |
| 全部 `sim/server/` | 移入 `server/`；原main事件与业务处理搬入 `app.create_app`，CLI与生命周期分开，导入不启动网络 |
| 全部 `sim/server/static/` | 原样保留控制台、Vue、Socket.IO、地图、CSS、JS与各许可证 |
| 比赛状态及自动赛事演示 | 保留StateManager业务与MatchSimulationEngine；仅增加worker停止和资源回收 |
| MQTT双向 | 保留全部发布topic、频率、Protobuf编码及原上行命令处理；修复包内pb2导入 |
| UDP状态与控制 | 保留原简化状态帧和完整CRC控制帧；可与MQTT同时发送，接收单独开关 |
| HEVC UDP视频 | 保留Web VideoStreamer与独立tools/video_sender.py的编码和分片算法，端口3334 |
| H.264 MQTT工业相机 | 保留原编码器选择、Annex-B切片、packetId与CustomByteBlock封装 |
| 视频管理 | 配置、上传、视频目录统一在simulator内；支持Windows跨盘自定义目录；附合成测试视频生成工具 |
| Protobuf | 原src/network/proto/robomaster.proto移至protocol/；原robomaster_pb2.py保留字节；生成和完整兼容检查工具与测试一起迁入 |
| 原 `sim/tests/` | 全部保留；只适配namespace、目录和Bash测试平台入口，保留原测试断言 |
| 原工具相关测试 | 保留两个release工具测试模块，增加旧生成器不得覆盖pb2及移植相关行为测试 |
| 独立Broker | 仅Mosquitto的Compose服务，localhost3333→内部1883；不复制Qt客户端Compose |
| Windows启动管理 | scripts/start.ps1、stop.ps1、check.ps1；实例、PID/启动时间/路径、容器ID/标签归属校验 |
| Bash启动管理 | 保留原run_sim.sh参数与启动契约；工具、默认视频、Compose及日志路径内部化 |
| 许可证与素材来源 | 保留MIT、vendor许可证、上游素材/第三方声明与地图授权台账 |
| Qt隔离 | 不改apps/client、libs、根CMake/presets、原build/run脚本或VS Code按钮 |

## 有意保留及必要适配

业务规则、命令语义、消息编号、MQTT topic、视频编码和分片继续来自上游，不另写Demo。原主入口中的事件处理函数机械搬入工厂后，由原StateManager、MatchSimulationEngine、MQTTPublisher及视频组件处理。增加的代码用于路径、配置、进程生命周期、部署和可验证性。

对上游行为的必要变化：

1. 命名空间从顶层 `server`/`sim.server` 统一为 `simulator`，不依赖兄弟RM26仓库。
2. MQTT默认值统一3333；UDP只有显式开启才发送，不在Broker失败后隐式切换协议。
3. Web根静态路由放到API之后，避免原顺序让上传被静态路由截获；上传路径支持Windows分隔符和跨盘视频目录。
4. 将原导入时启动连接/线程改成服务lifespan，正常退出、启动失败和视频子进程有对应回收。
5. Broker仅本目录Compose部署；复用Broker不取得停止权，停止成功后释放旧归属记录。无法确认Docker状态时保留记录并报错。
6. Protobuf生成先写临时目录并核对现有版本契约，拒绝用旧protoc覆盖上游pb2；兼容检查仍保留descriptor语义比较。
7. 上游未公开的本地视频不复制入仓库；`tools/create_test_video.py`可用FFmpeg生成测试片段到本目录。

这些变化不引入任何Qt链接依赖。客户端当前的外部通信入口是后续独立开发事项，不是本模拟器的运行前提。

## 测试和环境边界

实际验证结果、版本、完整命令及没有执行条件的项目见 [VALIDATION.md](VALIDATION.md)。AMQTT只供临时隔离测试，不替代部署要求中的Mosquitto容器；无Docker不能声明Compose容器已运行，无FFmpeg不能声明真实HEVC/H.264视频画面已验证。

## 提交和回滚

本次改动只在 `simulator/`，独立提交不包含Qt源代码、原脚本、运行日志、虚拟环境或上传文件。回滚该提交即可撤销移植，不需要恢复客户端构建配置。回滚源码前如有正在运行的服务，请先执行 `simulator/scripts/stop.ps1`；独立手工部署的Broker按README的Compose命令管理。

## 新增和修改文件

以下文件均属于 `simulator/`；原仓库中修改的只有原来的README、server/__init__.py与server/main.py，其余为新增。

- `simulator/.gitattributes`
- `simulator/.gitignore`
- `simulator/.python-version`
- `simulator/LICENSE`
- `simulator/MIGRATION.md`
- `simulator/README.md`
- `simulator/UPSTREAM.json`
- `simulator/UPSTREAM_ASSET_LICENSES.md`
- `simulator/UPSTREAM_THIRD_PARTY_NOTICES.md`
- `simulator/VALIDATION.md`
- `simulator/__init__.py`
- `simulator/docker-compose.yml`
- `simulator/docker/mosquitto.conf`
- `simulator/licenses/upstream-public-assets.json`
- `simulator/protocol/robomaster.proto`
- `simulator/pyproject.toml`
- `simulator/requirements.txt`
- `simulator/resources/videos/README.md`
- `simulator/robomaster_pb2.py`
- `simulator/run_sim.sh`
- `simulator/scripts/__init__.py`
- `simulator/scripts/check.ps1`
- `simulator/scripts/common.ps1`
- `simulator/scripts/process_host.py`
- `simulator/scripts/start.ps1`
- `simulator/scripts/stop.ps1`
- `simulator/server.py`
- `simulator/server/__init__.py`
- `simulator/server/app.py`
- `simulator/server/config.json`
- `simulator/server/crc.py`
- `simulator/server/hevc_annexb.py`
- `simulator/server/industrial_camera_streamer.py`
- `simulator/server/main.py`
- `simulator/server/match_simulation_engine.py`
- `simulator/server/mqtt_publisher.py`
- `simulator/server/proto/__init__.py`
- `simulator/server/protocol.py`
- `simulator/server/state_manager.py`
- `simulator/server/static/app.js`
- `simulator/server/static/index.html`
- `simulator/server/static/map_geometry.js`
- `simulator/server/static/minimap_bg.png`
- `simulator/server/static/style.css`
- `simulator/server/static/vendor/LICENSE.socket.io-4.5.4.txt`
- `simulator/server/static/vendor/LICENSE.vue-2.7.14.txt`
- `simulator/server/static/vendor/socket.io.min.js`
- `simulator/server/static/vendor/vue.min.js`
- `simulator/server/udp_receiver.py`
- `simulator/server/udp_sender.py`
- `simulator/server/video_streamer.py`
- `simulator/tests/__init__.py`
- `simulator/tests/test_application.py`
- `simulator/tests/test_lifecycle.py`
- `simulator/tests/test_map_geometry.js`
- `simulator/tests/test_match_simulation_engine.py`
- `simulator/tests/test_protocol_contract.py`
- `simulator/tests/test_run_sim_contract.py`
- `simulator/tests/test_video_sender.py`
- `simulator/tests/test_windows_scripts.py`
- `simulator/tools/__init__.py`
- `simulator/tools/create_test_video.py`
- `simulator/tools/release/__init__.py`
- `simulator/tools/release/check_sim_protobuf_runtime.py`
- `simulator/tools/release/generate_sim_protobuf.py`
- `simulator/tools/release/tests/__init__.py`
- `simulator/tools/release/tests/test_check_sim_protobuf_runtime.py`
- `simulator/tools/release/tests/test_generate_sim_protobuf.py`
- `simulator/tools/smoke_test.py`
- `simulator/tools/video_sender.py`
