# 2026 参考项目与 2027 需求对照

审计日期：2026-11-02。旧项目实际位置是同级 `../RM26_Client`。本轮重新检查源码、QML 引用、编译开关和命令路径，修正此前规划中的哨兵接收、性能同步和“重复定义”误报。本文件记录读到的实现证据，不能作为官方协议依据，也不声称旧客户端当前能够构建、通过实车验收或已经迁移到 RM27。

统一需求、协议覆盖和任务关联分别见 [需求说明](02_Requirements.md)、[协议覆盖](03_Protocol_Coverage.md)、[任务表](07_Task_Backlog.md)。功能名用于与这些表核对；下文 REF 编号只表示历史功能条目，不另建一套需求 ID。

## 1. 审阅范围与判断口径

递归清点旧项目 `src` 下 49 个 `.cpp`、56 个 `.h`、63 个 `.qml`，检查模块、函数、信号、数据绑定及 mock/空实现入口；重点展开阅读 `MainWindow`、`GameData`、网络与视频链、配置、弹窗状态机、输入策略、战术分析、AR、模拟器收发/状态/场景以及发布与验证文档。核对了根 CMake 的实际编译清单、QML QRC 和公开配置。第 8 节列本轮逐路径证据及深读边界；“递归清点”不声称每个文件每一行都已阅读。视觉样式、生成代码、资源二进制、训练数据及每个测试的全部分支没有逐行审阅；没有运行旧项目构建或测试。这里只把已读到的路径记为源码能力，不用旧 README 的“支持”代替实现与验证。

旧项目是 **Widgets 主窗口 + QQuickWidget 加载 QML + C++ 数据中心**；RM27 当前采用 Qt Quick 组合根和 `apps/ + libs/` 分层。可以借鉴功能和边界，不能整体复制巨大 `MainWindow.cpp`、`GameData.cpp`。

处理分类：

- **继承**：保留功能目标，按 RM27 架构重新接入并验证。
- **修改**：功能目标仍适用，但字段、角色、规则或交互必须按 2027 重做。
- **替代**：旧兼容路径由 2027 明确接口取代。
- **舍弃**：不纳入当前正式比赛交付；保留历史审计记录，不删除旧文件。
- **待确认**：缺少当前项目需求或明确适用依据，保持未实现，不阻断其他功能。

## 2. 客户端功能与迁移决定

表中源码路径相对旧项目根目录；链接定位旧项目目录，函数/组件名称用于检索。所有“有实现”都只表示源码路径存在，未把运行结果或官方验收一并认定为通过。

