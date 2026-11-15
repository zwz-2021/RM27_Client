#!/usr/bin/env python3
"""
video_sender.py - RoboMaster 2027 视频协议测试发送器

根据官方协议规范，将视频文件转换为 HEVC 并通过 UDP 发送。

UDP 包格式（8 字节头部）：
┌────────────┬──────────────┬──────────────┬────────────────┐
│ FrameID(2) │ SliceID(2)   │ TotalBytes(4)│ HEVC Data (N)  │
│  大端序     │  大端序       │  大端序       │  裸码流数据     │
└────────────┴──────────────┴──────────────┴────────────────┘

用法：
  python3 video_sender.py [视频文件] [目标IP] [目标端口]

示例：
  python3 video_sender.py testdemo.mov 127.0.0.1 3334
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

SIMULATOR_ROOT = Path(__file__).resolve().parent.parent
# Direct script execution needs the parent of the simulator package.
if __package__ in (None, "") and str(SIMULATOR_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(SIMULATOR_ROOT.parent))

from simulator.server.hevc_annexb import HevcAnnexBFrameExtractor
from simulator.server.video_datagrams import MAX_DATAGRAM_BYTES, send_video_frame

# 配置常量
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3334


def send_video_as_hevc_udp(video_path: str, host: str, port: int, loop: bool = True):
    """
    将视频转换为 HEVC 并通过 UDP 发送

    Args:
        video_path: 输入视频文件路径
        host: 目标 IP 地址
        port: 目标端口号（官方协议为 3334）
        loop: 是否循环播放（默认 True）
    """
    # 创建 UDP 套接字
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    frame_count = 0
    total_bytes_sent = 0
    extractor = HevcAnnexBFrameExtractor()
    process = None

    print(f"[video_sender] 开始发送到 {host}:{port}")
    print(f"[video_sender] UDP 整包上限: {MAX_DATAGRAM_BYTES} 字节")
    print(f"[video_sender] 循环模式: {'开启' if loop else '关闭'}")

    try:
        ffmpeg_cmd = [
            "ffmpeg",
            "-re",
        ]
        if loop:
            ffmpeg_cmd += ["-stream_loop", "-1"]
        ffmpeg_cmd += [
            "-i",
            video_path,
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-x265-params",
            "keyint=30:min-keyint=30:scenecut=0",
            "-bsf:v",
            "hevc_mp4toannexb",
            "-an",
            "-f",
            "hevc",
            "-",
        ]

        print(f"[video_sender] 启动 FFmpeg 转码...")
        print(f"[video_sender] 命令: {' '.join(ffmpeg_cmd)}")

        process = subprocess.Popen(
            ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        start_time = time.time()

        while True:
            chunk = process.stdout.read(4096)
            frames = extractor.push(chunk) if chunk else extractor.flush()
            for frame_data in frames:
                num_slices, bytes_sent = send_video_frame(sock, (host, port), frame_count, frame_data)
                total_bytes_sent += bytes_sent
                if frame_count % 30 == 0:
                    bitrate = (
                        total_bytes_sent
                        * 8
                        / max(time.time() - start_time, 0.001)
                        / 1024
                        / 1024
                    )
                    print(
                        f"[video_sender] Frame {frame_count}, Bitrate: {bitrate:.2f} Mbps, Slices: {num_slices}"
                    )
                frame_count += 1
            if not chunk:
                break

        code = process.wait(timeout=2)
        if code:
            raise RuntimeError(f"FFmpeg 未能完成视频转码（退出码 {code}），请检查视频文件。")
        if not frame_count:
            raise RuntimeError("FFmpeg 没有输出视频帧，请检查视频文件。")

    except KeyboardInterrupt:
        print("\n[video_sender] 用户中断")
    finally:
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                    process.wait(timeout=2)
                except Exception:
                    pass
            finally:
                if process.stdout:
                    process.stdout.close()
        sock.close()

        print("\n[video_sender] 发送统计:")
        print(f"  总帧数: {frame_count}")
        print(f"  总字节: {total_bytes_sent / 1024 / 1024:.2f} MB")
        print(f"  循环模式: {'开启' if loop else '关闭'}")


def main():
    # 解析命令行参数
    if len(sys.argv) < 2:
        print("用法: python3 video_sender.py <视频文件> [目标IP] [目标端口]")
        print("示例: python3 video_sender.py testdemo.mov 127.0.0.1 3334")
        sys.exit(1)

    video_file = Path(sys.argv[1]).expanduser()
    if not video_file.is_absolute():
        # Paths are simulator-relative rather than dependent on the caller cwd.
        candidate = SIMULATOR_ROOT / video_file
        video_file = candidate if candidate.is_file() else SIMULATOR_ROOT / "resources/videos" / video_file
    video_path = str(video_file.resolve())
    if not video_file.is_file():
        raise SystemExit(f"视频文件不存在: {video_path}")
    host = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_HOST
    port = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_PORT

    print("[video_sender] RoboMaster 2027 视频协议测试发送器")
    print(f"[video_sender] 视频文件: {video_path}")
    print(f"[video_sender] 目标地址: {host}:{port}")
    print()

    try:
        send_video_as_hevc_udp(video_path, host, port)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"[video_sender] 图传发送失败：{error}") from None


if __name__ == "__main__":
    main()
