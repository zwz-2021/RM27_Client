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