| 历史项 | 读到的功能、入口与边界 | 源码证据 | 2027 处理与理由 |
| --- | --- | --- | --- |
| REF-01 | 应用元数据、全屏启动、字体与屏幕缩放、主窗布局 | [main.cpp](../../../RM26_Client/src/main.cpp)，`MainWindow::initializeLayout/setupFonts/applyPanelResolutionScaling` | 继承启动与适配目标；实现继续用 RM27 的 Qt Quick，不引入 Widgets 混合布局负担 |
| REF-02 | MQTT 3.1.1/Paho：异步连接、订阅、发布、错误分类、有限重试 | [MqttManager.cpp](../../../RM26_Client/src/network/MqttManager.cpp)：`connectToBrokerAsync/subscribe/publish/onConnectCompleted/tryReconnect` | 修改；保持 2027 地址、身份、频率和最高 QoS，重做受控生命周期与订阅就绪状态 |
| REF-03 | 设置面板选择红蓝机器人；client ID 随身份切换；临时错误重连 | [MainWindow.cpp](../../../RM26_Client/src/ui/MainWindow.cpp)：`startServices/restartMqttForRobotType/onMqttSwitchCompleted/scheduleMqttReconnect`；`SettingsPanel.qml` | 修改；2027 不能选择英雄/工程，现场授权不能由客户端下拉框推定；旧会话回调必须隔离 |
| REF-04 | Topic 到 Protobuf、再到 GameData 的收包路由 | [NetworkManager.cpp](../../../RM26_Client/src/network/NetworkManager.cpp)：`subscribeToTopics/processMqttMessage` | 修改；旧表含重复 Event、旧消息和 CustomRobotData；按 2027 全表精确路由，逐字段审计，不通配冒充支持 |
| REF-05 | 官方 MQTT 与旧内部 wrapper/UDP 简化报文并存 | [Protocol.cpp](../../../RM26_Client/src/network/Protocol.cpp)、`NetworkManager::processData/sendData` | 替代；RM27 正式赛事数据走当前协议 MQTT，旧 CmdID+Length UDP 数据回退不作为官方数据线路 |
| REF-06 | TCP 换行 JSON 登录/心跳的 S1 管理器，可由环境变量开启 | [S1ProtocolManager.cpp](../../../RM26_Client/src/network/S1ProtocolManager.cpp)：`sendLoginRequest/sendHeartbeat/processMessage` | 舍弃当前计划的正式依赖；不是本项目固定通信协议接口，不能凭名称推定官方允许。只有另有明确需求与接口依据才单独规划 |
| REF-07 | 比赛阶段、倒计时、暂停、局数、比分、结算结果、结束原因、跨局清理 | [GameData.cpp](../../../RM26_Client/src/core/GameData.cpp)：`applyOfficialGameStateSnapshot/updateGameStatus`；`TopInfoBar/PopupOverlay` | 修改；从 2027 权威字段驱动，不能本地以实时比分提前猜胜负 |
| REF-08 | 全局单位血量、护盾、基地/前哨状态、双方累计伤害 | `GameData::updateGlobalUnitStatus`，`BaseHealthBar/OutpostStatusBadge/TopInfoBar/TabStatsPanel` | 修改；2027 阵容与八项血量顺序重核，不能沿用旧 1/3/6/7 布局 |
| REF-09 | 弹量六槽映射、己敌视角 | `GameData::updateGlobalUnitStatus` 的 `extendedAllyRoster`；`sim/server/mqtt_publisher.py::_global_unit_protocol_robot_ids` | 修改，限 P-002 指定范围沿用 `[1,2,3,4,6,7]` 及蓝方 +100；RM27 保留 2/102 槽位不恢复工程 |
| REF-10 | 后勤经济、累计与周期奖励、兑换允许发弹量 | `GameData::updateGlobalLogisticsStatus/notifyPeriodicRewards`；`TopInfoBar/ExchangePanel/AmmoSupplyPanel` | 修改；旧价格、周期、限额不能照抄；区分允许发弹量、全局累计弹量与实弹库存 |
| REF-11 | 特殊机制、能量机关和飞镖全局信息 | `GameData::updateGlobalSpecialMechanism`、`LeftBottomPanel/EventMessagePanel/MiniMap` | 修改；只显示当前协议真正提供的字段，未知值不填正常状态 |
| REF-12 | 静态机器人身份、连接/在场/存活、等级、性能上限 | `GameData::updateRobotStaticStatus`、文件顶部 `robotTypeFromProtocolId` | 修改；P-003 沿用有效 ID 优先、原始类型后备的来源，但 RM27 未知值不默认步兵；重装替代英雄，2 为保留 |
| REF-13 | 动态血量、热量、经验、底盘/缓冲能量、弹量、脱战及远程许可 | `GameData::updateRobotDynamicStatus`；`LeftBottomPanel/CentralAimingHUD` | 修改；旧代码把底盘能量赋给 `power`，窄化为 uint16，不能当作 RM27 单位/类型依据 |
| REF-14 | 模块状态表、离线转换消息、按角色选择测速模块 | `GameData::updateRobotModuleStatus`；`DamagePanel/ModuleStatusPanel` | 修改；旧代码将单一 armor 值复制为四块装甲、WIFI 为占位，不能宣称逐块真实状态；RM27 按对应字段/位定义重做 |
| REF-15 | 五类伤害统计和比例、复活后清理 | `GameData::updateRobotInjury/resetInjuryStatsOnRespawn`；`DamagePanel.qml` | 修改；保留协议原始分类和总量，显示汇总不丢来源；旧面板 mock 模块数据不能进入正式状态 |
| REF-16 | 位置、雷达高亮、大小地图、红蓝视角及坐标映射 | `GameData::updateRobotPosition/updateRadarInfo`；`MapCoordinateMapper`、`MiniMap/TacticalRadarMap` | 修改；P-001 只在雷达结构内按用户指定模拟器实际发送设计，其他坐标单位/特殊值按 2027 原文 |
| REF-17 | 哨兵路径显示，旧逻辑兼容归一化与分米两种输入 | `GameData::updateSentryPath`；`MiniMap.qml` 的路径绘制 | 修改；2027 MQTT 路径相对起始点、串口另有定义，不能按数值大小猜单位或混用累加算法 |
| REF-18 | 大地图 A/B/I 选择攻击/警戒/防御，点击标记，自动消退 | `MainWindow::handleMiniMapClick/setMiniMapCommandMode`；`MiniMap::addCommandMarker` | 修改；旧 UI 本地先画标记、1.5 秒冷却和 28×15 常数都不是 2027 收发确认依据；使用 MapClickCmd 与对应 MapClickInfo，角色限频分别处理 |
| REF-19 | Event 解析、击杀/结构事件、彩色消息、官方事件弹窗 | `GameData::eventInfo/addSystemMessage/addRobotMessage/recordKill`；`EventMessagePanel/MessageNotificationPanel/OfficialEventPopup/BattleMessageWidget` | 修改；2027 每个 event_id 与 param 解析逐项重核，未知事件保留诊断，不猜业务 |
| REF-20 | Buff 类别/等级/最大时间/剩余时间显示 | `GameData::updateBuff/buffTimedData`；`LeftBottomPanel/EventMessagePanel` | 修改；用权威剩余时间校正，离线/暂停/跨局不保留旧 Buff |
| REF-21 | 判罚、超热/超射速告警、受罚/断连/罚下层、飞镖遮挡切视图 | `GameData::updatePenalty/checkHeatLimit/checkSpeedLimit`；`MainWindow::checkDartHitViewSwitch`；`Punished/Out/Disconnected` | 修改；规则机制必须覆盖，但限制通知范围和时长不足时保留待确认，不能把旧事件发生时间当限制起点 |
| REF-22 | 性能体系选择上行、静态状态回填，设置初始化防误发；专用 Sync 仅订阅未解析 | `SettingsPanel::emitPerformanceSelectionIfReady/applyComboTextSilently`；`MainWindow::onPerformanceSelectionChanged/syncSettingsPanelState`；`NetworkManager::sendRobotPerformanceSelection`；`NetworkManager.cpp:1118` 仅列 Sync Topic | 修改；旧值 3/4 是英雄近战/远程，不迁移；补专用 Sync 接收和 2027 可选条件，送出不等于生效 |
| REF-23 | 17mm/42mm 弹量与远程血量兑换界面、二次确认、快捷键；远程弹量存在被本地策略丢弃的断点 | `ExchangeCommandPolicy.cpp:9`、`ExchangePanel.qml:141/147/164`、`AmmoSupplyPanel`、`MainWindow.cpp:8085` | 修改；旧普通 17mm 参数按 100 整数倍，不可替代 2027 cmd1 参数为 10 的倍数；远程 cmd=5 在旧策略只接受 1/2/6 的入口被拒，界面仍可能本地报成功；逐命令重做权威反馈 |
| REF-24 | 免费/付费复活、读条、金币费用、在线许可、按键防连发 | `RobotRespawn::updateFromStatus`；`MainWindow::tryHandleRespawnShortcut`；`PopupOverlayPolicy` | 修改；旧 `robotIndex=0` 兜底与缺字段缓存策略要按 2027 重做；复活按钮不能自行复活本地对象 |
| REF-25 | 工程科技核心装配难度、开始/确认步骤/退出、状态同步 | `ExchangePanelEngineer::confirmAssemblySelection/sendAssemblyCommandToServer/syncViewFromTechCoreStatus`；`GameData::updateTechCoreMotionStateSync` | **修改为 2027 重装装配业务**；保留通用交互经验，不能继承“工程机器人”身份、收益表和规则。2027 AssemblyCommand/TechCoreMotionStateSync 仍须逐项实现 |
| REF-26 | 英雄部署模式 K/L 长按、待同步状态 | `DeployModePanel.qml`；`NetworkManager::sendHeroDeployMode`；`GameData::updateDeployModeStatusSync` | 舍弃旧消息及英雄专属 UI；不因 1 号 ID 沿用就将其映射为重装部署 |
| REF-27 | 空中支援启动/中断及被针对提示 | `ExchangePanelAerial::sendAirSupportCommandToServer`；`NetworkManager::sendAirSupportCommand`；`GameData::updateAirSupportStatusSync` | 舍弃旧 AirSupportCommand/StatusSync 线路；2027 空中相关功能仅按当前通用命令和规则重做，不照搬旧支援时长/收费 |
| REF-28 | 长按开启能量机关、状态/臂数/平均环数/每组结果 | `RuneInteractionPanel::beginHold/markActivated`；`GameData::updateRuneStatusSync`；`NetworkManager::sendRuneActivate` | 修改；旧本地机会计数、20 秒等常量和模拟 Event 扩展不能默认成为 2027 官方字段 |
| REF-29 | 飞镖目标选择、开闸二次确认、发射、状态回写和次数显示 | `SiloControlPanel::switchTarget/confirmOpen/requestFire/onSiloStatusChanged`；`GameData::requestSiloOpen/requestSiloFire`；`NetworkManager::sendDartCommand` | 修改；2027 目标枚举、窗口、权限、次数按规则，重连不可凭 UI 本地计数还原历史；未同步时不能显示已发射 |
| REF-30 | 哨兵消息已定义并列入订阅，但客户端缺专用状态/结果解析与发送入口；模拟器具备指令效果和结果发布 | `NetworkManager.cpp:1123/1125` 仅订阅；`GameData.cpp:3692` 的 `updateSentryStatus` 为空；旧模拟器 `mqtt_publisher.py:351`、`state_manager.py:1449` | 修改；按 2027 补客户端收发、姿态/强化显示和指挥干预闭环。全 `src` 检索未见专用 `sendSentry*`，不能把 proto、订阅或模拟器效果算成客户端完成 |
| REF-31 | 键鼠位掩码、位移/滚轮、按钮采集，约 13ms 调度、发送统计 | `MainWindow::keyboardMouseBitForKey/handleKeyboardMouseControlKey/flushKeyboardMouseControlFrame`；`NetworkManager::sendKeyboardMouseControl` | 修改；按 2027 最高频率和 int32 范围；旧 13ms 可超过严格 75Hz，不能直接拷贝作为通过证据 |
| REF-32 | 弹窗/战术模式阻断控制、失焦/停止清输入、中和帧 | `MainWindow::isKeyboardMouseControlBlocked/resetKeyboardMouseControlState`；`InputHotkeyPolicy` | 继承目标；控制源授权与本地登录分开，停止/切换/断网不续发旧按下状态，快捷键不得双触发 |
| REF-33 | 主图传 UDP 大端 8 字节头、乱序/重复片重组、超时清理、帧统计 | `VideoReceiver::startListening/processPacket/assembleFrame/cleanupOldFrames` | 修改；2027 包长及有界缓存严格校验，旧实现长度不符仍发解码、单帧/在途内存上限不足，不能整体照搬 |
| REF-34 | FFmpeg 连续 HEVC 解析/解码、参数集与关键帧恢复 | `HevcDecoder::initialize/decode`；`VideoReceiver::markTransportDiscontinuity/decodeAssembledFrame` | 继承算法参考，修改线程/缓冲/关闭策略；当前 MinGW 兼容依赖先集成验证，官方码流仍需现场证据 |
| REF-35 | 视频独立线程、最新帧展示、缩放/帧率、无画面背景与卡顿阶段诊断 | `VideoBackgroundWidget::onTimedImageReceived/paintEvent/playUrl/stopVideo` | 继承目标；RM27 走 Qt Quick 专用帧通道；旧 6 号自动旋转 180° 属旧项目行为，不作为 2027 强制要求 |
| REF-36 | MQTT CustomByteBlock 内 H.264 + 尾包号，英雄工业相机与网格 | `NetworkManager::processMqttMessage(CustomByteBlock)`；`VideoReceiver::feedH264Frame`；`H264AnnexB/H264StreamRecoveryPolicy/H264Decoder`；`HeroVideoWidget` | 待确认/不纳入默认交付；官方只定义字节通道，私有视频格式不自动适用 2027，也不能把第二路视频当标准 UDP 图传 |
| REF-37 | 自定义机器人状态：摩擦轮、拨弹、底盘模式、电容、云台角度 | `NetworkManager::parseCustomByteBlock`、`CustomDataTypes.h`；`CustomUI/GunnerOverlay` 及四个子组件 | 待确认；固定结构体 memcpy 与尺寸识别只是旧私有业务，不擅自加入官方协议；标准 CustomByteBlock 通道本身仍需覆盖 |
| REF-38 | 自动向机器人转发敌方前哨站状态的私有 10 字节包 | `MainWindow::scheduleOutpostForward/flushOutpostForward` | 舍弃当前任务的自动业务；CustomControl 通道按 2027 长度/频率实现，通道内业务须另有明确约定 |
| REF-39 | 准备、自检、倒计时、复活、罚下、暂停弹窗仲裁和去重 | `PopupStateMachine::submitIntent/beginBatchUpdate/clearAll/recomputeActiveLocked`；`PopupOverlay.qml`；`PopupOverlayPolicy` | 继承状态机目标；优先级、输入阻断、跨局/角色清理结合 2027 重新验证 |
| REF-40 | 帮助、按键提示、准星、统计/伤害面板、设置与图层焦点管理 | `MainWindow::setupKeyPanels/eventFilter/restackOverlayLayers`；`HelpOverlayWidget/CentralAimingHUD/TabStatsPanel` | 继承操作体验目标；键位是否相同属项目选择，不伪装规则要求；先业务闭环，再统一正式 UI |
| REF-41 | 语音/BGM、基地受攻击与离线告警、固定时间事件提示、去重 | `MainWindow::setupAudio/playSecondarySound`；`TimedEventRules/RuneVoicePromptTracker`；`BattleMessageWidget` | 修改为可选增强；2026 固定时间表和机会计数不可照抄；核心状态必须有可见提示，音频缺失不能妨碍操作 |
| REF-42 | 结算战报、红蓝胜负动画、统计和可选音效 | `GameResultWidget::setResult/setupAnimations`；`MainWindow::onGameResultReceived/refreshGameResultWidgetStats` | 修改；保留真实结果显示为必需，动画/额外统计为可选，第三方素材/品牌及授权重新核对 |
| REF-43 | JSON 配置查找/校验、文件变化重载、环境变量覆盖 | `ConfigLoader::load`；`ConfigManager::loadConfig/onFileChanged/getEnvOrConfigPort`；`ConfigValidator` | 继承配置校验目标；旧重载不自动重建全部连接，RM27 必须明确应用/重连时机；没有通用 UI 设置持久化实现，不宣称所有滑块会保存 |
| REF-44 | 按时间命名的运行日志、事件时间线、MQTT 原始十六进制录包 | `main.cpp::installRuntimeLogHandler`、`MqttLogger::logRx/logTx/flushBuffer`、`LogFileNaming` | 修改；录包可借鉴，但旧缓冲超过 MAX_BUFFER_SIZE 后只留注释，未硬限制，必须加容量/磁盘失败策略 |
| REF-45 | UDP 每包 8 字节头日志、分阶段收包/组帧/解码/渲染耗时 | `VideoDatagramLogger::formatEntry/logDatagram`；`VideoReceiver/VideoBackgroundWidget` timing 日志 | 继承观测目标；头日志不能重放完整视频；无发送端时钟不能声称端到端延迟 |
| REF-46 | 战术指挥页：资源、机器人列表、大小地图、事件链、视频主/地图主布局 | `TacticalCommandPage.qml`、`TacticalRadarMap` 及 components；`TacticalAnalyzer::updateHeader/updateResources/updateRobotLists/updateRadarData` | 修改/可选增强；基础地图与指挥交互纳入必需，其分析仪表盘按 P2 处理；禁止正式模式缺数据时回退 mock |
| REF-47 | 新鲜度、威胁排序、己方执行能力、决策防抖、预测面板 | `DataFreshnessGuard`、`ThreatRanker::rankTargets/scoreSingle`、`ExecutionFusion::fuse`、`TacticalAnalyzer::updateMainDecision/updatePredictions` | 待确认/P2；这些是经验算法，不是官方需求。保留数据过期提示为必需，评分和预测不列入比赛完成条件 |
| REF-48 | ONNX YOLO 推理、NMS、目标跟踪/预测、AR 框、检测线程 | `YoloDetector::loadModel/detect`、`TargetTracker::update/kalmanPredict`、`AROverlayManager::processFrame`、`AROverlayWidget` | 待确认/P2；依赖模型与算力、授权及队伍需求；不自动加入核心控制，不把推理框当权威机器人位置 |
| REF-49 | 可选 HTTP 开发快照、视频统计/截图、开发钩子；另有普通主窗调试注入键 | `ClientDevHooks.cpp`、`MainWindow.cpp:6953–6985`，CMake `RM26_ENABLE_DEVTOOLS` 默认 OFF | HTTP 工具按开发隔离；普通主窗调试注入舍弃，详第 10 节 |
| REF-50 | 内置 ProtocolSimulator 旧手动造包，自动计时器已不产生数据 | `ProtocolSimulator::simulateGameStage/simulateRobotPunishment/onTimer` | 替代；RM27 内置 mock 仅演示，正式联调使用独立 Python 模拟器，不把血量借作判罚字段 |
| REF-51 | CMake 可选 MQTT/FFmpeg/ONNX、Protobuf 生成、资源检查、CTest | 根 `CMakeLists.txt`、`tests/CMakeLists.txt`、`tools/release`、`cmake/ValidateAssets.cmake` | 修改；固定 RM27 Windows/MinGW 依赖与打包，功能依赖缺失要明确报告，不允许空实现看似正常 |
| REF-52 | Ubuntu Docker/现场启动、可选录屏、音频代理、SSH/监听辅助 | `scripts/rm26-field-*`、`scripts/rm26-recording*`、`tools/mqtt_listen.py/ssh_engine.sh` | Windows 正式交付以现有 PowerShell 方式替代；Linux/Docker 客户端、SSH、录屏为历史/可选，不扩大当前平台范围 |

