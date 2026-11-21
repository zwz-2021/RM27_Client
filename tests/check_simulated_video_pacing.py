"""Replay a local 1080p60 recording through the web simulator sender and the normal Qt window.

The default is the 62.7-second recording from the reported incident (kept locally).
Use --recording to test another 1080p60 MP4 with compressed pictures larger than 64 KiB.
"""
import argparse
import asyncio
from contextlib import AsyncExitStack
import csv
from datetime import datetime
from fractions import Fraction
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import traceback
import uuid

from amqtt.broker import Broker
from check_hevc_decode import json_file
from check_mqtt_receive import ROOT, require
from check_udp_receive import exclusive_udp, open_window
from simulator.server.video_streamer import VideoStreamer


class MeasuredSocket:
    """Observe successful datagrams and each complete outgoing frame on the sender thread."""

    def __init__(self, sock):
        self.sock = sock
        self.packets = 0
        self.frames = []
        self.first_ns = 0

    def sendto(self, packet, target):
        before = time.perf_counter_ns()
        count = self.sock.sendto(packet, target)
        require(count == len(packet), "Short UDP send")
        frame, part, size = struct.unpack_from("!HHI", packet)
        self.packets += 1
        if part == 0:
            self.first_ns = before
        if part * 1392 + count - 8 == size:
            self.frames.append((frame, size, part + 1, self.first_ns, time.perf_counter_ns()))
        return count

    def close(self):
        self.sock.close()


def recording_frames(path):
    require(path.is_file(), f"Recording missing: {path}. Supply a local 1080p60 MP4 with --recording.")
    metadata = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,avg_frame_rate,nb_frames", "-of", "json", str(path)], timeout=30)
    video = json.loads(metadata)["streams"][0]
    require((video["width"], video["height"], Fraction(video["avg_frame_rate"])) == (1920, 1080, 60),
            "This incident regression requires a 1920x1080, 60 fps recording")
    require(str(video.get("nb_frames", "")).isdigit(), "MP4 must provide its source frame count")
    return int(video["nb_frames"])


