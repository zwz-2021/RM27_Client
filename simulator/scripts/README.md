# 模拟器与 Qt 客户端手动联测

以下命令在 **RM27_Client 仓库根目录**的 PowerShell 中执行。客户端使用步兵模拟配置和红方 3 号。先运行 `.\scripts\build.ps1 -Configuration Debug` 构建本次手测的版本。客户端和模拟器都使用 PATH 中的 FFmpeg。

## 打开模拟器和客户端

1. 在第一个 PowerShell 中运行 `.\simulator\scripts\check.ps1 -Runtime`。若 `MQTT handshake` 与 `Simulator HTTP health` 都显示 `passed`，直接打开[模拟器网页](http://127.0.0.1:8000)。从服务关闭状态启动时，先打开 Docker Desktop，再运行以下命令，等到出现 `Simulator ready` 和 `MQTT ready`。

   ```powershell
   .\simulator\scripts\start.ps1 -CurrentRobotId 3
   ```

2. 若旧客户端仍打开，在旧窗口的“工作台”点“停止”，释放本机 UDP/3334 后可以保留旧窗口。另开一个 PowerShell 运行本次构建的客户端，保持新窗口开启。

   ```powershell
   .\scripts\run.ps1 -Configuration Debug -SkipBuild -ConfigFile configs/infantry.example.json
   ```

3. 网页顶栏的 **OPERATOR** 选 **红3 步兵**，客户端“工作台”应显示“五类订阅就绪”。进入“运行信息”确认“图传 UDP 收包”已绑定 `127.0.0.1:3334`。若绑定失败，检查是否已有另一个客户端占用该端口。

## 手动观察结果

| 测什么 | 操作 | 应看到什么 |
| --- | --- | --- |
| 网页数值是否到达客户端 | 在网页“2027 当前机器人基础状态”的 `RobotDynamicStatus` 卡把“当前血量”改为 321，点“发送动态状态”。也可以再改为 322 重测。 | 客户端“工作台 → 当前机器人血量”跟随变化。若仍显示横杠，重新核对网页顶栏红 3 与“五类订阅就绪”。 |
| 本机录屏是否解出像素 | 打开客户端“运行信息”。在网页“图传控制 → 选择视频”选 `demo-1080p60-hevc.mp4`，点“切换”，核对“当前视频”后点“开始推流”。观察几秒，再点“停止推流”。本次只使用网页这一个发送入口。 | 有效包和完整压缩帧开始增加。“本机模拟解码”的已解码帧数随之增长，尺寸显示 1920×1080。停止推流后稍候，尾部帧排出，计数稳定。工作台画面安排在 T-055。 |
| 停止并重开是否清除旧视频 | 保持网页已停止推流，在客户端“工作台”点“停止”，再点“启动数据源”，回到“运行信息”。等几秒，确认计数后再从网页开始推流。 | 没有新输入时解码计数保持 0，旧尺寸清空。重新推流后，新的计数从零增长，并再次显示录屏尺寸。 |
| 离线解码能否读到末帧 | 在第一个 PowerShell 中对本机准备好的 `.hevc` 文件运行下方两条解码命令。可以让客户端保持打开。 | 第一条逐帧列出 3 个 1920×1080 结果及像素摘要，末行 `stopped`；整段录屏末行 `completed`，`frames` 为 3762。这是 62.7 秒离线录屏的确定帧数。 |
| 同一文件在损坏后能否恢复 | 按[离线恢复手测](../../libs/video/README.md#手动核对同一文件损坏后恢复)生成并打开两段相连的短片。 | 工具报告前段的解码错误，第二段从关键帧起连续 12 帧与原始像素一致。回归会打印实际恢复序号。 |
| 后台解码交付的帧能否保留 | 运行 [后台像素帧手测](../../libs/video/README.md#手动核对后台交付的像素帧)。同一个工具先在第 3 帧停止，再打开另一尺寸的单帧文件。 | 第二段从序号 1 开始，结束后还能读出第一段的 1920×1080 首帧，像素摘要与原值相同。这一步可在工作台保持打开时单独运行。 |

```powershell
$clip = 'simulator/resources/videos/demo-1080p60.hevc'
.\scripts\run.ps1 -Configuration Debug -SkipBuild -HevcFile $clip -StopAfter 3
.\scripts\run.ps1 -Configuration Debug -SkipBuild -HevcFile $clip | Select-Object -Last 1
```

录屏放在本机 `simulator/resources/videos/`。其他机器可用自己的本地视频测试推流，用 [HEVC 解码回归](../../tests/check_hevc_decode.py) 生成已知像素短片。

要重复核对本机链路的像素与先后顺序，运行下面的检查。它用两个内容不同的合成短片、临时端口及独立 Qt 窗口，结束时打印证据目录。窗口手测可以单独进行。

```powershell
.\simulator\.venv\Scripts\python.exe tests/check_simulated_video_decode.py --configuration Debug
```

## 结束测试

网页点“停止推流”，关闭自己打开的 Qt 窗口。若模拟器由你在本轮启动，再运行 `.\simulator\scripts\stop.ps1`。复用原来已在运行的服务时可以让它继续运行。

## 完整启动参数和排查

- [Windows 启动方式与全部参数](../../docs/planning/12_Build_and_Run.md#6-模拟器-windows-启动方式与全部参数)
- [检查、停止和日志](../../docs/planning/12_Build_and_Run.md#8-模拟器检查停止和运行日志)