## 3. 旧模拟器能力及不能当成闭环的路径

| 范围 | 实际阅读证据 | 可参考部分 | 迁移/验证缺口 |
| --- | --- | --- | --- |
| 独立 Web 服务与输入 | `sim/server/main.py` 的 FastAPI、Socket.IO 事件，`static/app.js/index.html` 的状态表单；`state_manager.py` 独立运行 | 状态快照、网页输入、机器人切换、视频开始/停止、日志反馈 | 客户端未启动也应独立运行；网页“提交成功”不等于对应 MQTT 字段已发出；各入口复用同一校验 |
| 周期发布 | `mqtt_publisher.py:596` 的 `start`、`:622` 的 `_publish_loop_5hz`、`:634` 的 `_publish_loop_1hz`、`:676` 的 `_publish_loop_10hz` | GameStatus 5Hz、静态/全局等 1Hz 调度、队伍视角与各发布函数 | `start()` 仅启动 5Hz/1Hz；10Hz 函数为空循环且未启动，动态等为触发式发送，不能说已满足 10Hz。逐消息与 2027 核对频率/QoS；旧 pb2/schema 不自动可信 |
| 通用命令与性能/哨兵/飞镖等处理 | `MQTTPublisher::_on_message` 直接分支处理 cmd_type=3/4，`StateManager::apply_sentry_command/handle_dart_command`、对应状态发布 | 用“命令→状态修改→同步/结果”构造测试场景 | 无 `handle_common_command` 总入口；CommonCommand 1/2/5/6 只有解析而无业务闭环。键鼠、CustomControl、MapClickInfoNotify、AssemblyCommand 均只解析打印后返回，不能说已装配/兑换/标记闭环 |
| 哨兵结果 | `push_sentry_ctrl_result/get_sentry_ctrl_results/publish_sentry_ctrl_result` | 明确业务结果与传输 ACK 分开 | 旧客户端订阅存在不足以证明所有按钮、限频、结果关联都正确 |
| 自动比赛场景 | `MatchSimulationEngine::tick/_timeline_state/_apply_current_frame/_resolve_event` | 暂停、倍速、按时间合成血量/路径/事件、手动覆盖 | 属确定性演示场景，未完整模拟官方物理/经济，旧场景的英雄/工程/空中支援必须修改 |
| 旧 UDP 数据 | `UDPSender::_send_packet` 是 CmdID(2)+Length(2)+Data，无 CRC 的简化格式 | 仅历史调试参考 | 不是 RM27 MQTT 数据协议，不能用该回退替代正式链路验收 |
| 标准主图传 | `VideoStreamer`、`HevcAnnexBFrameExtractor`、UDP `!HHI` | 本地视频转 HEVC，逐帧分片发送 | 旧 MAX_PAYLOAD_SIZE=1464，仅按 MTU 减头，不能代替 2027 明确 1400 字节数据报上限；必须在当前模拟器同步修正 |
| 工业相机 | `IndustrialCameraStreamer` H.264 分片尾加 packetId，通过 CustomByteBlock | 仅私有字节通道参考 | 300 字节私有分片+尾号不是标准 UDP 图传，不能顺手纳入 2027 官方业务 |
| 自动测试 | `sim/tests/test_protocol_contract.py/test_match_simulation_engine.py/test_run_sim_contract.py/test_map_geometry.js`；`tools/release` 检查器 | descriptor、固定 wire、生成漂移、场景/Web/几何检查、资源与配置发布检查 | 本次未执行旧测试；缺故障注入/真实网络/设备证据；测试存在也不等于已注册或通过 |

