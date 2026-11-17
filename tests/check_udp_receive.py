"""Exercise AT-052/053 through the Windows launcher, real Qt window and loopback sockets."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime
import json
import re
import socket
import subprocess
import sys
import time
import traceback
import uuid

from amqtt.broker import Broker
from check_mqtt_receive import ROOT, TOPICS, require
from simulator.tools.video_sender import send_video_as_hevc_udp


class Window:
    def __init__(self, process, evidence):
        self.process = process
        self.evidence = evidence

    async def reply(self):
        line = await asyncio.wait_for(self.process.stdout.readline(), 20)
        require(line, "Window driver closed; see window-driver.log")
        return json.loads(line)

    async def action(self, name):
        self.process.stdin.write((name + "\n").encode("ascii"))
        await self.process.stdin.drain()
        return await self.reply()

    async def observe(self, description, **patterns):
        start = time.monotonic()
        while True:
            view = await self.action("snapshot")
            if all(re.search(pattern, view.get(key, "")) for key, pattern in patterns.items()):
                with (self.evidence / "window.jsonl").open("a", encoding="utf-8") as log:
                    log.write(json.dumps({"observation": description, **view}, ensure_ascii=False) + "\n")
                return view
            if time.monotonic() - start > 12:
                raise AssertionError(f"{description} timed out. Last window: {view}")
            await asyncio.sleep(0.1)


@asynccontextmanager
async def open_window(config, title, configuration, *, trace_video=False):
    with (config.parent / "window-driver.log").open("wb") as errors:
        process = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(ROOT / "tests" / "check_udp_window.ps1"), "-ConfigFile", str(config),
            "-WindowTitle", title, "-Configuration", configuration,
            *(["-TraceSimulatedVideo"] if trace_video else []), cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
            creationflags=subprocess.CREATE_NO_WINDOW)
        window = Window(process, config.parent)
        try:
            require((await window.reply()).get("ready"), "Window driver did not open")
            yield window
        finally:
            process.stdin.close()
            exit_code = await asyncio.wait_for(process.wait(), 20)
        require(exit_code == 0, "Window failed to close; see window-driver.log")
        receipt = await window.reply()
        require(receipt["observation"] == "closed", "Missing normal window shutdown")
        (config.parent / "closed.json").write_text(json.dumps(receipt), encoding="utf-8")


def exclusive_udp(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", port))
        return sock
    except OSError:
        sock.close()
        raise


async def check_assembly(window, target):
    # Independent literal samples, deliberately using unequal fragment lengths.
    with exclusive_udp(0) as sender:
        source = rf"来源 127\.0\.0\.1:{sender.getsockname()[1]}\b"
        fragments = [
            bytes.fromhex("ff ff 00 00 00 00 00 06 41"),
            bytes.fromhex("ff ff 00 01 00 00 00 06 42 43"),
            bytes.fromhex("ff ff 00 02 00 00 00 06 44 45 46"),
        ]
        for index in (2, 1, 1, 0):
            sender.sendto(fragments[index], target)
        await window.observe("out-of-order and duplicate fragments complete one frame",
                             udpAssemblyLabel=r"完整帧 1\b.*重复分片 1\b",
                             udpLastFrameLabel=rf"帧号 65535 · 长度 6 字节 · {source}")

        sender.sendto(bytes.fromhex("00 00 00 00 00 00 00 01 47"), target)
        last = rf"帧号 0 · 长度 1 字节 · {source}"
        await window.observe("same sender wraps to complete frame zero", udpAssemblyLabel=r"完整帧 2\b",
                             udpLastFrameLabel=last)

        sender.sendto(bytes.fromhex("00 01 00 01 00 00 00 03 48"), target)
        await window.observe("incomplete frame expires without any further UDP traffic",
                             udpAssemblyLabel=r"(?s)完整帧 2\b.*丢帧 1\b.*超时 1\b.*在途 0 帧.*缓存 0 字节",
                             udpLastFrameLabel=last)

        for packet in (
            "00 02 00 00 00 00 00 02 49",  # Frame 2 announces 2 bytes.
            "00 02 00 01 00 00 00 03 4a",  # Same frame now announces 3.
            "00 02 00 01 00 00 00 02 4a",  # Old tail must not resurrect it.
            "00 03 00 00 ff ff ff ff 4b",  # Untrusted length must not allocate.
        ):
            sender.sendto(bytes.fromhex(packet), target)
        await window.observe("conflict, late tail and over-budget frame discarded",
                             udpAssemblyLabel=r"(?s)完整帧 2\b.*丢帧 3\b.*超时 1\b.*冲突 1\b.*超出预算 1\b"
                                              r".*重复分片 1\b.*迟到分片 1\b.*在途 0 帧.*缓存 0 字节",
                             udpLastFrameLabel=last, udpCountersLabel=r"^有效包 10 · 丢弃 0\b")


async def verify(configuration, evidence):
    clip = evidence / "four-frames.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=blue:size=1920x1080:rate=60",
                    "-frames:v", "4", "-c:v", "libx264", str(clip)], check=True, timeout=20)
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
        "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
                    "check_mqtt_receive.RecoveryPacketLog": {}},
    })
    title = "RM27 UDP test " + uuid.uuid4().hex
    async with AsyncExitStack() as services:
        await broker.start()
        services.push_async_callback(broker.shutdown)
        mqtt_port = broker._servers["default"].instance.sockets[0].getsockname()[1]
        packets = broker.plugins_manager.get_plugin("RecoveryPacketLog").packets
        blocker = services.enter_context(exclusive_udp(0))
        port = blocker.getsockname()[1]
        target = ("127.0.0.1", port)
        config = evidence / "infantry.json"
        config.write_text(json.dumps({
            "mode": "simulation", "seat": "infantry", "window": {"title": title, "width": 900, "height": 680},
            "mqtt": {"host": "127.0.0.1", "port": mqtt_port, "robotId": 3, "connectTimeoutMs": 1200},
            "video": {"bindAddress": "127.0.0.1", "port": port},
        }, indent=2), encoding="utf-8")

        async with open_window(config, title, configuration) as window:
            await window.observe("MQTT ready with UDP port occupied", connectionValue="^五类订阅就绪$",
                                 seatLabel="步兵（只读）")
            await broker.internal_message_broadcast("RobotStaticStatus", bytes.fromhex("20 03 28 03"), qos=1)
            await window.observe("fresh robot identity with UDP port occupied", identityValue=r"\b3\b")
            await broker.internal_message_broadcast("RobotDynamicStatus", bytes.fromhex("08 c1 02"), qos=1)
            await window.observe("fresh MQTT health with UDP port occupied", healthValue="^321$")
            await window.action("diagnosticsTab")
            await window.observe("port conflict reported", udpBindingLabel=rf"绑定失败.*127\.0\.0\.1:{port}\b")
            await window.action("overviewTab")
            await window.action("stopButton")
            await window.observe("first stop", connectionValue="^已停止$")
            blocker.close()
            await window.action("startButton")
            await window.observe("MQTT ready after manual restart", connectionValue="^五类订阅就绪$")
            await window.action("diagnosticsTab")
            await window.observe("UDP bound with fresh counters", udpBindingLabel=rf"已绑定 127\.0\.0\.1:{port}\b",
                                 udpCountersLabel=r"^有效包 0 · 丢弃 0\b", udpHeaderLabel="尚未收到有效包",
                                 udpAssemblyLabel=r"完整帧 0\b", udpLastFrameLabel="尚未收到完整帧")

            with exclusive_udp(0) as sender:
                source_port = sender.getsockname()[1]
                # PDF p.47: literal network-order bytes independent of both protocol implementations.
                max_packet = bytes.fromhex("ff ff 01 02 00 10 20 30") + bytes(1392)
                sender.sendto(max_packet, target)
                header = rf"来源 127\.0\.0\.1:{source_port} · 整包 1400 字节 · 帧号 65535 · 分片号 258 · 整帧 1056816 字节"
                await window.observe("inclusive 1400 bytes and big-endian fields", udpHeaderLabel=header,
                                     udpCountersLabel=r"^有效包 1 · 丢弃 0\b")
                for size in range(8):
                    sender.sendto(bytes(size), target)
                sender.sendto(max_packet + b"x", target)
                sender.sendto(bytes.fromhex("00 01 00 00 00 00 00 03"), target)
                sender.sendto(bytes.fromhex("00 01 00 00 00 00 00 01 aa bb"), target)
                await window.observe("bad packets counted; last valid header preserved", udpHeaderLabel=header,
                                     udpCountersLabel=r"^有效包 1 · 丢弃 11\b.*短包 8\b.*超长 1\b.*空载 1\b.*帧长矛盾 1\b")

                await services.aclose()
                await window.action("overviewTab")
                await window.observe("MQTT disconnected", connectionValue="^等待重连$")
                sender.sendto(bytes.fromhex("00 00 00 00 00 00 00 01 aa"), target)
                await window.action("diagnosticsTab")
                await window.observe("frame 65535 to 0 while MQTT offline", udpCountersLabel=r"^有效包 2 · 丢弃 11\b",
                                     udpHeaderLabel=r"整包 9 字节 · 帧号 0 · 分片号 0 · 整帧 1 字节",
                                     udpAssemblyLabel=r"完整帧 1\b",
                                     udpLastFrameLabel=rf"帧号 0 · 长度 1 字节 · 来源 127\.0\.0\.1:{source_port}\b")

                # Keep this source bound while the simulator opens its own UDP socket.
                await asyncio.to_thread(send_video_as_hevc_udp, str(clip), *target, loop=False)
            simulator = await window.observe("four HEVC frames from the simulator sender", udpHeaderLabel=r"帧号 3 · 分片号",
                                             udpCountersLabel=r"^有效包 (\d+) · 丢弃 11\b",
                                             udpAssemblyLabel=r"完整帧 5\b", udpLastFrameLabel=r"帧号 3 · 长度 [1-9]\d* 字节")
            simulator_packets = int(re.search(r"有效包 (\d+)", simulator["udpCountersLabel"])[1]) - 2
            require(simulator_packets >= 4, "Missing simulator packets")
            await window.action("overviewTab")
            await window.action("stopButton")
            await window.observe("manual stop while disconnected", connectionValue="^已停止$")
            with exclusive_udp(port):
                await window.action("diagnosticsTab")
                await window.observe("UDP released and last header cleared", udpBindingLabel="已停止",
                                     udpHeaderLabel="尚未收到有效包", udpCountersLabel=r"^有效包 0 · 丢弃 0\b",
                                     udpAssemblyLabel=r"(?s)完整帧 0\b.*超时 0\b.*在途 0 帧.*缓存 0 字节",
                                     udpLastFrameLabel="尚未收到完整帧")
            await window.action("overviewTab")
            await window.action("startButton")
            await window.action("diagnosticsTab")
            await window.observe("new session without old data", udpBindingLabel=rf"已绑定 127\.0\.0\.1:{port}\b",
                                 udpCountersLabel=r"^有效包 0 · 丢弃 0\b", udpHeaderLabel="尚未收到有效包",
                                 udpAssemblyLabel=r"完整帧 0\b", udpLastFrameLabel="尚未收到完整帧")
            await check_assembly(window, target)

    with exclusive_udp(port), socket.socket() as probe:
        probe.settimeout(1)
        require(probe.connect_ex(("127.0.0.1", mqtt_port)) != 0, "Test broker still listening")
    (evidence / "broker-packets.json").write_text(json.dumps(packets, indent=2), encoding="utf-8")
    topics = [tuple(pair) for row in packets if row["kind"] == "subscribe" for pair in row["topics"]]
    require(sorted(topics) == sorted([(topic, 1) for topic in TOPICS] * 2), "Expected two five-topic MQTT sessions")
    require(not any(row["kind"] == "client-publish" for row in packets), "Unexpected client business publish")
    log_file, = evidence.glob("client-*.jsonl")
    records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    events = [row["event"] for row in records if row["event"].startswith("video.")
              and row["event"] not in ("video.assembly_summary", "video.decode_summary")]
    require(events == ["video.bind_failed", "video.stopped", "video.bound", "video.stopped",
                       "video.bound", "video.stopped"] and records[-1]["event"] == "client.stop",
            f"Unexpected client lifecycle log: {events}")
    totals = [row["detail"] for row in records if row["event"] == "video.stopped"]
    require(totals == ["有效包 0 · 丢弃 0", f"有效包 {simulator_packets + 2} · 丢弃 11", "有效包 10 · 丢弃 0"],
            f"Client log disagrees with window counters: {totals}")
    assembly = [row["detail"] for row in records if row["event"] == "video.assembly_summary"]
    require(len(assembly) == 2 and re.search(r"完整帧 5\b", assembly[0])
            and re.search(r"完整帧 2\b.*超时 1\b.*冲突 1\b.*超出预算 1\b", assembly[1]),
            f"Client log disagrees with frame results: {assembly}")
    return {"udpPortReleased": port, "brokerPortReleased": mqtt_port, "simulatorPackets": simulator_packets,
            "simulatorCompleteFrames": 4, "fixtureCompleteFrames": 2, "fixtureTimeouts": 1,
            "fixtureConflicts": 1, "fixtureBudgetDrops": 1, "mqttSubscriptions": len(topics),
            "clientBusinessPublishes": 0, "clientLog": log_file.name}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    args = parser.parse_args()
    directory = ROOT / "logs" / ("check-udp-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    directory.mkdir(parents=True)
    print(f"UDP evidence: {directory}", flush=True)
    result = {"passed": False, "entry": "scripts/run.ps1 -SkipBuild -ConfigFile", "configuration": args.configuration}
    try:
        result.update(asyncio.run(verify(args.configuration, directory)))
        result["passed"] = True
    except Exception:
        result["error"] = traceback.format_exc()
        print(result["error"], file=sys.stderr)
    (directory / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    raise SystemExit(0 if result["passed"] else 1)
