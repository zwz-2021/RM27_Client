"""AT-056: observe fragment loss, undecodable input and recovery in the same Qt window."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime
import re
import socket
import sys
import traceback
import uuid

from amqtt.broker import Broker
import requests
import socketio
import uvicorn

from check_hevc_decode import json_file
from check_mqtt_receive import ROOT, TOPICS, require
from check_simulated_video_display import BLUE, EMPTY, RED, expect_pixels
from check_udp_receive import exclusive_udp, open_window
from simulator.protocol.rm27_base_pb2 import RobotDynamicStatus
from simulator.server.app import create_app
from simulator.server.main import build_parser
from simulator.tools.smoke_test import check_stopped
from simulator.tools.video_loss_demo import dependent_frames, make_clip, send_clip, send_incomplete


@asynccontextmanager
async def simulator_console(mqtt_port):
    with socket.socket() as listener, requests.Session() as http:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        args = build_parser().parse_args([
            "--web-host", "127.0.0.1", "--web-port", str(port),
            "--mqtt-host", "127.0.0.1", "--mqtt-port", str(mqtt_port), "--current-robot-id", "3"])
        application = create_app(args)
        server = uvicorn.Server(uvicorn.Config(application, log_level="error", access_log=False))
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        http.trust_env = False
        console = socketio.Client(reconnection=False, request_timeout=3, http_session=http)
        try:
            async with asyncio.timeout(12):
                while not server.started:
                    if serving.done():
                        await serving
                        raise RuntimeError("Simulator exited during startup")
                    await asyncio.sleep(0.05)
            await asyncio.to_thread(console.connect, url, transports=["websocket"], wait_timeout=5)
            state = await asyncio.to_thread(http.get, url + "/api/state", timeout=3)
            state.raise_for_status()
            index = state.json()["robotIds"].index(3)

            async def set_health(value):
                reply = await asyncio.to_thread(console.call, "referee_command", {
                    "command": "set_basic_robot_values", "robot_index": index, "health": value}, timeout=5)
                require(isinstance(reply, dict) and reply.get("ok"), f"Console rejected HP {value}: {reply}")

            yield port, set_health
        finally:
            try:
                if console.connected:
                    await asyncio.to_thread(console.disconnect)
            finally:
                server.should_exit = True
                await asyncio.wait_for(serving, 15)
        runtime = application.fastapi_app.state.simulator
        for component in (runtime.state_manager, runtime.mqtt_publisher,
                          runtime.video_streamer, runtime.industrial_camera_streamer):
            check_stopped(component)
        require(runtime.video_streamer.sock.fileno() == -1, "Simulator UDP sender still open")


@asynccontextmanager
async def sending(transfer, *args):
    # Keep the sending socket open until its finite recording has finished, including on a failed assertion.
    task = asyncio.create_task(asyncio.to_thread(transfer, *args))
    try:
        yield task
    finally:
        await task


async def expect_drained(window, description, packets, assembled, decoded, last_frame, source_port, *, failed=False):
    await window.action("diagnosticsTab")
    # A recovered segment can retain an FFmpeg diagnostic from before its first decodable frame.
    detail = r"\n解码错误 · [^\n]+" if failed else r"(?:\nFFmpeg 最近诊断 · [^\n]+)?$"
    await window.observe(description, udpCountersLabel=rf"^有效包 {packets} · 丢弃 0\b",
                         udpLastFrameLabel=rf"帧号 {last_frame} · .*来源 127\.0\.0\.1:{source_port}\b",
                         udpAssemblyLabel=rf"(?s)完整帧 {assembled} · 丢帧 1（超时 1 · 冲突 0 · 超出预算 0）"
                                          r".*在途 0 帧 · 缓存 0 字节（0 片）",
                         videoDecodeLabel=rf"等待输入 · 已解码 {decoded} 帧 · 1920×1080"
                                          r" · 排队 0 帧 / 0 字节 · 输入丢弃 0 帧" + detail)
    await window.action("overviewTab")


async def expect_waiting(window, description, capture_name, decoded):
    await window.observe(description, videoPreviewStatus="^画面已过期 · 等待可解码画面$")
    capture = await expect_pixels(window, capture_name, [[RED] * 4])
    await window.action("diagnosticsTab")
    view = await window.observe(description + " (decoder status)",
                                videoDecodeLabel=rf"等待可解码画面（参数集和关键帧） · 已解码 {decoded} 帧"
                                                 r" · 1920×1080 · 排队 \d+ 帧 / \d+ 字节 · 输入丢弃 0 帧"
                                                 r"(?:\nFFmpeg 最近诊断 · [^\n]+)?$")
    queue = re.search(r"排队 (\d+) 帧 / (\d+) 字节", view["videoDecodeLabel"])
    frames, size = map(int, queue.groups())
    require(frames <= 32 and size <= 4 * 1024 * 1024, f"Waiting queue exceeded bounds: {queue.group()}")
    await window.action("overviewTab")
    return capture, {"frames": frames, "bytes": size}


async def verify(configuration, evidence):
    red, blue = make_clip("red"), make_clip("blue")
    plain = dependent_frames(blue)
    loops = 4
    red_count, blue_count, plain_count = len(red) * loops, len(blue) * loops, len(plain) * loops
    with exclusive_udp(0) as reservation:
        port = reservation.getsockname()[1]
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
        "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
                    "check_mqtt_receive.RecoveryPacketLog": {}},
    })
    title = "RM27 simulated fragment loss " + uuid.uuid4().hex
    captures = []
    async with AsyncExitStack() as services:
        await broker.start()
        services.push_async_callback(broker.shutdown)
        mqtt_port = broker._servers["default"].instance.sockets[0].getsockname()[1]
        packets = broker.plugins_manager.get_plugin("RecoveryPacketLog").packets
        web_port, set_health = await services.enter_async_context(simulator_console(mqtt_port))
        config = evidence / "infantry.json"
        json_file(config, {"mode": "simulation", "seat": "infantry",
                           "window": {"title": title, "width": 960, "height": 760},
                           "mqtt": {"host": "127.0.0.1", "port": mqtt_port, "robotId": 3},
                           "video": {"bindAddress": "127.0.0.1", "port": port}})
        async with open_window(config, title, configuration) as window:
            await set_health(321)
            await window.observe("first live MQTT value while waiting for video", connectionValue="^五类订阅就绪$",
                                 videoPreviewStatus="^等待模拟画面$", healthValue="^321$")
            with exclusive_udp(0) as sender:
                source_port = sender.getsockname()[1]

                def red_then_loss():
                    complete = send_clip(sender, port, 0, red, loops)
                    loss = send_incomplete(sender, port, red_count, blue[0])
                    return complete, loss

                async with sending(red_then_loss) as initial:
                    await window.observe("red clip is playing before loss", videoPreviewStatus="^正在播放$",
                                         healthValue="^321$")
                    captures.append(await expect_pixels(window, "playing-red", [[RED] * 4]))
                red_packets, loss = initial.result()
                require(loss["sentPackets"] == loss["sliceCount"] - 1 and loss["sentPackets"] > 0,
                        f"Fixture did not omit exactly one fragment: {loss}")
                pre_recovery_packets = red_packets + loss["sentPackets"]
                await expect_drained(window, "one timeout during silence; only red frames decoded",
                                     pre_recovery_packets, red_count, red_count, red_count - 1, source_port)
                await window.observe("last red picture marked stale", videoPreviewStatus="^画面已过期$")
                await set_health(322)
                await window.observe("new MQTT value during video loss", videoPreviewStatus="^画面已过期$",
                                     healthValue="^322$", connectionValue="^五类订阅就绪$")
                captures.append(await expect_pixels(window, "stale-red", [[RED] * 4]))

                async with sending(send_clip, sender, port, red_count + 1, plain, loops) as prefix:
                    capture, first_queue = await expect_waiting(window, "ordinary blue frames over stale red",
                                                                "waiting-red", red_count)
                    captures.append(capture)
                pre_recovery_packets += prefix.result()
                assembled_before_restart = red_count + plain_count
                await expect_drained(window, "ordinary frames assembled but no new picture before drain",
                                     pre_recovery_packets, assembled_before_restart, red_count,
                                     assembled_before_restart, source_port, failed=True)
                await window.observe("decoder failure remains visible over the stale red picture",
                                     videoPreviewStatus="^画面已过期 · 解码失败，请查看运行信息$")
                captures.append(await expect_pixels(window, "undecodable-red", [[RED] * 4]))

                # A second prefix and the complete clip share one pacing clock. There is no idle
                # drain between ordinary frames and the independent blue frame that follows them.
                recovery = plain * loops + blue * loops
                async with sending(send_clip, sender, port, assembled_before_restart + 1, recovery) as restored:
                    capture, retry_queue = await expect_waiting(window, "retry replaces old failure with waiting",
                                                                "waiting-again-red", red_count)
                    captures.append(capture)
                    await window.observe("new clip playing in the same session", videoPreviewStatus="^正在播放$")
                    await set_health(323)
                    await window.observe("third MQTT value during recovery", videoPreviewStatus="^正在播放$",
                                         healthValue="^323$", connectionValue="^五类订阅就绪$")
                    captures.append(await expect_pixels(window, "recovered-blue", [[BLUE] * 4]))
                total_packets = pre_recovery_packets + restored.result()
                assembled = assembled_before_restart + len(recovery)
                decoded = red_count + blue_count
                await expect_drained(window, "all complete blue frames decoded; no second timeout or backlog",
                                     total_packets, assembled, decoded, assembled, source_port)
            await window.action("stopButton")
            await window.observe("receive session stopped", connectionValue="^已停止$", videoPreviewStatus="^已停止$")
            captures.append(await expect_pixels(window, "stopped", [EMPTY], tolerance=5))

    client_packets = [row for row in packets if row["clientId"] == "3"]
    json_file(evidence / "broker-client-packets.json", client_packets)
    topics = [tuple(pair) for row in client_packets if row["kind"] == "subscribe" for pair in row["topics"]]
    require(sum(row["kind"] == "connect" for row in client_packets) == 1
            and sorted(topics) == sorted((topic, 1) for topic in TOPICS), "Expected one five-topic Qt connection")
    require(not any(row["kind"] == "client-publish" for row in client_packets), "Unexpected client business publish")
    wire_health = {RobotDynamicStatus.FromString(bytes.fromhex(row["hex"])).current_health
                   for row in client_packets if row["kind"] == "broker-publish" and row["topic"] == "RobotDynamicStatus"}
    require({321, 322, 323} <= wire_health, f"Missing MQTT health changes on Qt connection: {wire_health}")
    with exclusive_udp(port):
        for tcp_port in (mqtt_port, web_port):
            with socket.socket() as probe:
                probe.settimeout(1)
                require(probe.connect_ex(("127.0.0.1", tcp_port)) != 0, f"Listener still on port {tcp_port}")
    return {"redFrames": red_count, "omission": loss, "ordinaryFramesBeforeSilence": plain_count,
            "ordinaryFramesImmediatelyBeforeKeyframe": plain_count, "recoveredBlueFrames": blue_count,
            "waitingQueueSamples": {"first": first_queue, "retry": retry_queue},
            "receivedPackets": total_packets, "assemblyTimeouts": 1, "assembledFrames": assembled,
            "decodedFrames": decoded,
            "pendingFragments": 0, "bufferedBytes": 0, "decoderQueuedBytes": 0, "captures": captures,
            "mqttHealthInWindow": [321, 322, 323], "clientBusinessPublishes": 0,
            "releasedPorts": {"udp": port, "mqtt": mqtt_port, "web": web_port}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    options = parser.parse_args()
    directory = ROOT / "logs" / datetime.now().strftime("check-simulated-loss-%Y%m%d-%H%M%S-%f")
    directory.mkdir(parents=True)
    print(f"Qt fragment-loss evidence: {directory}", flush=True)
    result = {"passed": False, "configuration": options.configuration, "entry": "scripts/run.ps1"}
    try:
        result.update(asyncio.run(verify(options.configuration, directory)))
        result["passed"] = True
        print("PASS: stale red pixels during undecodable input, visible diagnostics, live MQTT and blue recovery.")
    except Exception:
        result["error"] = traceback.format_exc()
        print(result["error"], file=sys.stderr)
    json_file(directory / "summary.json", result)
    raise SystemExit(0 if result["passed"] else 1)