## 4. 页面与控件清点

以下按实际源码和绑定分类，不把一个装饰子控件重复算作一条独立业务需求。目录中 63 个 QML 均被纳入清点；主窗加载、QRC 和组件引用继续决定是否真的可达。

| 功能组 | 组件清单 | 对应历史项 |
| --- | --- | --- |
| 核心 HUD/状态 | TopInfoBar、LeftBottomPanel、CentralAimingHUD、BaseHealthBar、OutpostStatusBadge、RobotStatusItem、RobotStatsTable、RobotStatsRow、TabStatsPanel、FpsDisplay、AuxiliaryShootingPanel | REF-07 至 REF-15、REF-40 |
| 操作/设置 | SettingsPanel、ActionButton、AmmoSupplyPanel、ExchangePanel、ExchangePanelEngineer、ExchangePanelAerial、DeployModePanel、RuneInteractionPanel、SiloControlPanel | REF-22 至 REF-29、REF-43 |
| 地图/消息 | MiniMap、EventMessagePanel、MessageNotificationPanel、OfficialEventPopup、DamagePanel、ModuleStatusPanel | REF-14 至 REF-21 |
| 阶段/异常浮层 | PopupOverlay、PrepPhasePopup、Countdown、RobotRespawn、BattlePausePopup、Out、Disconnected、Punished | REF-21、REF-24、REF-39 |
| 私有视频/状态 | HeroVideo；CustomUI/GunnerOverlay、FrictionWheelStatus、ChassisModePanel、SuperCapacitorBar、GimbalAngleIndicator | REF-36、REF-37 |
| 战术页面 | TacticalCommandPage、TacticalLargeMapOverlay、TacticalMock、TacticalHeader、ResourceSummaryBar、KeyEventChainPanel、TacticalVideoStage、MainDecisionConsole、TargetRankPanel、TacticalRadarMap、AllyCriticalStatusPanel、PredictionPanel、HologramLockOverlay、TargetInfoCard、TacticalEventPopup | REF-46、REF-47 |
| 战术子控件 | components/HudPanel、BaseHealthWing、RobotStatusRow、RobotListPanel、BattleEventPanel、BattleAnalysisPanel、CameraPreviewPanel、TopLogisticsStrip | REF-46、REF-47 |

`ModuleStatusPanel/Disconnected/Punished` 不在当前 QML QRC 中，且不能仅凭文件存在认定主页面会显示。Widgets 的 HealthBar、HeatRing、Crosshair、RobotStatusPanel/Widget、MiniMapWidget、InfoPanel、OperationsPanel 与 QML 有重复历史路径；`MainWindow` 实际创建/连接关系才是可达证据。`OperationsPanel` 的请求补给/警告/标记/维修按钮只发 `(0..3,0)` 通用信号，不能解释成当前官方业务；`MainWindow::onGameStart()` 是空实现。

## 5. 已识别的未完成和风险

1. 旧 `protocol_manifest.json` 自报 `alignment_status=in-progress`，只列四节 verified。本次读到的对应实现可参考，但不是旧全量协议已合规的证据。
2. `MqttManager::connectToBrokerAsync` 后台 lambda 捕获裸 `this`/共享句柄，`disconnect` 可销毁句柄。旧线程文档明确仍有交错风险；RM27 必须从生命周期设计消除，不能仅复制“异步”字样。
3. 重新阅读 `NetworkManager.cpp:290-304` 后确认：第一段 `isUdpListening/listeningPort` 位于块注释中，只有第二段生效。撤回旧规划的“源码重复定义”风险；没有运行编译，既不声称构建失败，也不声称旧基线可构建。
4. 旧 `ExchangePanel::sendCommonCommandToServer` 发信号就返回 true；远程弹量 cmd_type=5 还会被 `ExchangeCommandPolicy` 的 1/2/6 白名单拒绝。成功弹窗不能证明服务端批准或到账；旧模拟器 CommonCommand 只处理 3/4，其他兑换同样缺闭环。旧复活有 no-op 后备、`robotIndex=0`，工程装配有本地阶段/成功推定，必须改为权威反馈。
5. 旧模块面板回退 mock；机器人位置 `(0,0)` 被战术模块用作无位置；`ThreatRanker` 取第一台己方作距离原点、`objectiveScore=0`；`ExecutionFusion` 为每个己方机器人取当前机器人自定义数据。`TacticalAnalyzer::updateLinkHealth` 把 MQTT 状态固定为 ok、延迟固定 0；相机处理延迟也为 0；`updatePredictions` 清空 predictedEvents，事件预测尚未接入。均不能视为已完整可靠实现。
6. 旧 `MqttLogger` 缓冲不硬限量；UDP 组帧长度不符仍输出，按收到字节数判断齐帧，未完整证明连续片序号、单帧/在途内存上限。RM27 需要明确边界和故障测试。
7. 配置存在不等于运行生效：窗口默认尺寸/fullscreen、video.default_path/fps、robots.key_bindings 等有兼容/元数据字段；未找到通用 UI 设置写回 JSON/QSettings 的完整流程，故不标记全部设置已持久化。
8. 公共仓库不附模型/部分音视频，ONNX、FFmpeg、Paho 可选编译。空能力、示例素材、开发钩子和真实比赛能力必须分别报告；旧平台/资源检查的规则不能覆盖 RM27 当前约束。

