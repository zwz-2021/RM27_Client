# 模拟器与 Qt 客户端手动联测

以下命令在 **RM27_Client 仓库根目录**的 PowerShell 中执行。客户端使用步兵模拟配置和红方 3 号。先运行 `.\scripts\build.ps1 -Configuration Debug` 构建本次手测的版本。Qt 6.8 或以上的套件需含 Qt Multimedia。客户端和模拟器都使用 PATH 中的 FFmpeg。首次使用模拟器时，运行 `.\simulator\scripts\start.ps1 -Install` 准备 Python 环境。

准备两段画面容易区分的本地视频，放入 `simulator/resources/videos/`。本机已有 `testdemo.mp4`（动态图案）和 `demo-1080p60-hevc.mp4`（录屏）时可直接使用。新机器可用下面两条命令分别生成 640×360 的动态图案与 1920×1080 的静态彩条，只生成缺少的文件。

```powershell
.\simulator\.venv\Scripts\python.exe -m simulator.tools.create_test_video
ffmpeg -n -f lavfi -i smptebars=size=1920x1080:rate=60 -t 2 -c:v libx264 -pix_fmt yuv420p simulator/resources/videos/bars-1080p60.mp4
```

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
| 工作台能否显示录屏 | 先在工作台观察等待画面的提示。在网页“图传控制 → 选择视频”选 `testdemo.mp4`，点“切换”，核对“当前视频”后点“开始推流”。只用网页这一个发送入口。调节客户端窗口大小，切到“运行信息”再返回工作台。 | 工作台出现动态图案并保持原比例。“运行信息”的已解码帧数增长，动态图案对应尺寸为 640×360。返回工作台可以继续看到新画面。 |
| 停流和重新推流 | 网页点“停止推流”，客户端保持开启。等几秒，确认过期提示后，改选另一段录屏或 `bars-1080p60.mp4`，点“切换”，再点“开始推流”。 | 停流后保留末帧并标明画面已过期。重新推流后显示第二段录屏或彩条，过期提示消失。用上述 1080p 文件时，“运行信息”显示 1920×1080。 |
| 停止并重开会话 | 网页先停流。在客户端“工作台”点“停止”，观察画面后再点“启动数据源”。保持几秒，最后让网页重新推流。 | 停止会话时画面清空。重开后工作台等待首帧，“运行信息”解码计数为 0、旧尺寸清空。新的输入到达后画面恢复。 |
| 离线解码能否读到末帧 | 在第一个 PowerShell 中对本机准备好的 `.hevc` 文件运行下方两条解码命令。可以让客户端保持打开。 | 第一条逐帧列出 3 个 1920×1080 结果及像素摘要，末行 `stopped`；整段录屏末行 `completed`，`frames` 为 3762。这是 62.7 秒离线录屏的确定帧数。 |
| 同一文件在损坏后能否恢复 | 按[离线恢复手测](../../libs/video/README.md#手动核对同一文件损坏后恢复)生成并打开两段相连的短片。 | 工具报告前段的解码错误，第二段从关键帧起连续 12 帧与原始像素一致。回归会打印实际恢复序号。 |
| 后台解码交付的帧能否保留 | 运行 [后台像素帧手测](../../libs/video/README.md#手动核对后台交付的像素帧)。同一个工具先在第 3 帧停止，再打开另一尺寸的单帧文件。 | 第二段从序号 1 开始，结束后还能读出第一段的 1920×1080 首帧，像素摘要与原值相同。这一步可在工作台保持打开时单独运行。 |

```powershell
$clip = 'simulator/resources/videos/demo-1080p60.hevc'
.\scripts\run.ps1 -Configuration Debug -SkipBuild -HevcFile $clip -StopAfter 3
.\scripts\run.ps1 -Configuration Debug -SkipBuild -HevcFile $clip | Select-Object -Last 1
```

录屏放在本机 `simulator/resources/videos/`。其他机器可用自己的本地视频测试推流，用 [HEVC 解码回归](../../tests/check_hevc_decode.py) 生成已知像素短片。

要自动复现，在可交互的 Windows 桌面运行下面的检查。第一条对比解码像素与先后顺序，第二条从正常启动的 Qt 工作台截取实际像素，核对两种画面、过期、恢复和清空。检查使用临时端口和独立窗口，窗口手测可以单独进行。

```powershell
.\simulator\.venv\Scripts\python.exe tests/check_simulated_video_decode.py --configuration Debug
.\simulator\.venv\Scripts\python.exe tests/check_simulated_video_display.py --configuration Debug
```

### 手测最近有效 UDP 包距今多久

1. 按上方“打开模拟器和客户端”进入红 3 步兵模拟会话。让网页先停止推流，在客户端“工作台”点“停止”再点“启动数据源”。打开“运行信息”，确认 UDP 已绑定。应看到“最近 1 秒有效 UDP 收包：0 包/秒”，下方显示等待本会话首个有效包。
2. 网页“图传控制”选 `testdemo.mp4`，点“切换”后点“开始推流”。有效包总数应增加，每秒收包数应大于 0，距最近有效包的时间应接近 0 秒。每个通过包头和长度校验的分片算一个包，一帧画面可包含多个分片。
3. 网页点“停止推流”，保持客户端运行。最后一包离开一秒窗口后，下一次界面刷新应显示 0 包/秒。有效包总数应停住，距今秒数继续增加。在网页红 3 的 `RobotDynamicStatus` 卡把当前血量改成一个新值（如 322），点“发送动态状态”。回到同一客户端的“工作台”，应看到新血量和已过期的画面。
4. 网页再次开始推流，每秒收包数应重新大于 0。网页停流后在客户端停止数据源，“运行信息”的速率应显示横杠。再启动数据源，首包到达前应显示 0 包/秒。结束时关闭自己打开的客户端，自己启动的模拟器可用 `.\simulator\scripts\stop.ps1` 关闭。

### 按已知包数验证收包速率

在本机可交互的 Windows 桌面打开 PowerShell，在仓库根目录运行下面的检查。它在独立端口启动 Qt 窗口，向它送入 4 个有效分片和 2 个短包。窗口应显示 4 包/秒、丢弃 2 包，静默后显示 0 包/秒，再收到一个有效包时显示 1 包/秒。报告和诊断页截图保存在命令末尾列出的日志目录。

```powershell
.\simulator\.venv\Scripts\python.exe tests/check_udp_receive.py --configuration Debug
```

### 手测本机录屏丢一片并恢复

1. 按[打开模拟器和客户端](#打开模拟器和客户端)启动两者，选择红 3。网页点“停止推流”，保持模拟器和 MQTT 运行。要从零计数，可在客户端“工作台”点“停止”，再点“启动数据源”。确认“五类订阅就绪”，且“运行信息”显示 UDP 已绑定 `127.0.0.1:3334`，再回到工作台。
2. 在仓库根目录另开 PowerShell，运行下方命令。工具会生成测试片并发送五秒红色画面，然后故意漏发下一帧的一个分片，暂停在回车提示。保持该终端开着。

   ```powershell
   .\simulator\.venv\Scripts\python.exe -m simulator.tools.video_loss_demo
   ```

3. 红色画面先显示“正在播放”，停发约一秒后应保留红色并标明“画面已过期”。打开“运行信息”，从零开始的会话应显示完整帧 300、丢帧 1（超时 1）、在途 0 帧、缓存 0 字节。尾帧排空后应显示已解码 300 帧、排队 0 帧。等待期间在网页“当前血量”填 321 并点“发送动态状态”，回到工作台确认血量更新，画面仍为过期的红色。
4. 保持客户端会话开启，在发送工具的 PowerShell 窗口按回车。工作台应出现五秒蓝色画面并恢复“正在播放”。发送结束后蓝色末帧也会过期。此时完整帧和已解码帧均应到 600，超时仍为 1，在途、缓存和解码排队均回到 0。测试工具会自行退出，最后按下方结束步骤关闭自己启动的服务。

同一回环丢片场景的自动检查会自行打开测试窗口、分配临时端口并截图。首次运行自动检查时，用 `.\simulator\.venv\Scripts\python.exe -m pip install -e "./simulator[test]"` 安装测试依赖。

```powershell
.\simulator\.venv\Scripts\python.exe tests/check_simulated_video_loss.py --configuration Debug
```

### 手测缺少解码起点时的画面

1. 按[打开模拟器和客户端](#打开模拟器和客户端)启动红 3 步兵会话。网页点“停止推流”，保留 MQTT。在工作台点“停止”再点“启动数据源”，等到“五类订阅就绪”，确认运行信息中 UDP 已绑定 `127.0.0.1:3334`。测试工具会生成红、蓝短片。
2. 另开 PowerShell，从仓库根目录运行以下命令。看到五秒红片后，工具会故意漏掉一片并暂停。等红色末帧标为“画面已过期”。在网页修改当前血量并点“发送动态状态”，工作台应收到新值。

   ```powershell
   .\simulator\.venv\Scripts\python.exe -m simulator.tools.video_loss_demo --wait-for-keyframe
   ```

3. 在发送工具里按第一次回车。它会用约五秒发送 295 个缺少解码起点的普通蓝帧，再次暂停。工作台仍应显示过期的红色和等待可解码画面的提示。打开“运行信息”，此时可以区分收到的完整帧和真正解出了画面的帧。暂停后等待尾部排空，可以看到本段的解码错误。
4. 回到工作台，在发送工具里按第二次回车。同一窗口应出现蓝色并显示“正在播放”。五秒后发送结束，末帧自然过期。核对下表后点“停止”，画面应清空。关停服务见[结束测试](#结束测试)。

| 观察时机（从零计数，等每段排空） | 完整帧 | 已解码帧 | 工作台 |
| --- | ---: | ---: | --- |
| 第一次回车前 | 300 | 300 | 红色末帧过期 |
| 普通帧发完、第二次回车前 | 595 | 300 | 红色仍过期 |
| 完整蓝片发完 | 895 | 600 | 蓝色末帧过期 |

三次暂停或结束后，超时应累计 1 次，在途分片和解码排队均应归零。上节的 Qt 自动检查也会验证普通帧直接接上完整蓝片时的恢复。

### 手测本机录屏连续多帧缺片

1. 按[打开模拟器和客户端](#打开模拟器和客户端)启动红 3 步兵模拟会话。网页点“停止推流”，保持 MQTT 运行。在客户端点“停止”，再点“启动数据源”，令计数从零开始。等“五类订阅就绪”，确认 UDP 已绑定 `127.0.0.1:3334`。
2. 在仓库根目录另开 PowerShell，运行下方命令。工作台会先显示五秒红片（300 帧）。将网页和工作台并排，便于在接下来约八秒的缺片期间看到变化。

   ```powershell
   .\simulator\.venv\Scripts\python.exe -m simulator.tools.video_loss_demo --consecutive-loss
   ```

3. 工具提示“开始发送 16 组缺片样本”时，在网页将红 3 的“当前血量”改为一个新值，点“发送动态状态”。工作台应更新血量，红色末帧在约一秒后标为“画面已过期”。可以截一张同时包含新血量和过期红帧的图。若错过这八秒，可在回车提示处补查静默期间的血量更新，或从第 1 步重跑观察缺片发送期间的更新。
4. 每组 12 帧各漏一个分片，组间停 0.5 秒。本机组帧上限为 8 个在途帧，预计每组 4 帧超出预算，其余 8 帧超时。看到回车提示后，在“运行信息”核对下表第一行。页面显示采样瞬间的在途帧数，切页时可能已经归零。
5. 回到工作台，在发送工具中按一次回车。同一窗口应恢复“正在播放”，显示五秒蓝片（300 帧）。可在播放期间再截一张，结束后等尾帧排空再核对第二行。最后在客户端点“停止”检查画面清空，按[结束测试](#结束测试)关闭自己启动的服务。

| 从零开始的会话，排空后预期 | 完整帧 / 已解码帧 | 组帧丢帧（超时 / 超出预算） | 在途帧 / 缓存字节 / 解码排队 | 工作台 |
| --- | ---: | ---: | ---: | --- |
| 16 组缺片发完，按回车前 | 300 / 300 | 192（128 / 64） | 0 / 0 / 0 | 红色末帧过期，保留更新后的血量 |
| 蓝片发完 | 600 / 600 | 192（128 / 64） | 0 / 0 / 0 | 保留蓝色末帧，静默后标记过期 |

自动复测可运行 `.\simulator\.venv\Scripts\python.exe tests/check_simulated_video_loss.py --configuration Debug --consecutive-loss`。终端会打印本次证据目录，内含缓存峰值、窗口状态、过期红帧和恢复蓝帧截图。若只想核对发出的包，运行 `.\simulator\.venv\Scripts\python.exe -m simulator.tools.check_video_datagrams --loss-series-report logs/loss-series-manifest.json` 可保存独立抓取的逐帧清单。

### 手测本机录屏首帧分片倒序

1. 按[打开模拟器和客户端](#打开模拟器和客户端)启动红 3 步兵模拟会话。网页点“停止推流”，保留 MQTT。客户端工作台点“停止”再点“启动数据源”，让计数从零开始。等到“五类订阅就绪”，在“运行信息”确认 UDP 已绑定 `127.0.0.1:3334`，回到工作台。
2. 另开 PowerShell，在仓库根目录运行以下命令。工具会自行生成测试片，先发五秒红片，随后停发并等你按回车。

   ```powershell
   .\simulator\.venv\Scripts\python.exe -m simulator.tools.video_loss_demo --reverse-first-frame
   ```

3. 确认红色末帧标为“画面已过期”。在“运行信息”查看完整帧和已解码帧，等尾帧排空后应各为 300，最近完整帧号为 299，组帧丢帧为 0。此时可在网页修改红 3 血量并点“发送动态状态”，工作台仍应收到新值。
4. 回到工作台，在发送工具中按一次回车。工具会将蓝片首帧（帧号 300）的全部分片倒序发出，其余 299 帧按正常顺序发送。同一窗口应显示蓝色和“正在播放”。五秒蓝片结束后等末帧过期，在“运行信息”核对最近完整帧号 599、完整帧与已解码帧各 600、丢帧 0，在途、缓存和解码排队均为 0。
5. 在客户端点“停止”，应清空画面。按[结束测试](#结束测试)关停本轮启动的资源。独立抓包和自动窗口复测可分别用下方命令执行，均使用临时端口。

```powershell
.\simulator\.venv\Scripts\python.exe -m simulator.tools.check_video_datagrams --reverse-first-report logs/video-reverse-first-wire/manifest.json
.\simulator\.venv\Scripts\python.exe tests/check_simulated_video_loss.py --configuration Debug --reverse-first-frame
```

### 复测 1080p60 录屏的超时与卡顿

如果模拟器后端在更新代码前已启动，先在网页停止推流，运行 `.\simulator\scripts\stop.ps1`，再按上方步骤启动模拟器和新版步兵客户端。客户端进入“五类订阅就绪”后，在网页选 `demo-1080p60-hevc.mp4`、点“切换”，再开始推流。

让 62.7 秒的录屏循环播放至少 65 秒，观察画面进入第二圈时是否连贯。在“运行信息”确认系统 UDP 接收缓冲的实际字节数，本机目标为 2,097,152。新会话中组帧超时应保持 0。网页停止推流后等尾帧排空，完整帧数和解码帧数应一致，解码栏应无缺参考帧错误。工作台应保留最后画面并标明过期。

下面的自动检查使用临时端口和独立窗口，统计发送端和 Qt 显示控件两处超过 100 毫秒的间隔，并核对大帧收包。录屏放在本机 `simulator/resources/videos/`；其他机器可以用 `--recording` 指定含大帧的 1080p60 MP4。

```powershell
.\simulator\.venv\Scripts\python.exe tests/check_simulated_video_pacing.py --configuration Debug
```

## 结束测试

网页点“停止推流”，关闭自己打开的 Qt 窗口。若模拟器由你在本轮启动，再运行 `.\simulator\scripts\stop.ps1`。复用原来已在运行的服务时可以让它继续运行。

## 完整启动参数和排查

- [Windows 启动方式与全部参数](../../docs/planning/12_Build_and_Run.md#6-模拟器-windows-启动方式与全部参数)
- [检查、停止和日志](../../docs/planning/12_Build_and_Run.md#8-模拟器检查停止和运行日志)
