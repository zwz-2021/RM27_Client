"""Check both RM27 video senders against an independent loopback UDP capture.

Run from the repository root: python -m simulator.tools.check_video_datagrams
Requires FFmpeg with libx264 and libx265 on PATH.
"""

from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

from simulator.server.hevc_annexb import HevcAnnexBFrameExtractor
from simulator.server.video_datagrams import send_video_frame
from simulator.server.video_streamer import VideoStreamer
from simulator.tools.video_sender import send_video_as_hevc_udp


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_known_bytes(capture):
    target = capture.getsockname()
    full_piece = bytes(range(16)) * 87  # 1392 bytes
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        send_video_frame(sender, target, 65535, full_piece + b"Z")
        send_video_frame(sender, target, 65536, b"W")
    expected = (
        bytes.fromhex("ff ff 00 00 00 00 05 71") + full_piece,
        bytes.fromhex("ff ff 00 01 00 00 05 71") + b"Z",
        bytes.fromhex("00 00 00 00 00 00 00 01") + b"W",
    )
    for packet in expected:
        check(capture.recv(65535) == packet, "Fixed big-endian wire sample mismatch")
    print("Fixed wire samples passed: 1400/9/9 bytes, frame IDs 65535/65535/0.")


def check_incremental_extractor():
    # A large first slice spans many reads. A continuation slice belongs to the
    # same frame; the prefix SEI after it belongs to the following frame.
    vps = bytes.fromhex("00 00 00 01 40 01 11")
    slice1 = bytes.fromhex("00 00 01 02 01 80") + b"x" * 120000
    continuation = bytes.fromhex("00 00 00 01 02 01 00 33")
    sei = bytes.fromhex("00 00 01 4e 01 44")
    slice2 = bytes.fromhex("00 00 00 01 02 01 80 55")
    expected = [vps + slice1 + continuation, sei + slice2, slice2]
    stream = b"junk" + b"".join(expected)
    extractor = HevcAnnexBFrameExtractor()
    for chunk_size in (1, 3, 4096, 65536):
        extractor.push(slice1[:-2])
        extractor.reset()
        frames = []
        for offset in range(0, len(stream), chunk_size):
            frames.extend(extractor.push(stream[offset:offset + chunk_size]))
        frames.extend(extractor.flush())
        check(frames == expected, f"Annex B frame changed with chunk size {chunk_size}")
    print("Incremental Annex B: split prefixes, large NAL, multi-slice, reset and final frame passed.")


def check_short_pipe_read(clip):
    # The encoder keeps its pipe open after a few tiny pictures. The first
    # picture must reach the receiver without waiting for 4096 bytes or EOF.
    pictures = (bytes.fromhex("00 00 00 01 02 01 80 55"), bytes.fromhex("00 00 00 01 02 01 80 66"))
    child = ("import sys, time; sys.stdout.buffer.write(bytes.fromhex(sys.argv[1])); "
             "sys.stdout.buffer.flush(); time.sleep(30)")
    popen = subprocess.Popen
    sessions = iter(pictures)
    def small_frames(_cmd, **kwargs):
        return popen([sys.executable, "-c", child, (next(sessions) * 8).hex()], **kwargs)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as capture:
        capture.bind(("127.0.0.1", 0))
        capture.settimeout(5)
        streamer = VideoStreamer(*capture.getsockname())
        stopped = threading.Event()
        send_frame = streamer._send_frame
        def stop_after_first(frame):
            send_frame(frame)
            if not stopped.is_set():
                # Stop at a deterministic boundary inside a multi-frame pipe read.
                streamer.stop_streaming()
                stopped.set()

        with patch("subprocess.Popen", small_frames):
            try:
                streamer._send_frame = stop_after_first
                streamer.start()
                check(streamer.set_video_file(str(clip)) and streamer.start_streaming(), "Small pipe setup failed")
                check(capture.recv(65535) == bytes.fromhex("00 00 00 00 00 00 00 08") + pictures[0],
                      "Small frame was not delivered from the live pipe")
                check(stopped.wait(5) and streamer.start_streaming(), "Small pipe restart failed")
                check(capture.recv(65535) == bytes.fromhex("00 01 00 00 00 00 00 08") + pictures[1],
                      "A frame from the stopped read reached the new stream")
            finally:
                streamer.stop()
    print("Short picture sent before EOF; stopping inside a read discarded the remaining old pictures.")