## 6. 与本项目现有开发方式的衔接

保留通俗路线中的六步沟通方式、一次只开发一个小任务、先数据/命令闭环再完善 UI、客户端/独立模拟器/模拟器网页同步更新。每次先读 `AGENTS.md`、通俗路线、问题记录，再对照实际代码；本次只规划，不修改任何功能实现。

P-001、P-002、P-003 只在各自适用范围引用本文件列出的旧实现，不推广成全量兼容许可。P-002 与 P-003 的第 1 步离线实施结论沿用现有真实记录，P-001 仍待对应任务开发；官方设备未验证状态始终保留。更详细当前完成状态见 [当前缺口分析](05_Current_Gap_Analysis.md)。

这次审计补出的重点是：模块状态须有明确任务；输入与视频独立健康；会话/身份/跨局清理；命令待确认/失败状态；字节通道与私有业务边界；分片上限及缓存；构建能力与发行依赖；mock/空实现不可计完成；音效/战术/AR 归为可选增强。技术备查已经提到其中一部分，最新计划应提高到可执行任务和验收条目，不能笼统声称它们以前全未考虑。

## 7. 两赛季正式通信文件与旧实现的实质差异

本节单独比较本地 2026 V2.0.0（20260626）和固定 2027 V1.0.0（20261029）第 2 章。页码为 PDF 阅读器页号，便于回原文；2026 仅用于历史比较，不能替换 2027 依据。**旧项目自称 2026，并不表示实际代码已符合 2026 V2.0.0。** 文档间变化与旧实现偏差必须分开登记。

| 消息/范围 | 2026 正式文件 | 2027 正式文件 | 对实现的实质影响 |
| --- | --- | --- | --- |
| 消息集合 | 2.2.1 至 2.2.36，PDF 49-75 | 2.2.1 至 2.2.32，PDF 51-75 | 移除 HeroDeployModeEventCommand、DeployModeStatusSync、AirSupportCommand、AirSupportStatusSync 四类；其余后半部分章节重排，不按旧节号定位消息 |
| CustomControl | 2.2.2，PDF 51：data 最多 30 字节 | 2.2.2，PDF 53：data 最多 60 字节 | 传输层长度检查与边界样本改为 60；不把旧私有 10 字节业务顺带纳入 |
| GameStatus | 2.2.3，PDF 51-53：end_reason 1..9，基地血量/前哨血量/曾被摧毁等胜负判据 | 2.2.3，PDF 53-55：end_reason 1..7，其中 2 控制度，3 总攻击伤害，4 总剩余血量，5 平局，6 异常终止，7 手动判定 | wire 字段相同但枚举意义变化；不能把 27 的 6 显示成旧“全队机器人总剩余血量” |
| GlobalUnitStatus | 2.2.4，PDF 53-54：14 字段；#3/#8 护盾值；#4/#5 己方前哨、#9/#10 对方前哨；血量十项 `[己1,2,3,4,7,敌1,2,3,4,7]` | 2.2.4，PDF 55-56：16 字段；#3/#8 基地阵地控制；#4/#5 固定 R 前哨、#9/#10 固定 B 前哨；血量八项 `[己1,3,4,7,敌1,3,4,7]`；#15/#16 累计控制度 | `base_shield` 名字仍保留但语义不是护盾；R/B 实体固定，己敌视角单独转换；新增控制度；base_status=0 从“无敌”改为“100%防御增益” |
| GlobalLogisticsStatus | 2.2.5，PDF 54-55：科技等级对应工程装配 | 2.2.5，PDF 56-57：科技等级对应重装已成功装配最高难度 | 四字段结构/类型相同，角色、收益及装配规则不能旧名替换后即视为完成 |
| GlobalSpecialMechanism | 2.2.6，PDF 55：1/2 为堡垒占领计时 | 2.2.6，PDF 57：1/2 为堡垒激活计时；新增 3/4 R/B 前哨阵地、5/6 R/B 基地阵地激活计时，时间正负表示己敌推进 | 不是无符号倒计时；成对数组、符号、实体和显示内容同步变更 |
| Event | 2.2.7，PDF 55-56：5/6 英雄狙击伤害，7 空中支援，8 反制；14 对方四级装配触发缓冲；15 工程装配结果 | 2.2.7，PDF 58-59：5/6 R/B 前哨阵地控制，7/8 R/B 基地阵地控制；14 重装战亡临时激活缓冲；15 重装装配结果；新增 16 安装模块化 42mm | 同编号复用成不同事件，不能保留旧 switch 的副作用/语音；装配步骤齐全不等于 Event 15 成功结果 |
| RobotStaticStatus/性能选择与同步 | 2.2.10，PDF 58-59：shooter/chassis 都有英雄专属 3/4；2.2.23/24，PDF 68-69 | 2.2.10，PDF 60-62：只列 1/2；2.2.23/24，PDF 70-71 | 静态 14 字段结构一致不代表枚举一致；P-003 类型数字编码单按用户约定。2027 总表性能同步用途写步兵/重装、详细 2.2.24 只写步兵，角色范围须保留问题记录，不能由旧 UI 推定 |
| RobotDynamicStatus | 2.2.11，PDF 59-60：#4 current_chassis_energy 当前底盘能量 | 2.2.11，PDF 62-63：#4 reserved 保留位 | 不把保留字段显示为能量或功率，不延续旧赋值行为 |
| RobotModuleStatus | 2.2.12，PDF 60-61：#11 laser_detection_module 为激光检测在线态；#4/#5 描述发射机构状态 | 2.2.12，PDF 63-64：#11 modular_42mm 为重装模块化42mm安装权限 0/1；#4/#5 描述测速模块 | 相同 wire 字段号 11 已换义，不能复用旧激光开关/0..2校验；测速在线和安装权限分别显示 |
| 地图两类消息 | 2.2.17/18，PDF 64-66：**已存在** MapClickInfo 下行和 MapClickCmd 上行 | 2.2.17/18，PDF 66-68：同样两类；接收者示例由英雄/工程改成重装/哨兵 | 拆分不是 27 新增。旧客户端/模拟器仍用 MapClickInfoNotify，是旧实现未收敛到其自称版本；必须改为当前正式名称。两版表格 #3/#6 与示例 mode/type 关系需单独核对，不用旧 schema 决定 |
| RadarInfoToClient | 2.2.19，PDF 66-67：说明十二槽，敌 `[1,2,3,4,6,7]` 后己同序；示例缺字段号/错误 repeated 类型 | 2.2.19，PDF 68-69：说明八槽，敌 `[1,3,4,7]` 后己同序；示例同样不可直接编译 | P-001 用户指定当前模拟器实码十二槽临时基准，不能写成官方27八槽与旧基准相同；`robot_info=1` repeated 子结构及 cm 转换只在该约定范围使用 |
| AssemblyCommand/TechCoreMotionStateSync | 2.2.21/22，PDF 67-68：工程装配；#8 只在四级装配有效 | 2.2.21/22，PDF 69-70：重装装配；#8 四级或战亡临时激活缓冲期有效 | 指令两字段结构保持，但需加入重装战亡缓冲闭环及结果事件；不能迁移旧“对方四级强制退出”业务含义 |
| 附录二身份 | PDF 80-81：1/101 英雄，2/102 工程 | PDF 80-81：1/101 重装，2/102 保留 | 当前机器人可选名单、名称、图标、能力、场景都要同步，不由 ID 推导旧角色动作 |

