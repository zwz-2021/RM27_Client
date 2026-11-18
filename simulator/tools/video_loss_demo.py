"""在本机回环演示已知画面、缺一片并暂停、完整新片段恢复。"""

import argparse
import socket
import subprocess
import time

from simulator.server.hevc_annexb import HevcAnnexBFrameExtractor
from simulator.server.video_datagrams import send_video_frame


FPS = 60


def make_clip(color: str) -> list[bytes]:
    """生成一秒 1080p60 测试片，首帧自带参数集及 IDR。"""
    encoded = subprocess.run([
        "ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
        f"color=c={color}:size=1920x1080:rate={FPS}", "-frames:v", str(FPS),
        "-c:v", "libx265", "-preset", "ultrafast", "-tune", "zerolatency",
        "-x265-params", "log-level=error:pools=2:repeat-headers=1:open-gop=0:keyint=60:scenecut=0",
        "-pix_fmt", "yuv420p", "-f", "hevc", "pipe:1",
    ], stdout=subprocess.PIPE, timeout=30, check=True)
    extractor = HevcAnnexBFrameExtractor()
    frames = extractor.push(encoded.stdout) + extractor.flush()
    if len(frames) != FPS:
        raise ValueError(f"测试片应有 {FPS} 帧，实际生成 {len(frames)} 帧")
    return frames


def send_clip(sock: socket.socket, port: int, first_id: int, clip: list[bytes], loops: int = 1) -> int:
    target = ("127.0.0.1", port)
    start = time.monotonic()
    count = 0
    for index in range(len(clip) * loops):
        remaining = start + index / FPS - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        packets, _ = send_video_frame(sock, target, first_id + index, clip[index % len(clip)])
        count += packets
    return count


class _FrameCapture:
    """只暂存这一帧按正常模拟器路径生成的 UDP 包，选好漏片后再发出。"""

    def __init__(self):
        self.datagrams: list[bytes] = []

    def sendto(self, datagram: bytes, target: tuple[str, int]) -> int:
        self.datagrams.append(datagram)
        return len(datagram)


def send_incomplete(sock: socket.socket, port: int, frame_id: int, frame: bytes) -> dict:
    target = ("127.0.0.1", port)
    capture = _FrameCapture()
    send_video_frame(capture, target, frame_id, frame)
    datagrams = capture.datagrams
    if len(datagrams) < 2:
        raise ValueError("缺片测试帧至少需要两个分片")
    omitted = 1
    for index, datagram in enumerate(datagrams):
        if index != omitted:
            sock.sendto(datagram, target)
    return {"frameId": frame_id % 65536, "frameBytes": len(frame), "sliceCount": len(datagrams),
            "omittedSlice": omitted, "sentPackets": len(datagrams) - 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=3334, help="本机客户端的 UDP 端口，默认 3334")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口应在 1 至 65535 之间")
    print("正在生成红、蓝两段 1080p60 测试片。请在客户端打开工作台，网页停止推流。", flush=True)
    red, blue = make_clip("red"), make_clip("blue")
    loops = 5
    damaged_id = len(red) * loops
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        print(f"向 127.0.0.1:{args.port} 发送五秒红色画面。", flush=True)
        send_clip(sock, args.port, 0, red, loops)
        loss = send_incomplete(sock, args.port, damaged_id, blue[0])
        print(f"第 {damaged_id} 帧共 {loss['sliceCount']} 片，已故意漏发片号 {loss['omittedSlice']}。"
              "图传已暂停，等待末帧过期。", flush=True)
        time.sleep(2)
        input("请检查红色末帧过期、组帧超时及网页血量更新。回到工作台后，在这里按回车恢复。")
        print("正在发送五秒蓝色画面。", flush=True)
        send_clip(sock, args.port, damaged_id + 1, blue, loops)
    print("发送结束。客户端应保留蓝色末帧，随后显示过期。")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        raise SystemExit("已结束本机测试发送。") from None
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f"本机缺片测试失败：{error}") from None
