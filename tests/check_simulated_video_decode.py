"""Check local simulator HEVC pixels through the normal Qt window and real loopback UDP."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import traceback
import uuid

from amqtt.broker import Broker
from check_hevc_decode import HEIGHT, WIDTH, compare_frames, json_file
from check_mqtt_receive import ROOT, TOPICS, require
from check_udp_receive import exclusive_udp, open_window
from simulator.server.video_streamer import VideoStreamer
from simulator.tools.video_sender import send_video_as_hevc_udp


def make_recording(directory, name, levels, u, v):
    # Uniform planes survive the simulator's ordinary lossy transcode. Compute the
    # oracle before either encoder sees the pixels, including both chroma planes.
    clip = directory / f"{name}.mkv"
    hashes = []
    size = WIDTH * HEIGHT
    chroma = bytes([u]) * (size // 4) + bytes([v]) * (size // 4)
    with TemporaryDirectory(prefix="rm27-sim-video-") as folder:
        raw = Path(folder) / "planes.yuv"
        with raw.open("wb") as file:
            for y in levels:
                frame = bytes([y]) * size + chroma
                file.write(frame)
                hashes.append(hashlib.sha256(frame).hexdigest())
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "yuv420p",
                        "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", "60", "-i", str(raw),
                        "-c:v", "ffv1", str(clip)], check=True, timeout=30)
    json_file(directory / f"{name}-oracle.json", {"width": WIDTH, "height": HEIGHT, "rate": 60,
              "y": list(levels), "u": u, "v": v, "sha256": hashes})
    return clip, hashes


async def stop_and_check(window, port):
    await window.action("overviewTab")
    await window.action("stopButton")
    await window.observe("manual stop accepted", connectionValue="^已停止$")
    await window.action("diagnosticsTab")
    await window.observe("cleared video counters after stop", udpBindingLabel="已停止",
                         udpAssemblyLabel=r"完整帧 0\b", videoDecodeLabel=r"已解码 0 帧")
    with exclusive_udp(port):
        pass


async def verify(configuration, evidence):
    levels = range(32, 209, 16)
    live_file, live_hashes = make_recording(evidence, "loop", levels, 96, 160)
    finite_file, finite_hashes = make_recording(evidence, "finite", levels[::-1], 160, 96)
    require(len(set(live_hashes + finite_hashes)) == len(levels) * 2, "Frames from both runs must be distinct")
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
        "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
                    "check_mqtt_receive.RecoveryPacketLog": {}},
    })
    title = "RM27 local decode " + uuid.uuid4().hex
    with exclusive_udp(0) as reservation:
        port = reservation.getsockname()[1]
    target = ("127.0.0.1", port)
    async with AsyncExitStack() as services:
        await broker.start()
        services.push_async_callback(broker.shutdown)
        mqtt_port = broker._servers["default"].instance.sockets[0].getsockname()[1]
        packets = broker.plugins_manager.get_plugin("RecoveryPacketLog").packets
        config = evidence / "simulation.json"
        json_file(config, {"mode": "simulation",
                  "window": {"title": title, "width": 900, "height": 680},
                  "mqtt": {"host": "127.0.0.1", "port": mqtt_port, "robotId": 3, "connectTimeoutMs": 1200},
                  "video": {"bindAddress": target[0], "port": port}})
        async with open_window(config, title, configuration, trace_video=True) as window:
            await window.observe("legacy profile starts without a selected seat",
                                 connectionValue="^六类订阅就绪$", seatLabel=r"未指定（只读）")
            with exclusive_udp(port):
                pass
            await window.action("stopButton")
            await window.observe("profile is editable", connectionValue="^已停止$")
            await window.action("saveReceiverButton")
            await window.observe("saved personal infantry seat without closing the window", seatLabel=r"步兵（只读）")
            require(json.loads(config.read_text(encoding="utf-8"))["seat"] == "infantry", "Seat was not saved")
            await window.action("startButton")
            await window.observe("first infantry receive session", connectionValue="^六类订阅就绪$")
            await window.action("diagnosticsTab")
            await window.observe("waiting for first recording", udpBindingLabel=rf"已绑定 127\.0\.0\.1:{port}\b",
                                 videoDecodeLabel=r"已解码 0 帧")
            streamer = VideoStreamer(*target)
            try:
                streamer.start()
                require(streamer.set_video_file(str(live_file)) and streamer.start_streaming(),
                        "The web simulator's video service did not start")
                view = await window.observe("pixels while the web simulator is still streaming",
                                            videoDecodeLabel=r"(?s)已解码 ([1-9]\d*) 帧.*1920×1080")
                observed = int(re.search(r"已解码 (\d+) 帧", view["videoDecodeLabel"])[1])
                require(streamer.is_streaming and not streamer.error, f"Web sender stopped: {streamer.error}")
                await asyncio.to_thread(send_video_as_hevc_udp, str(finite_file), *target, loop=False)
                view = await window.observe("competing recording ignored while the first one keeps decoding",
                                            videoDecodeLabel=rf"(?s)已解码 (?!{observed} 帧)[1-9]\d* 帧.*"
                                                             rf"忽略其他发送端 {len(levels)} 帧")
                continued = int(re.search(r"已解码 (\d+) 帧", view["videoDecodeLabel"])[1])
                require(continued > observed, "First recording stopped making progress when the second one arrived")
                await stop_and_check(window, port)
            finally:
                streamer.stop()
            require(not streamer._worker.is_alive() and streamer.ffmpeg_process is None and streamer.sock.fileno() == -1,
                    "The web simulator kept its encoder, worker or socket after stop")
            await window.action("overviewTab")
            await window.action("startButton")
            await window.observe("reopened MQTT session", connectionValue="^六类订阅就绪$")
            await services.aclose()
            await window.observe("broker is offline during the finite recording", connectionValue="^等待重连$")
            await window.action("diagnosticsTab")
            await window.observe("fresh session without old input or output", udpAssemblyLabel=r"完整帧 0\b",
                                 videoDecodeLabel=r"已解码 0 帧")
            await asyncio.to_thread(send_video_as_hevc_udp, str(finite_file), *target, loop=False)
            await window.observe("finite input decoded through its last picture while MQTT is offline",
                                 udpAssemblyLabel=rf"完整帧 {len(levels)}\b",
                                 videoDecodeLabel=rf"(?s)等待输入.*已解码 {len(levels)} 帧.*1920×1080"
                                                  r".*排队 0 帧 / 0 字节.*输入丢弃 0 帧")
            await stop_and_check(window, port)

    # The opt-in product trace records only the first 32 decoded pictures of each
    # session. The complete finite input is smaller than that bound.
    log_file, = evidence.glob("client-*.jsonl")
    rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    traces = [json.loads(row["detail"]) for row in rows if row["event"] == "video.decode_frame"]
    starts = [i for i, frame in enumerate(traces) if frame["index"] == 1]
    require(len(starts) == 2 and starts[0] == 0, f"Expected exactly two sessions of traced pixels, got {starts}")
    live_trace, finite_trace = traces[:starts[1]], traces[starts[1]:]
    require(1 <= len(live_trace) <= 32, "Expected bounded live pixel evidence")
    live_expected = [live_hashes[i % len(live_hashes)] for i in range(len(live_trace))]
    compare_frames(live_trace, live_expected)
    compare_frames(finite_trace, finite_hashes)
    json_file(evidence / "broker-packets.json", packets)
    topics = [tuple(pair) for row in packets if row["kind"] == "subscribe" for pair in row["topics"]]
    require(sorted(topics) == sorted([(topic, 1) for topic in TOPICS] * 3), "Expected three six-topic sessions")
    require(not any(row["kind"] == "client-publish" for row in packets), "Unexpected client business publish")
    with exclusive_udp(port), socket.socket() as probe:
        probe.settimeout(1)
        require(probe.connect_ex(("127.0.0.1", mqtt_port)) != 0, "Test broker still listening")
    return {"profileSavedFromUnspecified": True, "liveFramesSeenBeforeStop": continued,
            "otherSenderFramesIgnored": len(levels),
            "liveTraceFrames": len(live_trace),
            "finiteFramesMatchedInOrder": len(finite_trace), "clientBusinessPublishes": 0,
            "releasedUdpPort": port, "releasedBrokerPort": mqtt_port, "clientLog": log_file.name}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    options = parser.parse_args()
    directory = ROOT / "logs" / datetime.now().strftime("check-simulated-decode-%Y%m%d-%H%M%S-%f")
    directory.mkdir(parents=True)
    print(f"Qt simulated decoder evidence: {directory}", flush=True)
    result = {"passed": False, "configuration": options.configuration, "entry": "scripts/run.ps1"}
    try:
        result.update(asyncio.run(verify(options.configuration, directory)))
        result["passed"] = True
        print(f"PASS: live pixels before stop, then all {result['finiteFramesMatchedInOrder']} finite frames in order.")
    except Exception:
        result["error"] = traceback.format_exc()
        print(result["error"], file=sys.stderr)
    json_file(directory / "summary.json", result)
    raise SystemExit(0 if result["passed"] else 1)