以下消息在本次第 2 章对照中未发现字段集合/编号/标量类型的实质变化：KeyboardMouseControl、RobotInjuryStat、RobotRespawnStatus、RobotPosition、Buff、PenaltyInfo、RobotPathPlanInfo、CustomByteBlock、CommonCommand、RuneActivateCommand、RuneStatusSync、SentryStatusSync、DartCommand、DartSelectTargetStatusSync、SentryCtrlCommand、SentryCtrlResult。它们仍受 **2027 规则、角色与接口限制** 约束；“字段相同”不是已完成或免审计。GameStatus、GlobalLogisticsStatus、GlobalSpecialMechanism、Event、RobotStaticStatus、AssemblyCommand、TechCoreMotionStateSync、RobotPerformanceSelectionCommand、RobotPerformanceSelectionSync 也有保持的字段结构，但上表已列出语义/适用变化，不能只做 descriptor 相等比较。

两版 CommonCommand #1 的普通 17mm 兑换都要求参数为 10 的倍数；旧 `ExchangeCommandPolicy::isValidRequest` 按 100 倍数限制，是旧实现偏差，不是 2027 新改规则。远程兑换 #5 与普通兑换 #1 是不同操作，不能因旧面板远程 100 发按钮而混为同一约束。

旧模拟器的对应迁移必须覆盖状态默认值、周期发布、命令处理、Web 输入和自动场景五处：例如 #11 激光态不能改个网页标签就当模块安装权限完成；GlobalUnitStatus 固定 R/B 前哨不能只修一端的红蓝显示；Event 5..8/14/16、结算原因、CustomControl 长度与旧名字订阅均要检查实际负载。P-001 十二槽、P-002 六弹量槽、P-003 类型约定是明确例外，不能把全部旧消息恢复为 26 语义。

## 8. 本轮重新审阅的调用路径与可达性证据

### 8.1 从启动到退出的实码链

以下行号来自本轮工作区的旧项目快照，用于定位而非未来不变的契约；修改旧项目后应按函数名重新定位。

| 用户过程/后台路径 | 已读源码与关键位置 | 本轮结论 |
| --- | --- | --- |
| 启动、资源、日志 | `src/main.cpp:159` 安装日志；`:245` 设置元数据；根 `CMakeLists.txt:453` 编译静态库、`:688` 注册 CTest | 应用和日志入口存在；本轮未启动旧客户端，不能把静态审阅写成运行通过 |
| 身份与连接 | `src/ui/MainWindow.cpp:1327` `startServices`、`:1471/1515` 连接回调、`:1603` 切身份、`:8073/8102` 登录/退出 | 本地登录状态、服务器连接、实际赛事身份是三个状态。退出函数清输入和本地登录标志，不等于完成官方身份释放流程 |
| MQTT 选择 | `MainWindow.cpp:1340-1380` 优先 Paho，Qt MQTT 仅在另一编译条件下使用；`MqttClient.cpp:36` 的 `start` | 本轮根 CMake 未找到 `RM_HAS_QT_MQTT` 定义/Qt6::Mqtt 配置。Qt MQTT 源码是条件后备，不能算当前构建的第二条可用链 |
| 异步与停止 | `src/network/MqttManager.cpp:114` 附近后台连接 lambda、`:131` `disconnect`、`:300` `messageArrivedCallback` | 回调转 Qt 队列有实现；后台裸 `this`/句柄跨停止与切换的竞态需重新设计，不能只因使用线程池就宣称生命周期安全 |
| 下行路由 | `NetworkManager.cpp:1096` `subscribeToTopics`、`:1134` `processMqttMessage`；`GameData.cpp:3700` 起 wrapper switch | GameStatus/全局/静态/动态/事件/模块/Buff/雷达/路径/装配/机关/飞镖/复活等有实分支；专用性能 Sync、哨兵状态/结果只有列表没有处理分支 |
| 数据精度和存在性 | `GameData.cpp:1979/2078/2622`，`NetworkManager.cpp:1163` 附近 countdown 转 uint16 | 大量 uint32/float 被转为 uint8/uint16，负剩余时间和小数热量无法完整保留；旧 proto3 缺省判断/非零才更新不能作为 RM27 optional 语义 |
| 模块和自检 | `GameData.cpp:4079` 模块 Map/列表、`DamagePanel.qml:45-60` mock 回退 | 单 armor 复制四块、WIFI 固定离线、激光字段未完整投影；面板存在不等于按字段正确实现模块自检 |
| 地图操作 | `MainWindow.cpp:4987/5086`，`NetworkManager.cpp:671`；`MiniMap.qml:280/299/713` | A/B/I 标记选择、坐标转换、点击、上行可追溯；没有正式 MapClickInfo 下行回显，旧模拟器只打印，不构成状态闭环 |
| 兑换 | `ExchangePanel.qml:141-170` → `MainWindow.cpp:8085` → `ExchangeCommandPolicy.cpp:9` → `NetworkManager::sendCommonCommand` | 远程弹量 cmd=5 被本地策略拒绝；本地面板总返回 true。普通兑换与远程兑换必须分别验收，不只点按钮看成功提示 |
| 复活 | `RobotRespawn.qml:88-100/147-165/348`，`MainWindow.cpp:5185` | 网络未绑定有 no-op 后备；C++ 快捷键使用 robotIndex=0；本地许可、读条和正式 param 不能用旧索引猜测 |
| 装配 | `ExchangePanelEngineer.qml:139/167/177/188`，`GameData.cpp:3668`，旧 `mqtt_publisher.py:237` | 客户端发送及同步投影存在；界面用步骤齐全推成功，模拟器接收后只打印。需要加入正式结果事件及拒绝/取消/超时，不能以旧工程界面为完成证明 |
| 哨兵 | `NetworkManager.cpp:1123/1125`；`GameData.cpp:3692`；旧 `mqtt_publisher.py:351` | 客户端仅订阅/空兼容入口，未找到专用发送函数。模拟器的效果函数与结果发布只能作迁移参考 |
| 输入与热键 | `MainWindow.cpp:5145-5574`，`InputHotkeyPolicy.cpp`，`PopupOverlayPolicy.cpp` | 16 位键位、鼠标三轴三键、弹窗阻断、中和帧存在；13ms 调度和立即 flush 仍须按 2027 限频测试；失焦/切身份/恢复不能重发旧按下状态 |
| 主视频 | `VideoReceiver.cpp:371/471/528`，`HevcDecoder.cpp:140`，`VideoBackgroundWidget.cpp:137/168/211` | 8字节大端头、按片排序、连续 HEVC、最新帧显示存在；包上限/总长/连续序号/内存上限不足，解码前置条件和关闭恢复需重做 |
| 私有第二路视频 | `NetworkManager.cpp:1512` 附近 CustomByteBlock 分支；`VideoReceiver::feedH264Frame`；`HeroVideoWidget` | 标准字节通道和 H264+尾包号私有格式是两件事。所有非空自定义块先送私有视频链再尝试状态解析，不应照搬为通用接收策略 |
| 设置 | `ConfigLoader.cpp:17`、`ConfigManager.cpp:40/75/261`；`SettingsPanel.qml:89/142` | JSON 读取校验/文件监视/环境覆盖与运行时开关存在；AR setter 只改内存发信号。未找到通用设置写回磁盘流程，重启保存不得算完成 |
| 日志与诊断 | `MqttLogger.cpp:159` 的 `appendLine`；`VideoDatagramLogger.cpp:73`；`ClientDevHooks.cpp:108/160` | MQTT 十六进制录包、UDP头日志、本地开发HTTP/截图/按键入口存在；缓冲未硬限量、UDP只记头、开发工具编译及运行双开关，不是完整回放 |
| 战术分析 | `TacticalAnalyzer.cpp:1130/1145/1216`、`ThreatRanker.cpp:22/81`、`ExecutionFusion.cpp:28` | MQTT健康固定ok、延迟0、预测事件清空；距离原点取第一台己方、每台取自身私有数据。评分和AR只能保留可选增强，不可变成权威赛事状态 |

