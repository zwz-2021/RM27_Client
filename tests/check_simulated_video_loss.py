"""AT-056: observe missing or reordered fragments and recovery in the same Qt window."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime
import re
import socket
import sys
import time
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
from simulator.tools.video_loss_demo import dependent_frames, make_clip, send_clip, send_incomplete, send_loss_series


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
async def sending(transfer, *args, **kwargs):
    # Keep the sending socket open until its finite recording has finished, including on a failed assertion.
    task = asyncio.create_task(asyncio.to_thread(transfer, *args, **kwargs))
    try:
        yield task
    finally:
        await task


async def expect_drained(window, description, packets, assembled, decoded, last_frame, source_port, *,
                         timeouts=1, over_budget=0, failed=False, header=None):
    await window.action("diagnosticsTab")
    # A recovered segment can retain an FFmpeg diagnostic from before its first decodable frame.
    detail = r"\n解码错误 · [^\n]+" if failed else r"(?:\nFFmpeg 最近诊断 · [^\n]+)?$"
    view = await window.observe(
        description, udpCountersLabel=rf"^有效包 {packets} · 丢弃 0\b",
        udpLastFrameLabel=rf"帧号 {last_frame} · .*来源 127\.0\.0\.1:{source_port}\b",
        udpAssemblyLabel=rf"(?s)完整帧 {assembled} · 丢帧 {timeouts + over_budget}"
                         rf"（超时 {timeouts} · 冲突 0 · 超出预算 {over_budget}）"
                         r".*在途 0 帧 · 缓存 0 字节（0 片）",
        videoDecodeLabel=rf"等待输入 · 已解码 {decoded} 帧 · 1920×1080"
                         r" · 排队 0 帧 / 0 字节 · 输入丢弃 0 帧" + detail,
        **({"udpHeaderLabel": header} if header else {}))
    await window.action("overviewTab")
    return view


async def expect_waiting(window, description, capture_name, decoded):
    await window.observe(description, videoPreviewStatus="^画面已过期 · 等待可解码画面$")
    capture = await expect_pixels(window, capture_name, [[RED] * 4])
    await window.action("diagnosticsTab")
    view = await window.observe(description + " (decoder status)",
                                udpFrameRateLabel=r"^最近 1 秒完整组帧：[1-9]\d* 帧/秒$",
                                videoDecodeRateLabel="^最近 1 秒解码输出：0 帧/秒$",
                                videoPresentationRateLabel="^最近 1 秒控件交付：0 帧/秒$",
                                videoDecodeLabel=rf"等待可解码画面（参数集和关键帧） · 已解码 {decoded} 帧"
                                                 r" · 1920×1080 · 排队 \d+ 帧 / \d+ 字节 · 输入丢弃 0 帧"
                                                 r"(?:\nFFmpeg 最近诊断 · [^\n]+)?$")
    queue = re.search(r"排队 (\d+) 帧 / (\d+) 字节", view["videoDecodeLabel"])
    frames, size = map(int, queue.groups())
    require(frames <= 32 and size <= 4 * 1024 * 1024, f"Waiting queue exceeded bounds: {queue.group()}")
    await window.action("overviewTab")
    return capture, {"frames": frames, "bytes": size,
                     "completeFrameRate": view["udpFrameRateLabel"],
                     "decodeOutputRate": view["videoDecodeRateLabel"],
                     "presentationRate": view["videoPresentationRateLabel"]}


async def check_stale_red(window, set_health):
    await window.observe("last red picture marked stale", videoPreviewStatus="^画面已过期$")
    await set_health(322)
    await window.observe("new MQTT value during video loss", videoPreviewStatus="^画面已过期$",
                         healthValue="^322$", connectionValue="^六类订阅就绪$")
    return await expect_pixels(window, "stale-red", [[RED] * 4])


async def check_loss_series(window, sender, port, red_count, frame, red_packets, set_health, captures):
    # Independent of the sender's report. The local fixture omits slice 1 of a 1392-byte split.
    pieces = [frame[offset:offset + 1392] for offset in range(0, len(frame), 1392)]
    kept = pieces[:1] + pieces[2:]
    peak_bytes, peak_fragments = 8 * sum(map(len, kept)), 8 * len(kept)
    async with sending(send_loss_series, sender, port, red_count, frame) as transfer:
        await window.action("diagnosticsTab")
        await window.observe("eight simultaneous incomplete frames retained at the local budget",
                             udpAssemblyLabel=rf"(?s)完整帧 {red_count} · .*在途 8 帧 · 缓存 {peak_bytes} 字节（{peak_fragments} 片）",
                             udpLastFrameLabel=rf"帧号 {red_count - 1} ·")
        await window.observe("fragments still arriving after the last complete red frame ages out",
                             udpPacketRateLabel=r"^最近 1 秒有效 UDP 收包：[1-9]\d* 包/秒$",
                             udpFrameRateLabel="^最近 1 秒完整组帧：0 帧/秒$",
                             videoDecodeRateLabel="^最近 1 秒解码输出：0 帧/秒$",
                             videoPresentationRateLabel="^最近 1 秒控件交付：0 帧/秒$",
                             udpAssemblyLabel=rf"完整帧 {red_count}\b")
        await window.action("overviewTab")
        captures.append(await check_stale_red(window, set_health))
        require(not transfer.done(), "The loss series ended before the stale preview and new MQTT value were observed")

    manifest = transfer.result()
    json_file(window.evidence / "sent-omissions.json", manifest)
    damaged_count = 16 * 12
    require([row["frameId"] for row in manifest] == list(range(red_count, red_count + damaged_count))
            and all(row["omittedSlice"] == 1 and row["sentPackets"] == len(kept) for row in manifest),
            "Unexpected frames or fragment counts in the consecutive loss series")
    received = red_packets + damaged_count * len(kept)
    timeouts, over_budget = 16 * 8, 16 * 4
    await expect_drained(window, "all 16 groups accounted for and buffers empty before the blue recording",
                         received, red_count, red_count, red_count - 1, sender.getsockname()[1],
                         timeouts=timeouts, over_budget=over_budget)
    return {"damagedFrames": damaged_count, "omissionsFile": "sent-omissions.json",
            "observedPendingPeak": {"frames": 8, "bytes": peak_bytes, "fragments": peak_fragments},
            "assemblyTimeouts": timeouts, "assemblyOverBudget": over_budget}, received


async def check_missing_start(window, sender, port, red_count, blue, plain, red_packets, set_health, captures):
    source_port = sender.getsockname()[1]
    loss = send_incomplete(sender, port, red_count, blue[0])
    require(loss["sentPackets"] == loss["sliceCount"] - 1 and loss["sentPackets"] > 0,
            f"Fixture did not omit exactly one fragment: {loss}")
    received = red_packets + loss["sentPackets"]
    await expect_drained(window, "one timeout during silence; only red frames decoded",
                         received, red_count, red_count, red_count - 1, source_port)
    captures.append(await check_stale_red(window, set_health))
    async with sending(send_clip, sender, port, red_count + 1, plain) as prefix:
        capture, first_queue = await expect_waiting(window, "ordinary blue frames over stale red",
                                                    "waiting-red", red_count)
        captures.append(capture)
    received += prefix.result()
    assembled = red_count + len(plain)
    await expect_drained(window, "ordinary frames assembled but no new picture before drain",
                         received, assembled, red_count, assembled, source_port, failed=True)
    await window.observe("decoder failure remains visible over the stale red picture",
                         videoPreviewStatus="^画面已过期 · 解码失败，请查看运行信息$")
    captures.append(await expect_pixels(window, "undecodable-red", [[RED] * 4]))
    return {"damagedFrames": 1, "omission": loss, "assemblyTimeouts": 1, "assemblyOverBudget": 0,
            "ordinaryFramesBeforeSilence": len(plain), "ordinaryFramesImmediatelyBeforeKeyframe": len(plain),
            "waitingQueueSamples": {"first": first_queue}}, received


def packet_age_seconds(view):
    text = view.get("udpPacketAgeLabel", "")
    match = re.fullmatch(r"距最近有效 UDP 包 (\d+\.\d) 秒（本机接收）", text)
    require(match, f"Expected a local UDP packet age in the diagnostics tab: {text!r}")
    return float(match[1])


async def check_reordered_start(window, sender, port, red_count, red_packets, blue, set_health, captures):
    source_port = sender.getsockname()[1]
    red_view = await expect_drained(window, "red recording drained before the silent interval", red_packets,
                                    red_count, red_count, red_count - 1, source_port, timeouts=0)
    red_age = packet_age_seconds(red_view)
    captures.append(await check_stale_red(window, set_health))
    await window.action("diagnosticsTab")
    await asyncio.sleep(1.5)
    silent_view = await window.observe("UDP stays silent while new MQTT health reaches the same window",
                                       udpPacketRateLabel="^最近 1 秒有效 UDP 收包：0 包/秒$",
                                       udpFrameRateLabel="^最近 1 秒完整组帧：0 帧/秒$",
                                       videoDecodeRateLabel="^最近 1 秒解码输出：0 帧/秒$",
                                       videoPresentationRateLabel="^最近 1 秒控件交付：0 帧/秒$",
                                       udpCountersLabel=rf"^有效包 {red_packets} · 丢弃 0\b")
    silent_age = packet_age_seconds(silent_view)
    require(silent_age >= red_age + 1.0, f"Packet age did not advance during silence: {red_age} -> {silent_age}")
    await window.action("captureDiagnostics")
    await window.action("overviewTab")

    # Stop after one recording: a later loop's IDR must not rescue a broken first frame.
    dependent_frames(blue)
    blue_packets = sum((len(frame) + 1391) // 1392 for frame in blue)
    resumed_at = time.monotonic()
    async with sending(send_clip, sender, port, red_count, blue, reverse_first=True) as restored:
        await window.observe("reordered recording playing before a second keyframe is sent",
                             videoPreviewStatus="^正在播放$")
        captures.append(await expect_pixels(window, "first-reordered-blue", [[BLUE] * 4]))
    require(restored.result() == blue_packets, "Unexpected packet count in the reordered recording")
    assembled = red_count + len(blue)
    blue_view = await expect_drained(window, "all pictures from the first blue recording decoded before another IDR",
                                     red_packets + blue_packets, assembled, assembled, assembled - 1,
                                     source_port, timeouts=0)
    blue_age = packet_age_seconds(blue_view)
    # Reading the UI can itself take time. The last blue packet cannot predate the first one.
    require(blue_age <= time.monotonic() - resumed_at + 0.3, f"Old packet age survived blue recovery: {blue_age}")
    return {"damagedFrames": 0, "assemblyTimeouts": 0, "assemblyOverBudget": 0,
            "localPacketAgeSeconds": {"afterRed": red_age, "duringSilence": silent_age, "afterBlue": blue_age},
            "packetRateDuringSilence": silent_view["udpPacketRateLabel"],
            "completeFrameRateDuringSilence": silent_view["udpFrameRateLabel"],
            "decodeOutputRateDuringSilence": silent_view["videoDecodeRateLabel"],
            "presentationRateDuringSilence": silent_view["videoPresentationRateLabel"],
            "firstReorderedFrameId": red_count, "blueFramesBeforeNextKeyframe": len(blue)}, red_packets + blue_packets


async def check_single_output_frame(window, sender, port, frame, frame_id, packets, frames, decoded, *,
                                    timeouts, over_budget, reverse_first):
    # Recheck the same complete AU on its own, so its exact delivery count and last
    # received fragment stay visible however long UI Automation takes to read them.
    count = (len(frame) + 1391) // 1392
    require(count >= 2, "Single-frame probe requires at least two fragments")
    await window.action("diagnosticsTab")
    await window.observe("all four rate windows empty before the isolated keyframe",
                         udpPacketRateLabel="^最近 1 秒有效 UDP 收包：0 包/秒$",
                         udpFrameRateLabel="^最近 1 秒完整组帧：0 帧/秒$",
                         videoPresentationRateLabel="^最近 1 秒控件交付：0 帧/秒$",
                         videoDecodeRateLabel="^最近 1 秒解码输出：0 帧/秒$")
    require(send_clip(sender, port, frame_id, [frame], reverse_first=reverse_first) == count, "Wrong probe packet count")
    source_port = sender.getsockname()[1]
    header = (rf"来源 127\.0\.0\.1:{source_port} · 整包 1400 字节 · 帧号 {frame_id} · "
              rf"分片号 0 · 整帧 {len(frame)} 字节") if reverse_first else None
    # This finite single-AU segment produces its picture only when idle drain closes
    # FFmpeg's input. Its output is new even though input-rate windows have expired.
    tail = await window.observe("one delayed picture counts after both UDP input windows expire",
                                udpPacketRateLabel="^最近 1 秒有效 UDP 收包：0 包/秒$",
                                udpFrameRateLabel="^最近 1 秒完整组帧：0 帧/秒$",
                                videoDecodeRateLabel="^最近 1 秒解码输出：1 帧/秒$",
                                videoPresentationRateLabel="^最近 1 秒控件交付：1 帧/秒$",
                                videoDecodeLabel=rf"已解码 {decoded + 1} 帧\b")
    await window.action("captureDecodeRate")
    quiet = await window.observe("one second without further decoded output expires the delayed picture",
                                 videoDecodeRateLabel="^最近 1 秒解码输出：0 帧/秒$",
                                 videoPresentationRateLabel="^最近 1 秒控件交付：0 帧/秒$",
                                 videoDecodeLabel=rf"已解码 {decoded + 1} 帧\b")
    await expect_drained(window, "isolated first AU adds exactly one complete and decoded frame",
                         packets + count, frames + 1, decoded + 1, frame_id, source_port,
                         timeouts=timeouts, over_budget=over_budget, header=header)
    tab_switches = []
    for index in range(3):
        # Main.qml retains the VideoOutput while its StackLayout page is hidden.
        # With no new output, switching pages must not turn the retained frame into
        # a new presentation. Sample across several 100 ms metric refreshes, and
        # fail on any nonzero read instead of waiting for a spurious count to expire.
        await window.action("overviewTab")
        await window.action("diagnosticsTab")
        started = time.monotonic()
        samples = []
        while True:
            view = await window.action("snapshot")
            elapsed = time.monotonic() - started
            require(view.get("videoPresentationRateLabel") == "最近 1 秒控件交付：0 帧/秒",
                    f"Tab switch {index + 1} counted an old picture at {elapsed:.3f}s: {view}")
            require(view.get("videoDecodeRateLabel") == "最近 1 秒解码输出：0 帧/秒",
                    f"Unexpected decoder output after tab switch {index + 1} at {elapsed:.3f}s: {view}")
            samples.append({"afterMilliseconds": round(elapsed * 1000, 1), **view})
            if elapsed >= 0.3:
                break
            await asyncio.sleep(0.05)
        tab_switches.append({"switch": index + 1, "samples": samples})
    await window.action("overviewTab")
    return {"frameId": frame_id, "frameBytes": len(frame), "packets": count,
            "lastReceivedSlice": 0 if reverse_first else count - 1,
            "sessionPacketsAfterProbe": packets + count, "sessionFramesAfterProbe": frames + 1,
            "sessionDecodedAfterProbe": decoded + 1,
            "decodeOutputRateDuringDrain": tail["videoDecodeRateLabel"],
            "decodeOutputRateAfterSilence": quiet["videoDecodeRateLabel"],
            "presentationRateDuringDrain": tail["videoPresentationRateLabel"],
            "presentationRateAfterSilence": quiet["videoPresentationRateLabel"],
            "silentTabSwitches": tab_switches}


async def verify(configuration, evidence, scenario):
    red, blue = make_clip("red"), make_clip("blue")
    loops = 4 if scenario == "missing-start" else 5
    red_count, blue_count = len(red) * loops, len(blue) * loops
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
            await window.observe("first live MQTT value while waiting for video", connectionValue="^六类订阅就绪$",
                                 videoPreviewStatus="^等待模拟画面$", healthValue="^321$")
            await window.action("diagnosticsTab")
            await window.observe("no picture delivered before the first video input",
                                 videoDecodeRateLabel="^最近 1 秒解码输出：0 帧/秒$",
                                 videoPresentationRateLabel="^最近 1 秒控件交付：0 帧/秒$")
            await window.action("overviewTab")
            with exclusive_udp(0) as sender:
                source_port = sender.getsockname()[1]

                async with sending(send_clip, sender, port, 0, red, loops) as initial:
                    await window.observe("red clip is playing before loss", videoPreviewStatus="^正在播放$",
                                         healthValue="^321$")
                    captures.append(await expect_pixels(window, "playing-red", [[RED] * 4]))
                red_packets = initial.result()
                plain = []
                assembled_before_restart = red_count
                recovery = blue * loops
                if scenario == "reverse-first-frame":
                    expected_red_packets = loops * sum((len(frame) + 1391) // 1392 for frame in red)
                    require(red_packets == expected_red_packets, "Unexpected number of packets in the red recording")
                    fault, pre_recovery_packets = await check_reordered_start(
                        window, sender, port, red_count, red_packets, blue, set_health, captures)
                    assembled_before_restart += len(blue)
                    recovery = blue * (loops - 1)
                elif scenario == "consecutive-loss":
                    fault, pre_recovery_packets = await check_loss_series(
                        window, sender, port, red_count, blue[0], red_packets, set_health, captures)
                else:
                    plain = dependent_frames(blue) * loops
                    fault, pre_recovery_packets = await check_missing_start(
                        window, sender, port, red_count, blue, plain, red_packets, set_health, captures)
                    assembled_before_restart += len(plain)
                    recovery = plain + recovery  # No idle drain between the dependent prefix and the keyframe.
                next_id = assembled_before_restart + fault["damagedFrames"]
                async with sending(send_clip, sender, port, next_id, recovery) as restored:
                    if plain:
                        capture, retry_queue = await expect_waiting(window, "retry replaces old failure with waiting",
                                                                    "waiting-again-red", red_count)
                        captures.append(capture)
                        fault["waitingQueueSamples"]["retry"] = retry_queue
                    await window.observe("new clip playing in the same session", videoPreviewStatus="^正在播放$")
                    await window.action("diagnosticsTab")
                    recovered_rate = await window.observe("complete blue recording resumes real decoder output",
                                                          udpFrameRateLabel=r"^最近 1 秒完整组帧：[1-9]\d* 帧/秒$",
                                                          videoPresentationRateLabel=r"^最近 1 秒控件交付：[1-9]\d* 帧/秒$",
                                                          videoDecodeRateLabel=r"^最近 1 秒解码输出：[1-9]\d* 帧/秒$")
                    await window.action("overviewTab")
                    await set_health(323)
                    await window.observe("third MQTT value during recovery", videoPreviewStatus="^正在播放$",
                                         healthValue="^323$", connectionValue="^六类订阅就绪$")
                    captures.append(await expect_pixels(window, "recovered-blue", [[BLUE] * 4]))
                total_packets = pre_recovery_packets + restored.result()
                assembled = assembled_before_restart + len(recovery)
                decoded = red_count + blue_count
                await expect_drained(window, "all complete blue frames decoded; no extra losses or backlog",
                                     total_packets, assembled, decoded, next_id + len(recovery) - 1, source_port,
                                     timeouts=fault["assemblyTimeouts"], over_budget=fault["assemblyOverBudget"])
                fault["singleAccessUnitProbe"] = await check_single_output_frame(
                    window, sender, port, blue[0], next_id + len(recovery), total_packets, assembled, decoded,
                    timeouts=fault["assemblyTimeouts"], over_budget=fault["assemblyOverBudget"],
                    reverse_first=scenario == "reverse-first-frame")
            await window.action("stopButton")
            await window.observe("receive session stopped", connectionValue="^已停止$", videoPreviewStatus="^已停止$")
            captures.append(await expect_pixels(window, "stopped", [EMPTY], tolerance=5))
            await window.action("diagnosticsTab")
            await window.observe("stopped decoder has no active output-rate window",
                                 videoPresentationRateLabel="^最近 1 秒控件交付：—$",
                                 videoDecodeRateLabel="^最近 1 秒解码输出：—$")

    client_packets = [row for row in packets if row["clientId"] == "3"]
    json_file(evidence / "broker-client-packets.json", client_packets)
    topics = [tuple(pair) for row in client_packets if row["kind"] == "subscribe" for pair in row["topics"]]
    require(sum(row["kind"] == "connect" for row in client_packets) == 1
            and sorted(topics) == sorted((topic, 1) for topic in TOPICS), "Expected one six-topic Qt connection")
    require(not any(row["kind"] == "client-publish" for row in client_packets), "Unexpected client business publish")
    wire_health = {RobotDynamicStatus.FromString(bytes.fromhex(row["hex"])).current_health
                   for row in client_packets if row["kind"] == "broker-publish" and row["topic"] == "RobotDynamicStatus"}
    require({321, 322, 323} <= wire_health, f"Missing MQTT health changes on Qt connection: {wire_health}")
    with exclusive_udp(port):
        for tcp_port in (mqtt_port, web_port):
            with socket.socket() as probe:
                probe.settimeout(1)
                require(probe.connect_ex(("127.0.0.1", tcp_port)) != 0, f"Listener still on port {tcp_port}")
    return {"redFrames": red_count, **fault, "recoveredBlueFrames": blue_count,
            "receivedPackets": total_packets, "assembledFrames": assembled,
            "decodedFrames": decoded,
            "decodeOutputRateDuringRecovery": recovered_rate["videoDecodeRateLabel"],
            "presentationRateDuringRecovery": recovered_rate["videoPresentationRateLabel"],
            "pendingFragments": 0, "bufferedBytes": 0, "decoderQueuedBytes": 0, "captures": captures,
            "mqttHealthInWindow": [321, 322, 323], "clientBusinessPublishes": 0,
            "releasedPorts": {"udp": port, "mqtt": mqtt_port, "web": web_port}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--consecutive-loss", dest="scenario", action="store_const", const="consecutive-loss",
                      help="Exercise 16 groups of incomplete loopback frames")
    mode.add_argument("--reverse-first-frame", dest="scenario", action="store_const", const="reverse-first-frame",
                      help="Reverse all fragments of the first blue frame after the red recording expires")
    parser.set_defaults(scenario="missing-start")
    options = parser.parse_args()
    directory = ROOT / "logs" / datetime.now().strftime("check-simulated-loss-%Y%m%d-%H%M%S-%f")
    directory.mkdir(parents=True)
    print(f"Qt fragment-loss evidence: {directory}", flush=True)
    result = {"passed": False, "configuration": options.configuration, "entry": "scripts/run.ps1",
              "scenario": options.scenario}
    try:
        result.update(asyncio.run(verify(options.configuration, directory, options.scenario)))
        result["passed"] = True
        print("PASS: stale red pixels, expected fragment diagnostics, live MQTT and blue recovery.")
    except Exception:
        result["error"] = traceback.format_exc()
        print(result["error"], file=sys.stderr)
    json_file(directory / "summary.json", result)
    raise SystemExit(0 if result["passed"] else 1)