def capture_frame(capture, expected_id):
    received = 0
    slice_id = 0
    total = 0
    max_packet = 0
    while slice_id == 0 or received < total:
        packet = capture.recv(65535)
        check(8 < len(packet) <= 1400, f"Invalid datagram length {len(packet)}")
        check(int.from_bytes(packet[:2], "big") == expected_id, f"Expected frame {expected_id}")
        check(int.from_bytes(packet[2:4], "big") == slice_id, f"Expected simulator slice {slice_id}")
        frame_size = int.from_bytes(packet[4:8], "big")
        if slice_id == 0:
            total = frame_size
        check(total == frame_size, f"Frame {expected_id} changed total size")
        received += len(packet) - 8
        max_packet = max(max_packet, len(packet))
        slice_id += 1
    check(received == total, f"Frame {expected_id}: {received} payload bytes, header says {total}")
    print(f"Frame {expected_id}: {total} bytes in {slice_id} datagrams, largest {max_packet}.")
    return max_packet


def expect_web_failure(streamer, clip, message):
    check(streamer.set_video_file(str(clip)) and streamer.start_streaming(), "Bad fixture setup")
    deadline = time.monotonic() + 10
    while streamer.is_streaming or streamer.ffmpeg_process is not None:
        check(time.monotonic() < deadline, "Simulator kept running after failed input")
        time.sleep(0.05)
    error = streamer.get_status()["error"]
    check(message in error, f"Unexpected simulator failure: {error}")
    print(f"Simulator input stopped: {error}")


def main():
    check_incremental_extractor()
    with tempfile.TemporaryDirectory(prefix="rm27-video-udp-") as directory:
        clip = Path(directory) / "four-frames.mp4"
        broken = Path(directory) / "broken.mp4"
        broken.write_bytes(b"not a video")
        subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=blue:size=1920x1080:rate=60",
            "-frames:v", "4", "-c:v", "libx264", str(clip),
        ], check=True, timeout=20)
        check_short_pipe_read(clip)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as capture:
            capture.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
            capture.bind(("127.0.0.1", 0))
            capture.settimeout(10)
            target = capture.getsockname()
            check_known_bytes(capture)
            failed = subprocess.run([
                sys.executable, "-X", "utf8", "-m", "simulator.tools.video_sender",
                str(broken), target[0], str(target[1]),
            ], capture_output=True, encoding="utf-8", timeout=10)
            check(failed.returncode != 0 and "FFmpeg" in failed.stderr and "退出码" in failed.stderr,
                  f"Broken clip did not fail clearly: {failed.returncode}, {failed.stderr}")
            print(f"Broken CLI input: exit {failed.returncode}, {failed.stderr.strip()}")
            send_video_as_hevc_udp(str(clip), *target, loop=False)
            sizes = [capture_frame(capture, frame_id) for frame_id in range(4)]
            check(max(sizes) == 1400, "Standalone sender did not exercise a full-size datagram")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as capture:
            capture.bind(("127.0.0.1", 0))
            capture.settimeout(10)
            streamer = VideoStreamer(*capture.getsockname())
            streamer.frame_id = 65535
            try:
                streamer.start()
                expect_web_failure(streamer, broken, "退出码")
                # Exercise the separate zero-exit/empty-output branch with an actual empty child process.
                popen = subprocess.Popen
                def empty_encoder(_cmd, **kwargs):
                    return popen([sys.executable, "-c", "pass"], **kwargs)
                with patch("subprocess.Popen", empty_encoder):
                    try:
                        send_video_as_hevc_udp(str(clip), *capture.getsockname(), loop=False)
                    except RuntimeError as error:
                        check("没有输出视频帧" in str(error), f"Unexpected CLI failure: {error}")
                    else:
                        raise RuntimeError("CLI accepted zero-exit encoder with empty output")
                    expect_web_failure(streamer, clip, "没有输出视频帧")
                check(streamer.set_video_file(str(clip)), "Simulator did not accept video fixture")
                check(streamer.start_streaming(), "Simulator did not start streaming")
                sizes = [capture_frame(capture, frame_id) for frame_id in (65535, 0, 1, 2, 3, 4)]
                check(max(sizes) == 1400, "Simulator did not exercise a full-size datagram")
                streamer.stop_streaming()
                status = streamer.get_status()
                check(not status["is_streaming"] and not status["error"], "Normal stop reported an error")
            finally:
                streamer.stop()
            check(not streamer._worker.is_alive() and streamer.ffmpeg_process is None
                  and streamer.sock.fileno() == -1, "Simulator did not release video resources")
    print("Both video senders passed: corrupt source, normal transmission, loopback datagrams and cleanup.")


if __name__ == "__main__":
    main()