### 8.2 页面、控件和弹窗是否真的加载

QRC 收录 60 个 QML；未收录的 3 个是 `ModuleStatusPanel.qml`、`Disconnected.qml`、`Punished.qml`。所有 63 个均已检查组件声明、数据属性/信号、函数或绑定索引；对于只含样式的控件，只作功能归类，不把每一处绘制坐标当作业务审计。

| 实际入口 | 组件/路径 | 可达性与边界 |
| --- | --- | --- |
| MainWindow 直接 `setSource` | TopInfoBar、CentralAimingHUD、EventMessagePanel、OfficialEventPopup、CustomUI/GunnerOverlay、Tactical/TacticalCommandPage、Tactical/TacticalEventPopup、MiniMap（大小两处）、LeftBottomPanel、MessageNotificationPanel、DeployModePanel、SiloControlPanel、SettingsPanel、TabStatsPanel；伤害面板按需加载 | `MainWindow.cpp:2183-3015/5870/7054` 明确创建；这些是活动 UI，仍按各自绑定判断是否真实数据 |
| 兑换/供弹按需载入 | ExchangePanel、ExchangePanelEngineer、ExchangePanelAerial、AmmoSupplyPanel | `MainWindow.cpp:571/4911/7586` 及 `m_exchangeQmlSource` 选型；旧英雄/工程/空中分支不自动适用 2027 |
| 弹窗统一入口 | PopupOverlay → PrepPhasePopup、Countdown、RobotRespawn、Out、BattlePausePopup | `PopupOverlay.qml:46-134` Loader 和 GameData/状态机 payload 可追溯；不包括未打包的 Disconnected/Punished |
| 活动组件的显示子件 | BaseHealthBar、OutpostStatusBadge、RobotStatusItem、RobotStatsTable/Row、FpsDisplay、AuxiliaryShootingPanel、ActionButton；CustomUI 四组件 | 由 QML 引用和上下文绑定实现显示；子件可复用概念，不能每个装饰组件另算一种业务功能 |
| 战术页实际引用子件 | TacticalRadarMap、TacticalLargeMapOverlay、TacticalMock、components 下 HudPanel、BaseHealthWing、RobotStatusRow、RobotListPanel、BattleEventPanel、BattleAnalysisPanel、CameraPreviewPanel、TopLogisticsStrip | `TacticalCommandPage.qml:14/36-90/282-349` 存在正式数据不足回退 mock；该风险须在新正式界面中消除 |
| QRC 收录但未从活动页面证实全部可达 | HeroVideo；TacticalHeader、ResourceSummaryBar、KeyEventChainPanel、TacticalVideoStage、MainDecisionConsole、TargetRankPanel、AllyCriticalStatusPanel、PredictionPanel、HologramLockOverlay、TargetInfoCard | 这些文件与属性已列入审计，但不能仅凭 QRC 收录认定各面板已在主页面显示；旧主画面的工业相机实际使用 `HeroVideoWidget` |
| 历史文件/空能力 | ModuleStatusPanel、Disconnected、Punished；Widgets 的 MiniMapWidget、HealthBarWidget、HeatRingWidget、CrosshairWidget、RobotStatusPanel 等 | 不以名称推断功能可达；当前主窗已使用相应 QML/新控件，保留旧源不表示第二份功能完整 |
| Widgets 的真实辅助入口 | GameResultWidget、BattleMessageWidget、HelpOverlayWidget、DebugLogWidget、InfoPanel、OperationsPanel、RobotStatusWidget | MainWindow 明确创建。`InfoPanel.cpp:18/315` 自带固定演示列表和本地倒计时；OperationsPanel 的 4 个按钮只发通用信号，未见主窗将其接成官方业务，不能算四种赛事交互已实现 |

### 8.3 旧源码审阅边界

| 源码范围 | 本轮阅读程度/输出用途 |
| --- | --- |
| `src/main.cpp`、根 CMake、`config.example.json`、QML QRC、proto/manifest | 展开入口、编译开关、配置结构、资源清单及正式/历史消息定义；不运行旧构建，不修改文件 |
| `src/network` 的 NetworkManager、MqttManager、MqttClient、VideoReceiver、HevcDecoder、H264Decoder/AnnexB/StreamRecoveryPolicy、MqttLogger、VideoDatagramLogger、Protocol、S1ProtocolManager、CRC 及配套头 | 阅读收发/路由、编译条件、参数集恢复、日志、接口声明与关键实现；CRC 作为旧串口/UDP路径识别，不把算法细节迁移成 MQTT 需求 |
| `src/core` 的 GameData、PopupStateMachine、MapCoordinateMapper、DataFreshnessGuard、TimedEventRules、TacticalAnalyzer、ExecutionFusion、ThreatRanker、YoloDetector、TargetTracker、LogFileNaming，相关数据/常量头 | 深读状态更新与命令相关段，查空分支/窄化/mock；推理数学、追踪矩阵和每个动画未逐行复核，故不宣称算法准确性或运行性能通过 |
| `src/ui` 的 MainWindow 和所有 Policy/布局头 | 阅读初始化/连接、面板加载、身份切换、热键/指针/复活/兑换/装配/地图/视频/音效等关键过程；纯样式与全部窗口平台兼容分支未逐行审阅 |
| `src/config`、`src/simulator`、`src/devhooks` | 展开读取/监视/覆盖、内置造包/空timer、开发HTTP入口/快照/截图的关键实现，区分可选编译和默认关闭 |
| `src/widgets` 全部组件及 `src/qml` 全部63组件 | 按定义/调用/引用清点；展开业务、数据、输入、消息、视频、结果相关实现；纯绘制、样式、资源二进制不逐行审阅 |
| `sim/server` 的 main、mqtt_publisher、state_manager、match_simulation_engine、udp_sender/receiver、video_streamer、industrial_camera_streamer、hevc_annexb、protocol/crc、static app/index/map_geometry、config | 阅读独立启动、事件和命令分支、发布路径、默认角色/状态、演示时间线、图传分片与网页输入的功能相关实现；不启动旧服务，不逐个模拟全部比赛规则 |
| `tests`、`sim/tests`、`tools/release`、`scripts`、维护文档 | 清点测试注册、入口和检查目标，读与本审计结论相关的策略测试/发布说明；没有逐行阅读所有测试分支、YOLO训练脚本/数据集和所有维护历史，不将其列为已验证证据 |

因此本轮完成的是**业务能力与迁移边界审计**，不声称逐行安全审计、完整算法证明、旧客户端运行验收或官方硬件合规验收。上述明确未逐行阅读的范围，不会把缺源码证据的功能补成“已完成”。

## 9. 52 项历史功能到统一需求的完整映射

