# 视频库文档入口

- [模块职责与图传边界](../../docs/planning/11_Architecture.md)
- [UDP 图传契约](../../docs/planning/03_Protocol_Coverage.md#udp视频独立覆盖)
- [测试视频与发送入口](../../docs/planning/12_Build_and_Run.md#7-视频文件上传与发送入口)

## 本地 HEVC 解码检查

在仓库根目录执行以下命令。构建使用项目的 Qt/MinGW 预设，检查脚本使用 Python 3、PATH 中的 FFmpeg（含 libx265）和 ffprobe。

```powershell
.\scripts\build.ps1 -Configuration Release -HevcProbe
python tests/check_hevc_decode.py --configuration Release
```

脚本会在输出的证据目录中生成 `known-1080p60.hevc`，用编码前的像素逐帧验证解码结果。也可将任意本地 Annex B HEVC 文件传给 `.\scripts\run.ps1 -Configuration Release -SkipBuild -HevcFile <文件路径>`。每个 `frame` 行给出显示序号、尺寸和像素摘要。最后的 `summary` 行给出完整帧数和结束状态。加 `-StopAfter 3` 可观察提前停止。

### 手动核对同一文件损坏后恢复

先运行上面的构建和回归命令。看到 `PASS: same-stream recovery` 后，在同一 PowerShell 中取刚生成的样本和像素核对结果。

```powershell
$report = Get-ChildItem .\logs\check-hevc-*\summary.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$recovery = (Get-Content -LiteralPath $report.FullName -Raw -Encoding UTF8 | ConvertFrom-Json).sameStreamRecovery
$recovery | Select-Object firstRecoveredOutputIndex, matchedRecoveryFrames
.\scripts\run.ps1 -Configuration Release -SkipBuild -HevcFile $recovery.file
$LASTEXITCODE
```

`firstRecoveredOutputIndex` 是第二段关键帧在输出中的序号，从 1 起算。`matchedRecoveryFrames` 应为 12，表示从关键帧到文件末尾逐帧匹配编码前的像素。每次运行都写入独立目录，可查看其中的 `recovery.jsonl` 和 `summary.json`。

手动打开这个故意截坏的样本会继续输出帧，末行是 `completed_with_errors`，`diagnostic` 保留 FFmpeg 的错误详情。此时启动脚本会报退出码 1，表示样本有损坏。只有末尾受损的文件也可能得到这个状态；用上述像素比对确定恢复位置。仅缺 PPS 的对照文件 `no-pps.hevc` 应为 0 帧、`error`。指定帧数提前停止会显示 `stopped`，已读到的错误也会保留并返回 1。自动回归在这些现象全部符合预期时返回 0。
