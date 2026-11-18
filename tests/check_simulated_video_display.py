"""Check AT-055 against actual Qt Quick window pixels using prerecorded loopback video."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime
import shutil
import subprocess
import sys
import time
import traceback
import uuid

from amqtt.broker import Broker
from check_hevc_decode import json_file
from check_mqtt_receive import ROOT, TOPICS, require
from check_udp_receive import exclusive_udp, open_window
from simulator.server.video_streamer import VideoStreamer


RED, BLUE, LIME = (255, 0, 0), (0, 0, 255), (0, 255, 0)
YELLOW, CYAN, MAGENTA = (255, 255, 0), (0, 255, 255), (255, 0, 255)
FIRST = [RED, BLUE, LIME, YELLOW]
ALTERNATE = [RED, BLUE, LIME, CYAN]
SECOND = [BLUE, YELLOW, MAGENTA, RED]
EMPTY = [(17, 25, 35)] * 4


def recording(path, base, right, lower_left, lower_right, alternate=None):
    # The four pre-encoding colours are the visible pixel oracle. The first clip
    # changes its lower-right quadrant every second while the same sender runs.
    filters = [f"color=c={base}:size=1920x1080:rate=60:duration=2",
               f"drawbox=x=960:y=0:w=960:h=1080:color={right}:t=fill",
               f"drawbox=x=0:y=540:w=960:h=540:color={lower_left}:t=fill",
               f"drawbox=x=960:y=540:w=960:h=540:color={lower_right}:t=fill"]
    if alternate:
        filters.append(f"drawbox=x=960:y=540:w=960:h=540:color={alternate}:t=fill:enable='gte(t,1)'")
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", ",".join(filters),
                    "-c:v", "ffv1", str(path)], timeout=30, check=True)


async def expect_pixels(window, name, patterns, tolerance=50):
    # Small channel differences are expected after YUV conversion and display colour management.
    deadline = time.monotonic() + 12
    while True:
        image = await window.action("capturePreview")
        rgb = image["rgb"]
        margin = image["sideMargin"]
        # A restored window can paint before its accessible preview bounds settle.
        # Only accept the margin and picture colours together in the same capture.
        dark_margin = len(margin) == 3 and max(margin) <= 45
        for pattern in patterns:
            if (dark_margin and len(rgb) == len(pattern) and
                    all(max(abs(a - b) for a, b in zip(pixel, reference)) <= tolerance
                        for pixel, reference in zip(rgb, pattern))):
                shutil.copyfile(window.evidence / "capture.png", window.evidence / (name + ".png"))
                return {"capture": name + ".png", **image}
        if time.monotonic() >= deadline:
            raise AssertionError(f"{name}: sampled {rgb}, margin {margin}; expected {patterns} "
                                 "with a dark side margin; see capture.png")
        await asyncio.sleep(0.1)


async def verify(configuration, evidence):
    first, second = evidence / "alternating.mkv", evidence / "restored.mkv"
    recording(first, "red", "blue", "lime", "yellow", "cyan")
    recording(second, "blue", "yellow", "magenta", "red")
    with exclusive_udp(0) as reservation:
        port = reservation.getsockname()[1]
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
        "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
                    "check_mqtt_receive.RecoveryPacketLog": {}},
    })
    title = "RM27 simulated display " + uuid.uuid4().hex
    captures = []
    async with AsyncExitStack() as services:
        await broker.start()
        services.push_async_callback(broker.shutdown)
        mqtt_port = broker._servers["default"].instance.sockets[0].getsockname()[1]
        packets = broker.plugins_manager.get_plugin("RecoveryPacketLog").packets
        config = evidence / "infantry.json"
        json_file(config, {"mode": "simulation", "seat": "infantry",
                           "window": {"title": title, "width": 960, "height": 760},
                           "mqtt": {"host": "127.0.0.1", "port": mqtt_port, "robotId": 3},
                           "video": {"bindAddress": "127.0.0.1", "port": port}})
        async with open_window(config, title, configuration) as window:
            await window.observe("waiting for first picture", connectionValue="^五类订阅就绪$",
                                 videoPreviewStatus="^等待模拟画面$")
            captures.append(await expect_pixels(window, "waiting", [EMPTY], tolerance=5))
            streamer = VideoStreamer("127.0.0.1", port)
            try:
                streamer.start()
                require(streamer.set_video_file(str(first)) and streamer.start_streaming(), "Start first recording")
                await window.observe("playing first recording", videoPreviewStatus="^正在播放$")
                captures.append(await expect_pixels(window, "first", [FIRST]))
                captures.append(await expect_pixels(window, "first-changed", [ALTERNATE]))
                await window.action("diagnosticsTab")
                await window.observe("decoder active on diagnostics page", videoDecodeLabel=r"已解码 [1-9]\d* 帧")
                await window.action("overviewTab")
                await window.observe("preview visible after returning", videoPreviewStatus="^正在播放$")
                captures.append(await expect_pixels(window, "returned", [FIRST]))
                streamer.stop_streaming()
                await window.observe("last picture marked stale", videoPreviewStatus="^画面已过期$")
                captures.append(await expect_pixels(window, "stale", [FIRST, ALTERNATE]))
                require(streamer.set_video_file(str(second)) and streamer.start_streaming(), "Restart recording")
                await window.observe("recovered in same receive session", videoPreviewStatus="^正在播放$")
                captures.append(await expect_pixels(window, "restored", [SECOND]))
                # Stop with frames still arriving to exercise old-session delivery and sink clearing.
                await window.action("stopButton")
                await window.observe("stopped with preview cleared", connectionValue="^已停止$",
                                     videoPreviewStatus="^已停止$")
                captures.append(await expect_pixels(window, "stopped", [EMPTY], tolerance=5))
                with exclusive_udp(port):
                    pass
            finally:
                streamer.stop()
            await window.action("startButton")
            await window.observe("new session waits for a new recording", connectionValue="^五类订阅就绪$",
                                 videoPreviewStatus="^等待模拟画面$")
            captures.append(await expect_pixels(window, "reopened", [EMPTY], tolerance=5))
    with exclusive_udp(port):
        pass
    json_file(evidence / "broker-packets.json", packets)
    topics = [tuple(pair) for row in packets if row["kind"] == "subscribe" for pair in row["topics"]]
    require(sorted(topics) == sorted([(topic, 1) for topic in TOPICS] * 2), "Expected two five-topic sessions")
    require(not any(row["kind"] == "client-publish" for row in packets), "Unexpected client business publish")
    return {"captures": captures, "clientBusinessPublishes": 0, "releasedUdpPort": port}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    options = parser.parse_args()
    directory = ROOT / "logs" / datetime.now().strftime("check-simulated-display-%Y%m%d-%H%M%S-%f")
    directory.mkdir(parents=True)
    print(f"Qt simulated display evidence: {directory}", flush=True)
    result = {"passed": False, "configuration": options.configuration, "entry": "scripts/run.ps1"}
    try:
        result.update(asyncio.run(verify(options.configuration, directory)))
        result["passed"] = True
        print("PASS: visible colour changes, stale picture, restored recording, stop and reopen.")
    except Exception:
        result["error"] = traceback.format_exc()
        print(result["error"], file=sys.stderr)
    json_file(directory / "summary.json", result)
    raise SystemExit(0 if result["passed"] else 1)