每条 REF 均有下列处置和需求落点。舍弃项的 ID 表示“身份/合规/接口边界有需求负责记录这一决定”，不表示必须恢复那项历史业务。可选增强不作为核心比赛交付的前置条件。

| 历史项 | 统一需求 ID | 最终处置/验收关注 |
| --- | --- | --- |
| REF-01 | REQ-001、REQ-057、REQ-060 | 继承启动/屏幕适配目标 |
| REF-02 | REQ-009、REQ-010、REQ-012、REQ-013 | 修改MQTT连接、订阅就绪和重连 |
| REF-03 | REQ-008、REQ-013、REQ-058 | 修改身份列表、切会话和真实状态 |
| REF-04 | REQ-006、REQ-007、REQ-011 | 修改全消息路由及字段校验 |
| REF-05 | REQ-011、REQ-073 | 以当前MQTT接口替代旧wrapper/UDP数据线路 |
| REF-06 | REQ-009、REQ-073 | 舍弃S1私有登录为正式依赖，记录边界 |
| REF-07 | REQ-015、REQ-016、REQ-059 | 修改权威阶段、结果和跨局清理 |
| REF-08 | REQ-017、REQ-045 | 修改八槽血量、控制度、固定R/B前哨 |
| REF-09 | REQ-017 | 限P-002沿用六弹量槽，保留有符号值 |
| REF-10 | REQ-018、REQ-030、REQ-033、REQ-034 | 修改经济和兑换，不继承旧费用常量 |
| REF-11 | REQ-024、REQ-048、REQ-051 | 修改机制、机关和飞镖信息 |
| REF-12 | REQ-008、REQ-019 | 按P-003修改角色解释，未知仍未知 |
| REF-13 | REQ-020 | 修改动态字段、原类型与保留位 |
| REF-14 | REQ-021、REQ-080 | 修改模块/自检，不复制装甲或填WIFI状态 |
| REF-15 | REQ-022 | 修改伤害各原始分类及汇总 |
| REF-16 | REQ-040、REQ-044、REQ-045 | 修改位置/视角；P-001限雷达临时约定 |
| REF-17 | REQ-041、REQ-045 | 修改路径与坐标，不按大小猜单位 |
| REF-18 | REQ-042、REQ-043、REQ-035 | 修改标记收发和等待反馈 |
| REF-19 | REQ-025、REQ-059 | 修改事件编号、参数、去重和提示 |
| REF-20 | REQ-026、REQ-014 | 修改Buff权威时间和过期状态 |
| REF-21 | REQ-027、REQ-028、REQ-059 | 修改判罚/遮挡/异常层，未决通知语义保留 |
| REF-22 | REQ-029、REQ-049、REQ-035 | 修改性能上行并补专用同步接收 |
| REF-23 | REQ-030、REQ-033、REQ-034、REQ-035 | 修改普通/远程兑换，覆盖cmd5断点 |
| REF-24 | REQ-023、REQ-031、REQ-032、REQ-037 | 修改复活参数、许可、反馈和防连发 |
| REF-25 | REQ-046、REQ-047、REQ-025、REQ-035 | 改为重装业务，补结果/取消/失败闭环 |
| REF-26 | REQ-008、REQ-073 | 舍弃旧英雄部署消息和专属UI |
| REF-27 | REQ-008、REQ-073 | 舍弃已移除空中支援消息；当前功能另按27资料 |
| REF-28 | REQ-048、REQ-035 | 修改机关启动/同步，不继承私有结果扩展 |
| REF-29 | REQ-051、REQ-035 | 修改飞镖目标/闸门/发射及权威反馈 |
| REF-30 | REQ-049、REQ-050、REQ-035 | 修改目标并补缺失客户端收发/UI |
| REF-31 | REQ-036、REQ-067 | 修改键鼠节奏、数据范围与统计 |
| REF-32 | REQ-037、REQ-060 | 继承失焦清键、输入仲裁目标 |
| REF-33 | REQ-052、REQ-053、REQ-065 | 修改UDP包/组帧和边界处理 |
| REF-34 | REQ-054、REQ-056 | 继承解码思路，按当前依赖重做恢复 |
| REF-35 | REQ-055、REQ-056、REQ-067 | 继承最新帧、无视频和阶段诊断目标 |
| REF-36 | REQ-039、REQ-073 | 私有H264格式待确认，不纳入默认业务 |
| REF-37 | REQ-039、REQ-073 | 私有机器人状态待确认，仅保留标准通道 |
| REF-38 | REQ-038、REQ-073 | 舍弃私有自动前哨转发，字节通道仍实现 |
| REF-39 | REQ-015、REQ-037、REQ-059 | 继承弹窗仲裁目标，修改27触发条件 |
| REF-40 | REQ-057、REQ-060、REQ-074 | 继承帮助/控件/焦点体验目标 |
| REF-41 | REQ-079、REQ-059 | 音效归可选，必要状态保留可见提示 |
| REF-42 | REQ-016、REQ-057、REQ-079 | 必须真实结果；动画/音效为可选 |
| REF-43 | REQ-002、REQ-058 | 继承配置校验，补应用/重连及持久化边界 |
| REF-44 | REQ-004、REQ-068、REQ-066 | 修改录包/日志上限及磁盘失败 |
| REF-45 | REQ-067、REQ-068 | 继承分阶段观测，头日志不冒充可回放 |
| REF-46 | REQ-040、REQ-043、REQ-057、REQ-077 | 基础地图必需；战术分析页可选 |
| REF-47 | REQ-014、REQ-077 | 数据新鲜度必需；经验评分/预测可选 |
| REF-48 | REQ-078、REQ-073 | 可选AI/AR，模型/算力/接口另行确认 |
| REF-49 | REQ-063、REQ-064、REQ-067 | 继承可测试与可观测目标，工具形式自选 |
| REF-50 | REQ-061、REQ-062 | 独立模拟器替代旧内置业务，演示数据明确标注 |
| REF-51 | REQ-001、REQ-005、REQ-063、REQ-069 | 修改Windows依赖/生成/资源和发行检查 |
| REF-52 | REQ-069、REQ-070、REQ-073、REQ-076 | Windows脚本替代旧Linux现场依赖；录屏等仍可选 |

本表覆盖 REF-01 至 REF-52 共 52 项，未映射历史项为 0。统一任务与验收分别由 [任务表](07_Task_Backlog.md) 和 [验收清单](08_Test_and_Acceptance.md) 承接；本文件不把 52 个历史分组直接当成需求数量。

## 10. 独立审查补充的旧行为处置

| 审查项 | 旧项目实码证据 | 迁移决定 |
| --- | --- | --- |
| COV-01，REF-49/50 | `MainWindow.cpp:6780,6953–6985` 普通主窗 Ctrl+Shift+T/D 调用 `GameData` 的正常状态更新路径（`GameData.cpp:2580`）。与 `RM26_ENABLE_DEVTOOLS` 管理的 HTTP 钩子是不同路径 | 舍弃普通主窗调试注入。正式入口不从热键合成比赛时间、阶段或命中，内置预览仍以独立来源演示。T-015/057/060/063/073 和同号 AT 验证状态、事件及发送均不受注入影响。 |
| COV-08，REF-31/40/43 | `SettingsPanel.qml:615–637` 滑块，经 `MainWindow.cpp:6356,5433–5459` 影响位移增益（0.1…3 倍）并在特定状态调用 `QCursor::setPos` | 灵敏度校准待定，属于交互选项。T-036/037/060 保留协议与焦点基本行为。若后续选做校准，再验收舍入、溢出、保存、编辑/失焦/切图和指针影响。 |

详细路径及审查范围见 [10 独立审查](10_Coverage_Review.md)。