async def verify(path, configuration, evidence, report):
    frame_count = recording_frames(path)
    # Keep streaming into the next cycle to include seek/decoder restart stalls.
    target_frames = frame_count + 60
    with exclusive_udp(0) as reservation:
        port = reservation.getsockname()[1]
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
        "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}},
    })
    async with AsyncExitStack() as services:
        await broker.start()
        services.push_async_callback(broker.shutdown)
        mqtt_port = broker._servers["default"].instance.sockets[0].getsockname()[1]
        title = "RM27 local video cadence " + uuid.uuid4().hex
        config = evidence / "infantry.json"
        json_file(config, {"mode": "simulation", "seat": "infantry",
                           "window": {"width": 960, "height": 760, "title": title},
                           "mqtt": {"host": "127.0.0.1", "port": mqtt_port, "robotId": 3},
                           "video": {"bindAddress": "127.0.0.1", "port": port}})
        async with open_window(config, title, configuration, trace_video=True) as window:
            await window.observe("session ready", connectionValue="^六类订阅就绪$", videoPreviewStatus="^等待模拟画面$")
            waiting = await window.action("capturePreview")
            streamer = VideoStreamer("127.0.0.1", port)
            trace = MeasuredSocket(streamer.sock)
            streamer.sock = trace
            try:
                streamer.start()
                require(streamer.set_video_file(str(path)) and streamer.start_streaming(), "Recording did not start")
                await window.observe("playing the recording", videoPreviewStatus="^正在播放$")
                playing = await window.action("capturePreview")
                require(playing["rgb"] != waiting["rgb"], "The displayed recording still matches the empty surface")
                shutil.copyfile(evidence / "capture.png", evidence / "playing.png")
                deadline = time.monotonic() + target_frames / 60 * 2 + 10
                while len(trace.frames) < target_frames:
                    require(streamer.is_streaming, f"Sender stopped early: {streamer.error}")
                    require(time.monotonic() < deadline, "Sender failed to finish one full recording")
                    await asyncio.sleep(0.02)
            finally:
                streamer.stop()
            # The looping sender can finish another picture before stop. Count every datagram it actually sent.
            with (evidence / "frames.csv").open("w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(("frame", "bytes", "datagrams", "first_ns", "last_ns"))
                writer.writerows(trace.frames)
            gaps_ms = [(b[3] - a[4]) / 1e6 for a, b in zip(trace.frames, trace.frames[1:])]
            longest = max(range(len(gaps_ms)), key=gaps_ms.__getitem__)
            report.update(sourceFrames=frame_count, sentFrames=len(trace.frames), sentPackets=trace.packets,
                          maxFrameBytes=max(row[1] for row in trace.frames),
                          sendMaxGapMs=round(gaps_ms[longest], 3), frameAfterMaxGap=trace.frames[longest + 1][0],
                          sendOver100ms=sum(g > 100 for g in gaps_ms))
            await window.observe("last frame is marked stale", videoPreviewStatus="^画面已过期$")
            await window.action("diagnosticsTab")
            view = await window.observe("decoder drained", videoDecodeLabel=r"等待输入.*已解码 [1-9]\d* 帧")
            report["window"] = view

    with exclusive_udp(port):
        pass
    rows = [json.loads(line) for line in next(evidence.glob("client-*.jsonl")).read_text(encoding="utf-8").splitlines()]
    timings = [json.loads(row["detail"]) for row in rows if row["event"] == "video.display_timing"]
    require(len(timings) == 1, "Expected one timing summary from the product's video sink")
    timing = report["displayWhileReceiving"] = timings[0]
    require(report["maxFrameBytes"] > 65536, "Fixture did not exercise a large burst")
    require(view["udpCountersLabel"].startswith(f"有效包 {trace.packets} · 丢弃 0（"), "Missing or invalid UDP packets")
    require(f"完整帧 {len(trace.frames)} · 丢帧 0（超时 0" in view["udpAssemblyLabel"], "Missing or expired frames")
    require(f"已解码 {len(trace.frames)} 帧" in view["videoDecodeLabel"] and
            "输入丢弃 0 帧" in view["videoDecodeLabel"] and "\n" not in view["videoDecodeLabel"],
            "Incomplete or corrupted decode")
    # The UI keeps only its latest decoded picture. Allow a little coalescing and
    # the final decoder drain, while requiring actual delivery of most source pictures.
    coverage = timing["intervals"] / len(trace.frames)
    report["displayIntervalCoverage"] = round(coverage, 4)
    require(coverage >= 0.9, "GUI intervals covered less than 90% of the stream")
    require(report["sendOver100ms"] == 0, f"Sender stalled: {report['sendMaxGapMs']} ms")
    require(timing["over100ms"] == 0, f"Display stalled during input: {timing}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    parser.add_argument("--recording", type=Path, default=ROOT / "simulator/resources/videos/demo-1080p60-hevc.mp4")
    args = parser.parse_args()
    directory = ROOT / "logs" / datetime.now().strftime("check-simulated-pacing-%Y%m%d-%H%M%S-%f")
    directory.mkdir(parents=True)
    report = {"passed": False, "recording": str(args.recording.resolve()), "configuration": args.configuration,
              "timingWindow": "One loop plus at least 60 more frames. Consecutive successful UDP sends "
                              "between frames and consecutive GUI sink deliveries up to the last accepted input; "
                              "excludes initial startup and the final decoder drain."}
    print(f"Qt recording cadence evidence: {directory}", flush=True)
    try:
        asyncio.run(verify(args.recording.resolve(), args.configuration, directory, report))
        report["passed"] = True
        print(f"PASS: {report['sentFrames']} frames, {report['sentPackets']} packets, no long gaps.")
    except Exception:
        report["error"] = traceback.format_exc()
        print(report["error"], file=sys.stderr)
    json_file(directory / "summary.json", report)
    raise SystemExit(0 if report["passed"] else 1)
