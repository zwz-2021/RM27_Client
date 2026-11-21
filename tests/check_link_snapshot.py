"""AT-067: save bounded status snapshots from the normal Qt receiver window."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack, contextmanager
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import socket
import sys
import time
import traceback
import uuid

from amqtt.broker import Broker
from check_hevc_decode import json_file
from check_mqtt_receive import ROOT, TOPICS, require
from check_simulated_video_display import BLUE, RED, expect_pixels
from check_simulated_video_loss import sending, simulator_console
from check_udp_receive import exclusive_udp, open_window
from simulator.protocol.rm27_base_pb2 import RobotDynamicStatus
from simulator.tools.video_loss_demo import make_clip, send_clip


RATE_FIELDS = (("udp", "valid_packets_last_second"),
               ("assembly", "completed_frames_last_second"),
               ("decode", "decoded_frames_last_second"),
               ("decode", "presented_frames_last_second"))


def rates(snapshot):
    return [snapshot[group][field] for group, field in RATE_FIELDS]


def assert_snapshot(snapshot, raw, title):
    require(len(raw) <= 32 * 1024, "Snapshot exceeded its 32 KiB limit")
    require(set(snapshot) == {"schema_version", "sampled_at_local", "sampled_at_utc", "semantics",
                              "session", "mqtt", "udp", "assembly", "decode"}, "Unexpected snapshot schema")
    require(snapshot["schema_version"] == 1, "Missing schema version")
    local = datetime.fromisoformat(snapshot["sampled_at_local"])
    utc = datetime.fromisoformat(snapshot["sampled_at_utc"].replace("Z", "+00:00"))
    require(local.utcoffset() is not None and utc.utcoffset().total_seconds() == 0
            and local == utc, "Sampling timestamps must represent the same instant with explicit zones")
    require(snapshot["semantics"]["rate_window_ms"] == 1000, "Missing local rate-window units")
    require(set(snapshot["mqtt"]["topics"]) == TOPICS, "Snapshot should contain five exact MQTT topics")
    for forbidden in ("127.0.0.1", str(ROOT), str(ROOT).replace("\\", "/"), title, "infantry.json"):
        require(forbidden not in raw.decode("utf-8"), f"Snapshot exposed excluded configuration: {forbidden}")
    for group, field in RATE_FIELDS:
        value = snapshot[group][field]
        require(value is None or (isinstance(value, str) and value.isdecimal()),
                f"{group}.{field} must preserve an integer count or explicit null")


async def save_snapshot(window, evidence, title, name):
    target = evidence / "link-snapshot.json"
    before = target.read_bytes() if target.exists() else None
    await window.action("saveDiagnosticSnapshotButton")
    deadline = time.monotonic() + 12
    while True:
        raw = target.read_bytes() if target.exists() else None
        if raw is not None and raw != before:
            break
        require(time.monotonic() < deadline, f"{name}: no new committed snapshot")
        await asyncio.sleep(0.05)
    # Waiting for both the changed file and success feedback avoids accepting the
    # previous operation's label while the asynchronous writer is still running.
    feedback = await window.observe(name + " save feedback", snapshotSaveFeedback=r"^已保存诊断快照：")
    require(feedback["snapshotSaveEnabled"], "Save button did not become available after completion")
    require(str(target) in feedback["snapshotSaveFeedback"].replace("/", "\\"),
            "Successful feedback did not identify the saved file")
    snapshot = json.loads(raw)
    assert_snapshot(snapshot, raw, title)
    (evidence / (name + ".json")).write_bytes(raw)
    return snapshot


@contextmanager
def prevent_replacement(path):
    """Deny delete/rename of this test's file while allowing the test to read it."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        if not kernel.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


def assert_empty(snapshot, *, stopped=False):
    expected_rate = None if stopped else "0"
    require(rates(snapshot) == [expected_rate] * 4, f"Wrong empty-session rates: {rates(snapshot)}")
    require(snapshot["udp"]["valid_packets_total"] == "0"
            and snapshot["udp"]["last_valid_packet_age_ms"] is None
            and snapshot["udp"]["last_header"] is None
            and snapshot["assembly"]["completed_frames_total"] == "0"
            and snapshot["assembly"]["last_frame"] is None
            and snapshot["decode"]["decoded_frames_total"] == "0"
            and not snapshot["decode"]["has_frame"], "Old video data leaked into a cleared session")


