# 模拟器与 Qt 客户端手动联测

以下命令在 **RM27_Client 仓库根目录**的 PowerShell 中执行。使用本机模拟器、红方 3 号和已构建的 Release 客户端。若尚未构建，先运行 `.\scripts\build.ps1 -Configuration Release`。

## 打开模拟器和客户端

1. 在第一个 PowerShell 中运行 `.\simulator\scripts\check.ps1 -Runtime`。若 `MQTT handshake` 与 `Simulator HTTP health` 都显示 `passed`，直接打开[模拟器网页](http://127.0.0.1:8000)。从服务关闭状态启动时，先打开 Docker Desktop，再运行以下命令，等到出现 `Simulator ready` 和 `MQTT ready`。

   ```powershell
   .\simulator\scripts\start.ps1 -CurrentRobotId 3
   ```

2. 在第二个 PowerShell 中打开步兵只读客户端，保持窗口开启。

   ```powershell
   .\scripts\run.ps1 -Configuration Release -SkipBuild -ConfigFile configs/infantry.example.json
   ```

3. 网页顶栏的 **OPERATOR** 选 **红3 步兵**，客户端“工作台”应显示“五类订阅就绪”。进入“运行信息”确认“图传 UDP 收包”已绑定 `127.0.0.1:3334`。若绑定失败，检查是否已有另一个客户端占用该端口。

## 手动观察结果

| 测什么 | 操作 | 应看到什么 |
| --- | --- | --- |
| 网页数值是否到达客户端 | 在网页“2027 当前机器人基础状态”的 `RobotDynamicStatus` 卡把“当前血量”改为 321，点“发送动态状态”。也可以再改为 322 重测。 | 客户端“工作台 → 当前机器人血量”跟随变化。若仍显示横杠，重新核对网页顶栏红 3 与“五类订阅就绪”。 |
| 录屏是否通过 UDP 到达并组成完整帧 | 打开客户端“运行信息”。在网页“图传控制 → 选择视频”选 `demo-1080p60-hevc.mp4`，点“切换”，核对“当前视频”后点“开始推流”。观察几秒再点“停止推流”。 | 发送时，客户端“有效包”和“本机模拟组帧 · 完整帧”持续增加，“最近完整帧”出现帧号、长度及来源。停发后计数稳定，再次推流会继续增加。当前 Qt 工作台显示到组帧诊断，实时画面留待后续实现。 |
| 离线解码能否读到末帧 | 在第一个 PowerShell 中对本机准备好的 `.hevc` 文件运行下方两条解码命令。可以让客户端保持打开。 | 第一条逐帧列出 3 个 1920×1080 结果及像素摘要，末行 `stopped`；整段录屏末行 `completed`，`frames` 为 3762。这是 62.7 秒离线录屏的确定帧数。 |
| 同一文件在损坏后能否恢复 | 按[离线恢复手测](../../libs/video/README.md#手动核对同一文件损坏后恢复)生成并打开两段相连的短片。 | 工具报告前段的解码错误，第二段从关键帧起连续 12 帧与原始像素一致。回归会打印实际恢复序号。 |
| 后台解码交付的帧能否保留 | 运行 [后台像素帧手测](../../libs/video/README.md#手动核对后台交付的像素帧)。同一个工具先在第 3 帧停止，再打开另一尺寸的单帧文件。 | 第二段从序号 1 开始，结束后还能读出第一段的 1920×1080 首帧，像素摘要与原值相同。这一步可在工作台保持打开时单独运行。 |

```powershell
$clip = 'simulator/resources/videos/demo-1080p60.hevc'
.\scripts\run.ps1 -Configuration Release -SkipBuild -HevcFile $clip -StopAfter 3
.\scripts\run.ps1 -Configuration Release -SkipBuild -HevcFile $clip | Select-Object -Last 1
```

录屏放在本机 `simulator/resources/videos/`。其他机器可用自己的本地视频测试推流，用 [HEVC 解码回归](../../tests/check_hevc_decode.py) 生成已知像素短片。

## 结束测试

网页点“停止推流”，关闭自己打开的 Qt 窗口。若模拟器由你在本轮启动，再运行 `.\simulator\scripts\stop.ps1`。复用原来已在运行的服务时可以让它继续运行。

## 完整启动参数和排查

- [Windows 启动方式与全部参数](../../docs/planning/12_Build_and_Run.md#6-模拟器-windows-启动方式与全部参数)
- [检查、停止和日志](../../docs/planning/12_Build_and_Run.md#8-模拟器检查停止和运行日志)
