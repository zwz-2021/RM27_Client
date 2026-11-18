"""在本机回环用红、蓝合成录屏演示视频缺片、乱序与恢复。"""

import argparse
import re
import socket
import subprocess
import time

from simulator.server.hevc_annexb import HevcAnnexBFrameExtractor
from simulator.server.video_datagrams import send_video_frame


FPS = 60
LOSS_GROUPS = 16
LOSS_GROUP_SIZE = 12


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


def dependent_frames(clip: list[bytes]) -> list[bytes]:
    """取出测试片首个 IDR 后的普通帧，确保其中没有新的解码起点。"""
    frames = clip[1:]
    if not frames:
        raise ValueError("测试片需要包含首帧和后续普通帧")
    for index, frame in enumerate(frames, start=1):
        types = {(header[0] >> 1) & 63 for header in re.findall(b"\x00\x00\x01(.)", frame, re.DOTALL)}
        if not any(0 <= t <= 9 for t in types) or any(16 <= t <= 23 or t in (32, 33, 34) for t in types):
            raise ValueError(f"测试片第 {index} 帧不符合无参数集、无随机接入帧的要求，NAL 类型为 {sorted(types)}")
    return frames


def send_clip(sock: socket.socket, port: int, first_id: int, clip: list[bytes], loops: int = 1,
              *, reverse_first: bool = False) -> int:
    target = ("127.0.0.1", port)
    start = time.monotonic()
    count = 0
    for index in range(len(clip) * loops):
        remaining = start + index / FPS - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        frame = clip[index % len(clip)]
        if reverse_first and index == 0:
            datagrams = _capture_fragments(target, first_id, frame)
            for packet in reversed(datagrams):
                sock.sendto(packet, target)
            count += len(datagrams)
        else:
            packets, _ = send_video_frame(sock, target, first_id + index, frame)
            count += packets
    return count


class _FrameCapture:
    """暂存一帧按正常模拟器路径生成的 UDP 包，供演示工具逐片发送。"""

    def __init__(self):
        self.datagrams: list[bytes] = []

    def sendto(self, datagram: bytes, target: tuple[str, int]) -> int:
        self.datagrams.append(datagram)
        return len(datagram)


def _capture_fragments(target: tuple[str, int], frame_id: int, frame: bytes) -> list[bytes]:
    capture = _FrameCapture()
    send_video_frame(capture, target, frame_id, frame)
    if len(capture.datagrams) < 2:
        raise ValueError("缺片或倒序测试至少需要两个分片")
    return capture.datagrams


def send_incomplete(sock: socket.socket, port: int, frame_id: int, frame: bytes) -> dict:
    target = ("127.0.0.1", port)
    datagrams = _capture_fragments(target, frame_id, frame)
    omitted = 1
    for index, datagram in enumerate(datagrams):
        if index != omitted:
            sock.sendto(datagram, target)
    return {"frameId": frame_id % 65536, "frameBytes": len(frame), "sliceCount": len(datagrams),
            "omittedSlice": omitted, "sentPackets": len(datagrams) - 1}


def send_loss_series(sock: socket.socket, port: int, first_id: int, frame: bytes) -> list[dict]:
    """每组连续发出十二个各缺一片的帧，给上一组留出半秒的回收时间。"""
    manifest = []
    for group in range(LOSS_GROUPS):
        if group:
            time.sleep(0.5)
        for offset in range(LOSS_GROUP_SIZE):
            frame_id = first_id + group * LOSS_GROUP_SIZE + offset
            manifest.append(send_incomplete(sock, port, frame_id, frame))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=3334, help="本机客户端的 UDP 端口，默认 3334")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--wait-for-keyframe", action="store_true", help="恢复前先发缺少参数集和起始关键帧的普通蓝帧")
    mode.add_argument("--consecutive-loss", action="store_true", help="连续发送多组各缺一片的帧，观察过期画面和缓存回收")
    mode.add_argument("--reverse-first-frame", action="store_true", help="待红片过期后，将完整蓝片的首帧分片全部倒序发送")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口应在 1 至 65535 之间")
    print("正在生成红、蓝两段 1080p60 测试片。请在客户端打开工作台，网页停止推流。", flush=True)
    red, blue = make_clip("red"), make_clip("blue")
    ordinary = dependent_frames(blue) if args.wait_for_keyframe else []
    loops = 5
    next_id = len(red) * loops
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        print(f"向 127.0.0.1:{args.port} 发送五秒红色画面。", flush=True)
        send_clip(sock, args.port, 0, red, loops)
        if args.consecutive_loss:
            print(f"开始发送 {LOSS_GROUPS} 组缺片样本，每组 {LOSS_GROUP_SIZE} 帧。"
                  "请观察红色末帧过期，并在网页更改血量，查看工作台是否更新。", flush=True)
            manifest = send_loss_series(sock, args.port, next_id, blue[0])
            print(f"已发完帧号 {next_id} 至 {next_id + len(manifest) - 1} 的 {len(manifest)} 个缺片帧，每帧漏发片号 1。"
                  "请在运行信息查看超时、超出预算和在途帧数。", flush=True)
            next_id += len(manifest)
        elif args.reverse_first_frame:
            print("红片已发完，图传已暂停。红色末帧应标为过期，累计丢帧应为 0。", flush=True)
        else:
            loss = send_incomplete(sock, args.port, next_id, blue[0])
            print(f"第 {next_id} 帧共 {loss['sliceCount']} 片，已故意漏发片号 {loss['omittedSlice']}。"
                  "图传已暂停，等待末帧过期。", flush=True)
            next_id += 1
        time.sleep(2)
        if args.reverse_first_frame:
            input(f"请检查红色末帧过期、运行信息中完整帧为 {next_id} 且丢帧为 0，再按回车。")
        else:
            input("请检查红色末帧过期、组帧超时及网页血量更新。确认后在这里按回车继续。")
        if ordinary:
            count = len(ordinary) * loops
            print(f"约五秒内连续发送 {count} 个普通蓝帧，缺少参数集和起始关键帧。"
                  "请看运行信息中完整帧继续增加，工作台仍保留过期红帧。", flush=True)
            send_clip(sock, args.port, next_id, ordinary, loops)
            next_id += count
            input("普通帧已发完。等尾部排空后，红色画面应仍过期，运行信息应显示解码失败、排队为零。"
                  "按回车发送完整蓝片。")
        if args.reverse_first_frame:
            print(f"蓝片首帧（帧号 {next_id}）的全部分片将倒序发出，后续帧按正常顺序发送。", flush=True)
        print("正在发送五秒蓝色画面。", flush=True)
        send_clip(sock, args.port, next_id, blue, loops, reverse_first=args.reverse_first_frame)
    print("发送结束。客户端应保留蓝色末帧，随后显示过期。")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        raise SystemExit("已结束本机测试发送。") from None
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f"本机录屏测试失败：{error}") from None