async def verify(configuration, evidence):
    red, blue = make_clip("red"), make_clip("blue")
    loops = 8
    frames_per_clip = len(red) * loops
    captures, snapshots = [], {}
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
        "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
                    "check_mqtt_receive.RecoveryPacketLog": {}},
    })
    title = "RM27 diagnostic snapshot " + uuid.uuid4().hex
    async with AsyncExitStack() as services:
        await broker.start()
        services.push_async_callback(broker.shutdown)
        mqtt_port = broker._servers["default"].instance.sockets[0].getsockname()[1]
        packets = broker.plugins_manager.get_plugin("RecoveryPacketLog").packets
        blocker = services.enter_context(exclusive_udp(0))
        port = blocker.getsockname()[1]
        config = evidence / "infantry.json"
        json_file(config, {"mode": "simulation", "seat": "infantry",
                           "window": {"title": title, "width": 960, "height": 760},
                           "mqtt": {"host": "127.0.0.1", "port": mqtt_port, "robotId": 3},
                           "video": {"bindAddress": "127.0.0.1", "port": port}})
        async with open_window(config, title, configuration) as window:
            await window.observe("bound-port failure with healthy MQTT connection",
                                 connectionValue="^五类订阅就绪$", videoPreviewStatus="视频端口绑定失败")
            await window.action("diagnosticsTab")
            failed = await save_snapshot(window, evidence, title, "bind-failed")
            require(failed["udp"]["state"] == "bind_failed" and failed["udp"]["error_present"]
                    and failed["mqtt"]["state"] == "connected" and rates(failed) == [None] * 4,
                    f"Bind failure exported misleading rates: {failed}")
            snapshots["bindFailed"] = "bind-failed.json"

            await window.action("overviewTab")
            await window.action("stopButton")
            await window.observe("stopped to release test conflict", connectionValue="^已停止$")
            blocker.close()
            await window.action("startButton")
            await window.observe("waiting with no simulator data", connectionValue="^五类订阅就绪$",
                                 videoPreviewStatus="^等待模拟画面$")
            await window.action("diagnosticsTab")
            empty = await save_snapshot(window, evidence, title, "no-data")
            assert_empty(empty)
            require(empty["decode"]["state"] == "waiting" and empty["udp"]["state"] == "bound"
                    and all(not item["received"] and item["stale"] is None
                            for item in empty["mqtt"]["topics"].values()), "No-data snapshot invented samples")
            snapshots["noData"] = "no-data.json"

            web_port, set_health = await services.enter_async_context(simulator_console(mqtt_port))
            await set_health(321)
            await window.action("overviewTab")
            await window.observe("live five-topic MQTT path", connectionValue="^五类订阅就绪$", healthValue="^321$")
            # Three topics publish at 1 Hz; allow their first period after readiness.
            await asyncio.sleep(1.1)
            await window.action("diagnosticsTab")
            mqtt = await save_snapshot(window, evidence, title, "mqtt-no-video")
            require(all(item == {"received": True, "stale": False} for item in mqtt["mqtt"]["topics"].values()),
                    f"Simulator topics not fresh in diagnostic snapshot: {mqtt['mqtt']}")
            assert_empty(mqtt)
            snapshots["mqttNoVideo"] = "mqtt-no-video.json"

            total_packets = 0
            with exclusive_udp(0) as sender:
                for index, (name, clip, color) in enumerate((("red", red, RED), ("blue", blue, BLUE))):
                    await window.action("overviewTab")
                    async with sending(send_clip, sender, port, index * frames_per_clip, clip, loops) as transfer:
                        await window.observe(name + " playing", videoPreviewStatus="^正在播放$")
                        captures.append(await expect_pixels(window, name + "-playing", [[color] * 4]))
                        await window.action("diagnosticsTab")
                        await window.observe(name + " four active rates",
                                             udpPacketRateLabel=r"^最近 1 秒有效 UDP 收包：[1-9]\d* 包/秒$",
                                             udpFrameRateLabel=r"^最近 1 秒完整组帧：[1-9]\d* 帧/秒$",
                                             videoDecodeRateLabel=r"^最近 1 秒解码输出：[1-9]\d* 帧/秒$",
                                             videoPresentationRateLabel=r"^最近 1 秒控件交付：[1-9]\d* 帧/秒$")
                        playing = await save_snapshot(window, evidence, title, name + "-playing")
                        require(not transfer.done(), "Recording ended before active snapshot was saved")
                        require(playing["decode"]["state"] == "playing"
                                and all(value is not None and int(value) > 0 for value in rates(playing))
                                and playing["decode"]["width"] == 1920 and playing["decode"]["height"] == 1080
                                and not playing["decode"]["frame_stale"], f"Wrong playing snapshot: {playing}")
                        snapshots[name + "Playing"] = name + "-playing.json"
                    total_packets += transfer.result()
                    expected_frames = (index + 1) * frames_per_clip
                    await window.observe(name + " drained and all rates expired",
                                         udpCountersLabel=rf"^有效包 {total_packets} · 丢弃 0\b",
                                         udpAssemblyLabel=rf"完整帧 {expected_frames} · 丢帧 0\b",
                                         videoDecodeLabel=rf"等待输入 · 已解码 {expected_frames} 帧\b.*排队 0 帧 / 0 字节",
                                         udpPacketRateLabel="^最近 1 秒有效 UDP 收包：0 包/秒$",
                                         udpFrameRateLabel="^最近 1 秒完整组帧：0 帧/秒$",
                                         videoDecodeRateLabel="^最近 1 秒解码输出：0 帧/秒$",
                                         videoPresentationRateLabel="^最近 1 秒控件交付：0 帧/秒$")
                    await window.action("overviewTab")
                    await set_health(322 + index)
                    await window.observe(name + " stale while MQTT continues", videoPreviewStatus="^画面已过期$",
                                         healthValue=f"^{322 + index}$", connectionValue="^五类订阅就绪$")
                    await window.action("diagnosticsTab")
                    quiet = await save_snapshot(window, evidence, title, name + "-quiet")
                    require(quiet["decode"]["state"] == "stale" and quiet["decode"]["frame_stale"]
                            and rates(quiet) == ["0"] * 4
                            and int(quiet["udp"]["valid_packets_total"]) == total_packets
                            and int(quiet["assembly"]["completed_frames_total"]) == expected_frames
                            and int(quiet["decode"]["decoded_frames_total"]) == expected_frames
                            and quiet["udp"]["last_valid_packet_age_ms"] >= 1000
                            and quiet["mqtt"]["topics"]["RobotDynamicStatus"] == {"received": True, "stale": False},
                            f"Quiet snapshot lost counts or mixed stale video with live MQTT: {quiet}")
                    snapshots[name + "Quiet"] = name + "-quiet.json"

            target = evidence / "link-snapshot.json"
            committed = target.read_bytes()
            with prevent_replacement(target):
                await window.action("saveDiagnosticSnapshotButton")
                feedback = await window.observe("locked target gives save failure", snapshotSaveFeedback="^保存失败：")
                require(feedback["snapshotSaveEnabled"], "Failure left the save button disabled")
                require(target.read_bytes() == committed, "Failed atomic replace damaged the previous snapshot")
                await window.action("overviewTab")
                await set_health(324)
                await window.observe("receive remains responsive after write failure", healthValue="^324$",
                                     connectionValue="^五类订阅就绪$")
            await window.action("diagnosticsTab")
            recovered = await save_snapshot(window, evidence, title, "write-recovered")
            require(recovered["mqtt"]["state"] == "connected", "Saving interrupted the MQTT session")
            for index in range(3):
                await save_snapshot(window, evidence, title, f"repeat-{index + 1}")
            require([item.name for item in evidence.glob("link-snapshot*")] == ["link-snapshot.json"],
                    "Repeated saves left additional target or temporary files")
            snapshots["writeRecovered"] = "write-recovered.json"
            await window.action("captureDiagnostics")

            await window.action("overviewTab")
            await window.action("stopButton")
            await window.observe("stopped after playback", connectionValue="^已停止$", videoPreviewStatus="^已停止$")
            await window.action("diagnosticsTab")
            stopped = await save_snapshot(window, evidence, title, "stopped")
            assert_empty(stopped, stopped=True)
            require(not stopped["session"]["active"] and stopped["udp"]["state"] == "stopped"
                    and stopped["decode"]["state"] == "stopped"
                    and all(not item["received"] for item in stopped["mqtt"]["topics"].values()),
                    "Stopped snapshot retained active session state")
            snapshots["stopped"] = "stopped.json"
            with exclusive_udp(port):
                pass
            await window.action("overviewTab")
            await window.action("startButton")
            await window.observe("new receive session starts without video", connectionValue="^五类订阅就绪$",
                                 videoPreviewStatus="^等待模拟画面$")
            await window.action("diagnosticsTab")
            reopened = await save_snapshot(window, evidence, title, "reopened")
            assert_empty(reopened)
            require(reopened["decode"]["state"] == "waiting", "Reopened snapshot revived an old picture")
            snapshots["reopened"] = "reopened.json"

    client_packets = [row for row in packets if row["clientId"] == "3"]
    json_file(evidence / "broker-client-packets.json", client_packets)
    topics = [tuple(pair) for row in client_packets if row["kind"] == "subscribe" for pair in row["topics"]]
    require(sum(row["kind"] == "connect" for row in client_packets) == 3
            and sorted(topics) == sorted([(topic, 1) for topic in TOPICS] * 3),
            "Expected exactly three five-topic Qt connections at QoS 1")
    require(not any(row["kind"] == "client-publish" for row in client_packets), "Unexpected client business publish")
    wire_health = {RobotDynamicStatus.FromString(bytes.fromhex(row["hex"])).current_health
                   for row in client_packets if row["kind"] == "broker-publish" and row["topic"] == "RobotDynamicStatus"}
    require({321, 322, 323, 324} <= wire_health, f"Missing actual MQTT health updates: {wire_health}")
    with exclusive_udp(port):
        for tcp_port in (mqtt_port, web_port):
            with socket.socket() as probe:
                probe.settimeout(1)
                require(probe.connect_ex(("127.0.0.1", tcp_port)) != 0, f"Test listener still on port {tcp_port}")
    log_file, = evidence.glob("client-*.jsonl")
    records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    require(records[-1]["event"] == "client.stop", "Client did not log normal shutdown")
    return {"snapshots": snapshots, "captures": captures, "framesPerClip": frames_per_clip,
            "receivedPackets": total_packets, "decodedFrames": frames_per_clip * 2,
            "writeFailurePreservedPreviousFile": True, "repeatedSaves": 3,
            "mqttHealthInWindow": [321, 322, 323, 324], "mqttConnections": 3,
            "clientBusinessPublishes": 0, "clientLog": log_file.name,
            "releasedPorts": {"udp": port, "mqtt": mqtt_port, "web": web_port}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    args = parser.parse_args()
    directory = ROOT / "logs" / datetime.now().strftime("check-link-snapshot-%Y%m%d-%H%M%S-%f")
    directory.mkdir(parents=True)
    print(f"Link snapshot evidence: {directory}", flush=True)
    result = {"passed": False, "entry": "scripts/run.ps1", "configuration": args.configuration}
    try:
        result.update(asyncio.run(verify(args.configuration, directory)))
        result["passed"] = True
        print("PASS: normal Qt save, live MQTT/video, stale/reset states and atomic failure recovery.")
    except Exception:
        result["error"] = traceback.format_exc()
        print(result["error"], file=sys.stderr)
    json_file(directory / "summary.json", result)
    raise SystemExit(0 if result["passed"] else 1)
