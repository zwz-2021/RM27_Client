"""S2 live checks: normal simulator console -> isolated AMQTT -> real Qt/QML.

The Qt probe uses the production data source/session/view model. Its JSON lines
are observations only; fixtures enter through the real Socket.IO console API.
AMQTT and the deliberately incomplete fault broker do not verify Mosquitto,
official hardware, permissions, or any robot.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid

from amqtt.plugins.base import BasePlugin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TOPICS = {"GameStatus", "GlobalUnitStatus", "GlobalLogisticsStatus",
          "RobotStaticStatus", "RobotDynamicStatus"}
TOTAL_ECONOMY = "18446744073709551615"
INFANTRY_LABEL = "本地席位 · 步兵（只读）"
UNSPECIFIED_LABEL = "本地席位 · 未指定（只读）"
INFANTRY_FEEDBACK = "步兵席只读，请在官方操作端执行赛事操作。"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class QtProbe:
    """A separately running Qt GUI, controlled without modifying its state."""

    def __init__(self, executable, evidence, name, port, robot_id=3, screenshot=False, timeout_ms=1500, seat=None):
        self.output = evidence / f"{name}.jsonl"
        self.control = evidence / f"{name}.control"
        self.control.write_text("0 none", encoding="utf-8")
        self.console = (evidence / f"{name}.log").open("wb")
        self.sequence = 0
        self.samples = []
        self.offset = 0
        settings = {"mode": "simulation", "mqtt": {"host": "127.0.0.1", "port": port,
                    "robotId": robot_id, "connectTimeoutMs": timeout_ms}}
        if seat is not None:
            settings["seat"] = seat
        config = evidence / f"{name}.config.json"
        config.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        arguments = [str(executable), "--config", str(config),
                     "--output", str(self.output), "--control", str(self.control)]
        if screenshot:
            arguments += ["--screenshot", str(evidence / f"{name}.png")]
        self.process = subprocess.Popen(
            arguments,
            cwd=ROOT, stdout=self.console, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def read_new(self):
        if not self.output.exists():
            return []
        fresh = []
        with self.output.open("rb") as stream:
            stream.seek(self.offset)
            while True:
                start = stream.tell()
                line = stream.readline()
                if not line or not line.endswith(b"\n"):
                    self.offset = start
                    break
                fresh.append(json.loads(line))
                self.offset = stream.tell()
        self.samples.extend(fresh)
        return fresh

    def wait(self, predicate, description, timeout=10, after=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            fresh = self.read_new()
            candidates = fresh or self.samples[-1:]
            for sample in candidates:
                if (after is None or sample.get("commandSeq", -1) >= after) and predicate(sample):
                    return sample
            require(self.process.poll() is None,
                    f"Qt exited ({self.process.returncode}) while waiting for {description}; see {self.output.with_suffix('.log')}")
            time.sleep(0.025)
        last = self.samples[-1] if self.samples else None
        raise AssertionError(f"Qt timeout: {description}; last={last}")

    def command(self, action):
        self.sequence += 1
        # Same-volume replacement prevents the reader from observing partial text.
        pending = self.control.with_suffix(".pending")
        pending.write_text(f"{self.sequence} {action}", encoding="utf-8")
        # Windows may briefly deny rename while QFile has the destination open.
        # Retry only that transient sharing/permission collision, with a bound.
        deadline = time.monotonic() + 2
        while True:
            try:
                os.replace(pending, self.control)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
        return self.sequence

    def stop(self):
        seq = self.command("stop")
        sample = self.wait(lambda s: not s["running"], "stopped session", after=seq)
        require(not sample["connected"] and not sample["subscriptionsReady"],
                "Stopped session still reports transport ready")
        require(sample["health"] is None and not sample["topics"],
                "Stopped session retained active authoritative data")
        return sample

    def perform(self, action, predicate, description):
        return self.wait(predicate, description, after=self.command(action))

    def blur_with_input(self):
        before = self.perform("focus", lambda s: s["windowFocused"], "Qt window has keyboard focus")
        self.perform("held-input", lambda s: s["wPresses"] > before["wPresses"]
                     and s["mouseMoves"] > before["mouseMoves"], "W press and mouse movement delivered")
        self.perform("blur", lambda s: s["peerFocused"] and not s["windowFocused"],
                     "focus transferred to a separate window with W held")
        self.perform("release", lambda s: s["peerFocused"] and s["wReleases"] > before["wReleases"],
                     "W released in the separate window")

    def close(self):
        try:
            if self.process.poll() is None:
                self.command("quit")
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
                    raise AssertionError("Qt did not release resources and exit within 5 seconds")
            require(self.process.returncode == 0,
                    f"Qt failed on shutdown: {self.process.returncode}")
        finally:
            self.console.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


class WireCapture:
    def __init__(self, port, evidence):
        import paho.mqtt.client as mqtt
        from simulator.protocol import rm27_base_pb2 as pb
        self.messages = {topic: getattr(pb, topic) for topic in TOPICS}
        self.ready = threading.Event()
        self.condition = threading.Condition()
        self.latest = {}
        self.errors = []
        self.file = (evidence / "mqtt-wire.jsonl").open("w", encoding="utf-8")
        self.peer = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                client_id=f"rm27_check_{uuid.uuid4().hex}")

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code == 0:
                client.subscribe([(topic, 1) for topic in sorted(TOPICS)])

        def on_subscribe(client, userdata, mid, reason_codes, properties):
            if all(code < 128 for code in reason_codes):
                self.ready.set()

        def on_message(client, userdata, message):
            with self.condition:
                try:
                    require(message.qos <= 1, "Received QoS exceeds fixed protocol limit")
                    decoded = self.messages[message.topic].FromString(message.payload)
                    self.latest[message.topic] = decoded
                    self.file.write(json.dumps({"at": time.time(), "topic": message.topic,
                                                "qos": message.qos, "hex": message.payload.hex()}) + "\n")
                    self.file.flush()
                except Exception as error:
                    self.errors.append(str(error))
                self.condition.notify_all()

        self.peer.on_connect = on_connect
        self.peer.on_subscribe = on_subscribe
        self.peer.on_message = on_message
        self.peer.connect("127.0.0.1", port, keepalive=10)
        self.peer.loop_start()
        require(self.ready.wait(5), "Wire capture subscriptions were not acknowledged")

    def wait(self, topic, predicate, timeout=6):
        with self.condition:
            ok = self.condition.wait_for(
                lambda: self.errors or (topic in self.latest and predicate(self.latest[topic])), timeout)
            require(not self.errors, f"Capture decode error: {self.errors}")
            require(ok, f"Expected simulator payload did not arrive: {topic}")
            return self.latest[topic]

    def close(self):
        try:
            self.peer.disconnect()
            self.peer.loop_stop()
        finally:
            self.file.close()


def exercise_console(executable, evidence, base_url, port, cycles):
    import requests
    import socketio
    session = requests.Session()
    session.trust_env = False
    console = socketio.Client(reconnection=False, request_timeout=3, http_session=session)
    capture = None
    checks = []

    def get_state():
        response = session.get(base_url + "/api/state", timeout=3)
        response.raise_for_status()
        return response.json()

    def command(name, **values):
        reply = console.call("referee_command", {"command": name, **values}, timeout=5)
        require(isinstance(reply, dict) and reply.get("ok"), f"Console rejected {name}: {reply}")
        return reply

    try:
        for asset in ("/", "/app.js", "/vendor/socket.io.min.js"):
            response = session.get(base_url + asset, timeout=3)
            require(response.status_code == 200 and response.content, f"Missing console asset {asset}")
        console.connect(base_url, transports=["websocket"], wait_timeout=5)
        capture = WireCapture(port, evidence)
        for robot_id, team in ((3, "red"), (103, "blue")):
            command("set_current_robot", robot_id=robot_id)
            state = get_state()
            index = state["robotIds"].index(robot_id)
            command("set_basic_robot_values", robot_index=index, health=321, heat=12.5, bullets=-7)
            command("set_logistics_protocol_state", team=team, total_economy_obtained=TOTAL_ECONOMY)
            command("set_base_game_status", current_stage=4, stage_countdown_sec=-1,
                    stage_elapsed_sec=30, is_paused=True)
            capture.wait("RobotStaticStatus", lambda m: m.robot_id == robot_id and m.robot_type == 3)
            capture.wait("RobotDynamicStatus", lambda m: m.current_health == 321 and m.current_heat == 12.5)
            unit = capture.wait("GlobalUnitStatus", lambda m: len(m.robot_health) == 8 and m.robot_health[1] == 321)
            require(len(unit.robot_bullets) == 6 and unit.robot_bullets[2] == -7,
                    "P-002 six-slot signed ammo mapping differs from designated reference")
            capture.wait("GlobalLogisticsStatus", lambda m: m.total_economy_obtained == int(TOTAL_ECONOMY))
            capture.wait("GameStatus", lambda m: m.stage_countdown_sec == -1 and m.is_paused)
            require(get_state()["globalLogisticsStatus"][f"{team}_total_economy_obtained"] == TOTAL_ECONOMY,
                    "Console JSON lost uint64 decimal precision")
            seat = "infantry" if team == "blue" else None
            with QtProbe(executable, evidence, f"qt-{team}", port, robot_id, screenshot=True, seat=seat) as qt:
                sample = qt.wait(
                    lambda s: s["subscriptionsReady"] and set(s["topics"]) == TOPICS
                    and s["receivedRobotId"] == robot_id and s["health"] == "321"
                    and s["totalEconomy"] == TOTAL_ECONOMY,
                    f"five normal console topics visible in Qt ({team})")
                require(sample["qmlLoaded"], "Qt probe did not load production QML")
                require(sample["qmlHealth"] == "321", "Actual QML HP label does not show 321")
                require(TOTAL_ECONOMY in sample["ui"]["logistics"],
                        "Visible logistics text lost uint64 decimal precision")
                require(float(sample["heat"]) == 12.5, "Qt heat lost its fractional part")
                require(sample["gameCountdown"] == "-1" and sample["paused"] is True,
                        "Qt lost signed game time or pause state")
                require(sample["unitHealth"][1] == 321 and sample["unitBullets"][2] == -7,
                        "Qt global array mapping differs from wire")
                checks.append(f"{team}: console -> broker -> Qt/QML HP 321 and all five topics")
                require(sample["qmlSeat"] == (INFANTRY_LABEL if seat else UNSPECIFIED_LABEL)
                        and sample["actionAvailable"] == bool(seat),
                        "QML seat or action visibility differs from the explicit configuration")
                if seat:
                    qt.blur_with_input()
                    command("set_basic_robot_values", robot_index=index, health=323)
                    qt.wait(lambda s: s["qmlHealth"] == "323" and s["peerFocused"] and set(s["topics"]) == TOPICS,
                            "five-topic receiving continues while product window is unfocused")
                    qt.perform("focus", lambda s: s["windowFocused"] and not s["peerFocused"],
                               "focus returns to product window")
                else:
                    qt.perform("shortcut", lambda s: not s["actionAvailable"] and not s["qmlActionFeedback"],
                               "robot ID 3 alone exposes no infantry action")
                # A subsequent console write proves the visible data is live.
                command("set_basic_robot_values", robot_index=index, health=322)
                qt.wait(lambda s: s["health"] == "322", "live console HP update")
                qt.stop()
                if team == "red":
                    for cycle in range(cycles):
                        seq = qt.command("start")
                        qt.wait(lambda s: s["running"] and s["subscriptionsReady"],
                                f"start cycle {cycle + 1}", after=seq)
                        qt.stop()
                    checks.append(f"{cycles} start/stop cycles; each stop cleared transport/data")
                seq = qt.command("start")
                qt.wait(lambda s: s["health"] == "322" and set(s["topics"]) == TOPICS,
                        "fresh data after restart", after=seq)
                qt.stop()
            require((evidence / f"qt-{team}.png").is_file(), "Qt did not save its actual QML screenshot")
        return checks
    finally:
        try:
            if console.connected:
                console.disconnect()
        finally:
            try:
                if capture is not None:
                    capture.close()
            finally:
                session.close()


def exercise_injection(executable, evidence, port):
    """Independent literal bytes after stopping this run's simulator publisher."""
    import paho.mqtt.client as mqtt
    peer = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                       client_id=f"rm27_injection_{uuid.uuid4().hex}")
    wire = (evidence / "injected-wire.jsonl").open("w", encoding="utf-8")

    def publish(topic, payload, retain=False):
        wire.write(json.dumps({"at": time.time(), "topic": topic,
                               "hex": payload.hex(), "retain": retain}) + "\n")
        wire.flush()
        result = peer.publish(topic, payload, qos=1, retain=retain)
        result.wait_for_publish(timeout=5)
        require(result.is_published(), "Independent sample was not acknowledged")

    peer.connect("127.0.0.1", port, keepalive=10)
    peer.loop_start()
    try:
        publish("RobotDynamicStatus", bytes.fromhex("08 c1 02"), retain=True)
        with QtProbe(executable, evidence, "qt-injection", port, 3) as qt:
            qt.wait(lambda s: s["subscriptionsReady"], "independent sample subscriptions")
            sample = qt.wait(lambda s: "保留报文" in s["error"], "retained payload explicitly rejected")
            require(sample["health"] is None and not sample["topics"], "Retained payload became live state")
            publish("RobotDynamicStatus", b"", retain=True)
            # PDF61: uint32 robot_id field4, robot_type field5 (P-003).
            publish("RobotStaticStatus", bytes.fromhex("20 03 28 03"))
            qt.wait(lambda s: s["receivedRobotId"] == 3, "matching static identity")
            # PDF62: uint32 HP field1 =321, float heat field2 =12.5.
            publish("RobotDynamicStatus", bytes.fromhex("08 c1 02 15 00 00 48 41"))
            qt.wait(lambda s: s["health"] == "321", "independent HP321 wire sample")
            # Header says varint HP but its value is truncated. No partial write.
            publish("RobotDynamicStatus", b"\x08")
            sample = qt.wait(lambda s: "坏包" in s["error"], "truncated protobuf visible rejection")
            require(sample["health"] == "321", "Malformed packet polluted the last valid HP")
            # Explicit zero remains distinct from no optional field.
            publish("RobotDynamicStatus", bytes.fromhex("08 00"))
            sample = qt.wait(lambda s: s["health"] == "0" and s["qmlHealth"] == "0",
                             "explicit HP zero in actual QML")
            publish("RobotDynamicStatus", b"")
            qt.wait(lambda s: s["health"] is None and "RobotDynamicStatus" in s["topics"]
                    and s["qmlHealth"] == "—", "optional HP omitted in actual QML")
            publish("RobotDynamicStatus", bytes.fromhex("08 c1 02"))
            qt.wait(lambda s: s["health"] == "321", "HP restored before identity mismatch")
            publish("RobotStaticStatus", bytes.fromhex("20 67 28 03"))
            qt.wait(lambda s: s["health"] is None and "静态身份" in s["error"],
                    "wrong static identity clears robot-relative data")
            publish("RobotStaticStatus", bytes.fromhex("20 03 28 03"))
            qt.wait(lambda s: s["receivedRobotId"] == 3, "matching identity recovered")
            publish("RobotDynamicStatus", bytes.fromhex("08 c1 02"))
            qt.wait(lambda s: s["health"] == "321", "matching identity accepts new HP")
            # No per-packet await: the callback mailbox sees cross-topic bursts.
            # Immediate state-change observations in the Qt probe also catch a
            # transient wrong assignment that a 50ms periodic poll could miss.
            for burst in range(10):
                publish("RobotStaticStatus", bytes.fromhex("20 03 28 03"))
                publish("RobotDynamicStatus", bytes.fromhex("08 c1 02"))
                qt.wait(lambda s: s["health"] == "321", "known HP before identity burst")
                first_sample = len(qt.samples)
                packets = [("RobotStaticStatus", bytes.fromhex("20 67 28 03")),
                           ("RobotDynamicStatus", bytes.fromhex("08 bc 03")),
                           ("RobotStaticStatus", bytes.fromhex("20 03 28 03")),
                           ("GameStatus", bytes([0x30, 40 + burst]))]
                pending = []
                for topic, payload in packets:
                    wire.write(json.dumps({"at": time.time(), "topic": topic,
                                           "hex": payload.hex(), "burst": burst}) + "\n")
                    pending.append(peer.publish(topic, payload, qos=1))
                wire.flush()
                for result in pending:
                    result.wait_for_publish(timeout=5)
                    require(result.is_published(), "Identity burst was not acknowledged")
                sample = qt.wait(lambda s: s["gameCountdown"] == str(40 + burst),
                                 f"identity burst {burst + 1} applied in receive order")
                require(sample["health"] is None, "Cross-robot burst retained previous robot-relative data")
                require(all(s["health"] != "444" and s["qmlHealth"] != "444"
                            for s in qt.samples[first_sample:]),
                        "Other robot's burst HP444 was assigned to configured robot3")
            publish("RobotStaticStatus", bytes.fromhex("20 03 28 03"))
            publish("RobotDynamicStatus", bytes.fromhex("08 c1 02"))
            qt.wait(lambda s: s["health"] == "321", "HP restored after identity bursts")
            # Keep Game fresh while Dynamic stops. Repeated records prove this
            # is per-topic age, not an aggregate MQTT last-message timestamp.
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                publish("GameStatus", bytes.fromhex("28 04 30 0a 40 01"))
                time.sleep(0.15)
            sample = qt.wait(lambda s: "RobotDynamicStatus" in s["staleTopics"]
                             and s["qmlHealth"] == "—", "only stopped Dynamic becomes stale in QML")
            require("GameStatus" not in sample["staleTopics"], "Fresh Game became stale with Dynamic")
            publish("RobotStaticStatus", bytes.fromhex("20 03 28 03"))
            qt.wait(lambda s: "RobotStaticStatus" not in s["staleTopics"] and s["receivedRobotId"] == 3,
                    "static identity fresh before Dynamic recovery")
            publish("RobotDynamicStatus", bytes.fromhex("08 c1 02"))
            qt.wait(lambda s: s["health"] == "321" and "RobotDynamicStatus" not in s["staleTopics"],
                    "new Dynamic clears its stale flag")
            qt.stop()
        return ["independent bytes: retained rejected, malformed, zero/absent HP, wrong identity, per-topic stale/recovery",
                "10 cross-topic identity bursts: other robot HP444 never assigned or shown"]
    finally:
        try:
            peer.disconnect()
            peer.loop_stop()
        finally:
            wire.close()


async def mqtt_packet(reader):
    header = await reader.readexactly(1)
    length = 0
    multiplier = 1
    for _ in range(4):
        encoded = (await reader.readexactly(1))[0]
        length += (encoded & 127) * multiplier
        if not encoded & 128:
            require(length <= 1024 * 1024, "Fault peer received oversized packet")
            return header[0], await reader.readexactly(length)
        multiplier *= 128
    raise AssertionError("Malformed MQTT remaining length")


class FaultBroker:
    """Tiny wire fixture only: tests failure/readiness, not MQTT conformance."""

    def __init__(self, mode):
        self.mode = mode
        self.connections = set()
        self.accept_count = 0
        self.identity_barrier = threading.Event()
        self.observed = []
        self.errors = []

    async def accept(self, reader, writer):
        self.connections.add(writer)
        self.accept_count += 1
        attempt = self.accept_count
        pending_pubacks = set()
        subscribed_topics = set()

        def send_publish(topic, payload, kind, packet_id=None):
            encoded = topic.encode("utf-8")
            packet_id_bytes = b"" if packet_id is None else packet_id.to_bytes(2, "big")
            publish_body = len(encoded).to_bytes(2, "big") + encoded + packet_id_bytes + payload
            require(len(publish_body) < 128, "Fault fixture packet needs multi-byte remaining length")
            writer.write(bytes([0x30 if packet_id is None else 0x32, len(publish_body)]) + publish_body)
            self.observed.append({"kind": kind, "topic": topic, "attempt": attempt, "packetId": packet_id,
                                  "hex": payload.hex(), "at": time.monotonic()})

        try:
            while True:
                header, body = await mqtt_packet(reader)
                kind = header >> 4
                if kind == 1:
                    require(body[:7] == b"\x00\x04MQTT\x04", "Expected MQTT 3.1.1 CONNECT")
                    size = int.from_bytes(body[10:12], "big")
                    client_id = body[12:12 + size].decode("utf-8")
                    self.observed.append({"kind": "connect", "clientId": client_id, "attempt": attempt})
                    if self.mode == "timeout":
                        continue
                    writer.write(b"\x20\x02\x00\x00")
                elif kind == 8:
                    pos, codes = 2, []
                    while pos < len(body):
                        size = int.from_bytes(body[pos:pos + 2], "big")
                        pos += 2
                        topic = body[pos:pos + size].decode("utf-8")
                        pos += size
                        qos = body[pos]
                        pos += 1
                        self.observed.append({"kind": "subscribe", "topic": topic, "qos": qos, "attempt": attempt})
                        subscribed_topics.add(topic)
                        codes.append(128 if self.mode == "reject" and topic == "RobotDynamicStatus" else min(qos, 1))
                    if self.mode == "delayed" and subscribed_topics == TOPICS:
                        # Publish before the final SUBACK, then hold the ACK.
                        # The receive time must survive the pre-ready mailbox.
                        for topic, payload in (("RobotStaticStatus", bytes.fromhex("20 03 28 03")),
                                               ("RobotDynamicStatus", bytes.fromhex("08 c1 02"))):
                            send_publish(topic, payload, "publish-before-final-suback")
                        await writer.drain()
                        await asyncio.sleep(1.3)
                        self.observed.append({"kind": "delayed-final-suback", "at": time.monotonic()})
                    if self.mode == "overflow" and subscribed_topics == TOPICS:
                        # The ninth static identity exceeds the engineering
                        # queue bound of eight before any queued data is usable.
                        # Withhold the last ACK so failure cannot look ready.
                        for index in range(9):
                            send_publish("RobotStaticStatus", bytes([0x20, 3 if index % 2 == 0 else 103, 0x28, 3]),
                                         "static-before-withheld-suback")
                        await writer.drain()
                        continue
                    if self.mode == "abandoned" and subscribed_topics == TOPICS and attempt == 1:
                        # Withhold the last SUBACK. Require PUBACKs for both
                        # old packets before dropping this TCP connection.
                        send_publish("RobotStaticStatus", bytes.fromhex("20 03 28 03"), "old-static", 1)
                        send_publish("RobotDynamicStatus", bytes.fromhex("08 bc 03"), "old-hp444", 2)
                        pending_pubacks = {1, 2}
                        await writer.drain()
                        continue
                    writer.write(bytes([0x90, 2 + len(codes)]) + body[:2] + bytes(codes))
                    if self.mode == "abandoned":
                        self.observed.append({"kind": "suback", "attempt": attempt, "codes": codes})
                        if subscribed_topics == TOPICS and attempt == 2:
                            send_publish("GameStatus", bytes.fromhex("30 29"), "new-game-barrier")
                            await writer.drain()
                            require(await asyncio.to_thread(self.identity_barrier.wait, 10),
                                    "Qt did not observe the new game barrier before the new identity")
                            send_publish("RobotStaticStatus", bytes.fromhex("20 03 28 03"), "new-static")
                            send_publish("RobotDynamicStatus", bytes.fromhex("08 c2 02"), "new-hp322")
                    if self.mode == "disconnect" and subscribed_topics == TOPICS:
                        send_publish("RobotStaticStatus", bytes.fromhex("20 03 28 03"), "publish-after-suback")
                        send_publish("RobotDynamicStatus", bytes.fromhex("08 c1 02"), "publish-after-suback")
                        await writer.drain()
                        await asyncio.sleep(0.3)
                        self.observed.append({"kind": "close-connected-peer", "at": time.monotonic()})
                        break
                elif kind == 4 and self.mode == "abandoned" and attempt == 1:
                    packet_id = int.from_bytes(body, "big")
                    require(packet_id in pending_pubacks, "Unexpected old-attempt PUBACK")
                    self.observed.append({"kind": "old-puback", "attempt": attempt, "packetId": packet_id})
                    pending_pubacks.remove(packet_id)
                    if not pending_pubacks:
                        break
                elif kind == 12:
                    writer.write(b"\xd0\x00")
                elif kind == 14:
                    break
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        except Exception as error:
            self.errors.append(str(error))
        finally:
            self.connections.discard(writer)
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()

    async def close(self):
        self.identity_barrier.set()
        for writer in list(self.connections):
            writer.close()
        for writer in list(self.connections):
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()


def exercise_fault(executable, evidence, mode, port, fixture=None):
    with QtProbe(executable, evidence, f"qt-{mode}", port,
                 timeout_ms=3500 if mode == "delayed" else 800) as qt:
        if mode == "empty":
            sample = qt.wait(lambda s: s["subscriptionsReady"], "accepted subscriptions without data")
            require(sample["connected"] and not sample["topics"] and sample["health"] is None,
                    "Connected empty broker created fake robot data")
        elif mode == "delayed":
            qt.wait(lambda s: s["subscriptionsReady"] and s["health"] == "321"
                    and "RobotDynamicStatus" in s["staleTopics"] and s["qmlHealth"] == "—",
                    "pre-ready Dynamic retains original age and is stale on delivery")
            require(all(s["health"] != "321" or "RobotDynamicStatus" in s["staleTopics"]
                        for s in qt.samples), "Pre-ready old Dynamic briefly became fresh")
            require(all(s["qmlHealth"] != "321" for s in qt.samples),
                    "Pre-ready old Dynamic briefly appeared live in QML")
        elif mode == "disconnect":
            for _ in range(2):
                qt.wait(lambda s: s["subscriptionsReady"] and s["health"] == "321"
                        and s["qmlHealth"] == "321", "live HP before peer closes TCP")
                sample = qt.wait(lambda s: s["retryWaiting"] and not s["topics"]
                                 and s["health"] is None and s["qmlHealth"] == "—",
                                 "connected peer loss clears data and actual QML")
                require(not sample["subscriptionsReady"] and not sample["connected"]
                        and "断开" in sample["error"], "Connection loss was not diagnosed correctly")
        elif mode == "abandoned":
            qt.wait(lambda s: s["retryWaiting"], "first attempt fails without its final SUBACK")
            require(not any(s["subscriptionsReady"] for s in qt.samples), "Unacknowledged attempt became ready")
            qt.wait(lambda s: s["subscriptionsReady"] and s["gameCountdown"] == "41",
                    "game barrier on replacement connection")
            require(all(s["receivedRobotId"] is None and s["health"] is None and s["qmlHealth"] == "—"
                        for s in qt.samples), "Pre-SUBACK identity or HP crossed to the replacement connection")
            fixture.identity_barrier.set()
            qt.wait(lambda s: s["receivedRobotId"] == 3 and s["health"] == "322" and s["qmlHealth"] == "322",
                    "fresh identity and HP after the observed game barrier")
            require(all(s["health"] != "444" and s["qmlHealth"] != "444" for s in qt.samples),
                    "Old pre-SUBACK HP444 was briefly accepted")
        elif mode == "overflow":
            sample = qt.wait(lambda s: s["retryWaiting"], "static identity queue overflow is visible")
            require("静态身份" in sample["error"] and "上限" in sample["error"],
                    "Identity queue overflow was mistaken for another connection failure")
            require(not sample["topics"] and sample["qmlHealth"] == "—",
                    "Identity overflow left robot data visible")
            require(not any(s["subscriptionsReady"] for s in qt.samples),
                    "Identity overflow became ready before rejection")
        else:
            sample = qt.wait(lambda s: s["retryWaiting"], f"visible {mode} failure", timeout=15)
            require(not sample["subscriptionsReady"] and sample["health"] is None,
                    f"{mode} failure falsely became ready or populated robot HP")
            if mode == "reject":
                require(all(part in sample["error"] for part in ("拒绝订阅", "RobotDynamicStatus", "SUBACK", "0x80")),
                        f"SUBACK rejection lacks its topic or reason: {sample['error']}")
        qt.stop()


class RecoveryPacketLog(BasePlugin):
    """AMQTT wire observations attributed to the connecting MQTT client."""

    def __init__(self, context):
        super().__init__(context)
        self.packets = []

    async def on_mqtt_packet_received(self, *, packet, session=None):
        from amqtt.mqtt.packet import CONNECT, PUBACK, PUBLISH, SUBSCRIBE
        kind = packet.fixed_header.packet_type
        row = {"at": time.monotonic(), "clientId": session.client_id if session else None}
        if kind == CONNECT:
            row.update(kind="connect", clientId=packet.client_id, cleanSession=packet.clean_session_flag)
        elif kind == PUBLISH:
            row.update(kind="client-publish", topic=packet.variable_header.topic_name)
        elif kind == SUBSCRIBE:
            row.update(kind="subscribe", id=packet.variable_header.packet_id, topics=packet.payload.topics)
        elif kind == PUBACK:
            row.update(kind="client-puback", id=packet.variable_header.packet_id)
        else:
            return
        self.packets.append(row)

    async def on_mqtt_packet_sent(self, *, packet, session=None):
        from amqtt.mqtt.packet import PUBLISH, SUBACK
        if packet.fixed_header.packet_type == SUBACK:
            self.packets.append({"kind": "suback", "at": time.monotonic(), "clientId": session.client_id,
                                 "id": packet.variable_header.packet_id, "codes": packet.payload.return_codes})
        elif packet.fixed_header.packet_type == PUBLISH:
            self.packets.append({"kind": "broker-publish", "at": time.monotonic(), "clientId": session.client_id,
                                 "topic": packet.variable_header.topic_name, "hex": packet.payload.data.hex()})


async def exercise_recovery(executable, evidence):
    from amqtt.broker import Broker

    wire = {}
    broker = None
    port = 0
    retries = []

    async def start_broker(phase):
        nonlocal broker, port
        broker = Broker({
            "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}},
            "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
                        f"{__name__}.RecoveryPacketLog": {}},
        })
        wire[phase] = broker.plugins_manager.get_plugin("RecoveryPacketLog").packets
        await broker.start()
        port = broker._servers["default"].instance.sockets[0].getsockname()[1]

    async def stop_broker():
        nonlocal broker
        if broker is not None:
            await broker.shutdown()
            broker = None

    async def publish(topic, wire_hex):
        await broker.internal_message_broadcast(topic, bytes.fromhex(wire_hex), qos=1)

    async def publish_five(hp_hex):
        await publish("RobotStaticStatus", "20 03 28 03")
        await publish("GameStatus", "30 0a")
        await publish("GlobalUnitStatus", "5a 08 01 02 03 04 05 06 07 08 62 06 01 02 03 04 05 06")
        await publish("GlobalLogisticsStatus", "10 2a")
        await publish("RobotDynamicStatus", hp_hex)

    def next_attempt(qt, after_ms):
        return next((row for row in qt.samples if row["elapsedMs"] > after_ms
                     and row["connectionDetail"].startswith("正在连接 MQTT ")), None)

    def record_retry_interval(qt, retry):
        attempt = next_attempt(qt, retry["observedAtMs"])
        require(attempt is not None, "Missing Connecting observation after retry")
        elapsed = attempt["elapsedMs"] - retry["observedAtMs"]
        retry.update(nextConnectAttemptAtMs=attempt["elapsedMs"], actualWaitMs=elapsed)
        require(retry["delayMs"] * 0.9 <= elapsed <= retry["delayMs"] + 750,
                f"Waiting -> Connecting interval outside local scheduling tolerance: {retry}")

    async def wait_retry(qt, delay, after_ms=None):
        return await asyncio.to_thread(
            qt.wait, lambda s: s["retryWaiting"] and s["running"]
            and (after_ms is None or (attempt := next_attempt(qt, after_ms)) is not None
                 and s["elapsedMs"] >= attempt["elapsedMs"])
            and str(delay) + " 毫秒" in s["connectionDetail"] and "重连" in s.get("qmlConnection", "")
            and not s["subscriptionsReady"] and not s["topics"] and not s["staleTopics"]
            and s["receivedRobotId"] is None and s.get("qmlHealth") == "—",
            f"clear all five topics and show {delay}ms retry", 15)

    try:
        await start_broker("before-loss")
        with QtProbe(executable, evidence, "qt-recovery", port, seat="infantry") as qt:
            await asyncio.to_thread(qt.wait, lambda s: s["subscriptionsReady"], "initial five SUBACKs")
            await publish_five("08 c1 02")
            before = await asyncio.to_thread(qt.wait, lambda s: set(s["topics"]) == TOPICS and s["qmlHealth"] == "321",
                                             "all five topics before AMQTT shutdown")
            require(before["qmlSeat"] == INFANTRY_LABEL and before["actionAvailable"] and not before["qmlActionFeedback"],
                    "Infantry seat/action/initial feedback not rendered from configuration")
            await asyncio.to_thread(qt.perform, "click-action", lambda s: s["qmlActionFeedback"] == INFANTRY_FEEDBACK,
                                    "actual Qt button click explains infantry refusal")
            await asyncio.to_thread(qt.blur_with_input)
            await publish_five("08 c3 02")
            await asyncio.to_thread(qt.wait, lambda s: s["peerFocused"] and s["qmlHealth"] == "323"
                                    and set(s["topics"]) == TOPICS and not s["staleTopics"],
                                    "fresh five-topic receiving during loss of input focus")
            await asyncio.to_thread(qt.perform, "focus", lambda s: s["windowFocused"], "focus restored to product")
            await stop_broker()
            last = None
            for delay in (500, 1000, 2000, 4000, 4000):
                sample = await wait_retry(qt, delay, last)
                retries.append({"delayMs": delay, "observedAtMs": sample["elapsedMs"]})
                if last is not None:
                    record_retry_interval(qt, retries[-2])
                last = sample["elapsedMs"]

            await start_broker("after-loss")
            started = time.monotonic()
            sample = await asyncio.to_thread(qt.wait, lambda s: s["subscriptionsReady"],
                                             "automatic resubscription within 10 seconds", 10)
            recovery_ms = round((time.monotonic() - started) * 1000)
            record_retry_interval(qt, retries[-1])
            require(recovery_ms <= 10000 and not sample["topics"] and sample["qmlHealth"] == "—",
                    "New connection reused old values or exceeded recovery target")
            require(not sample["qmlActionFeedback"] and sample["qmlSeat"] == INFANTRY_LABEL,
                    "Seat or action feedback crossed the reconnect boundary incorrectly")
            await asyncio.to_thread(qt.perform, "shortcut", lambda s: s["qmlActionFeedback"] == INFANTRY_FEEDBACK,
                                    "actual F6 event rejects independently after reconnect")
            first = len(qt.samples)
            # No robot ID on Dynamic: identity from the first connection must
            # never authorize new HP. Game is an ordered independent barrier.
            await publish("RobotDynamicStatus", "08 bc 03")
            await publish("GameStatus", "30 2b")
            sample = await asyncio.to_thread(qt.wait, lambda s: s["gameCountdown"] == "43",
                                             "identity-free Game accepted on new connection")
            require(sample["topics"] == ["GameStatus"] and sample["qmlHealth"] == "—",
                    "New Dynamic was used before the new static identity")
            await publish("RobotStaticStatus", "20 67 28 03")
            await publish("RobotDynamicStatus", "08 bc 03")
            await publish("GameStatus", "30 2c")
            sample = await asyncio.to_thread(qt.wait, lambda s: s["gameCountdown"] == "44",
                                             "wrong robot ID ignored on recovered connection")
            require(sample["topics"] == ["GameStatus"] and "静态身份" in sample["error"],
                    "Recovered session accepted mismatching robot identity")
            await publish_five("08 c2 02")
            await asyncio.to_thread(qt.wait, lambda s: set(s["topics"]) == TOPICS
                                    and s["receivedRobotId"] == 3 and s["qmlHealth"] == "322"
                                    and not s["staleTopics"], "all five fresh topics after matching identity")
            require(all(s["health"] not in ("321", "444") and s["qmlHealth"] not in ("321", "444")
                        for s in qt.samples[first:]), "Old HP or unbound HP briefly appeared")

            await stop_broker()
            await wait_retry(qt, 500)  # success resets the backoff
            stopped = await asyncio.to_thread(qt.stop)
            require(not stopped["qmlActionFeedback"], "Stopping did not clear action feedback")
            await start_broker("after-stop")
            # Leave the listener up beyond the cancelled retry. Closing the
            # probe earlier could falsely credit process exit for cancellation.
            await asyncio.sleep(1.1)
            await asyncio.to_thread(qt.perform, "click-action", lambda s: not s["running"]
                                    and s["qmlActionFeedback"] == INFANTRY_FEEDBACK,
                                    "stopped infantry session still clearly explains refusal")
            qt.read_new()
            require(not qt.samples[-1]["running"] and not qt.samples[-1]["topics"],
                    "Stopped Qt session reactivated")
        require(not wire["after-stop"], "Stopped Qt session contacted the restored broker")
        await stop_broker()

        # Seat is an operator configuration independent of the connected robot.
        await start_broker("independent-id")
        with QtProbe(executable, evidence, "qt-infantry-id1", port, robot_id=1, seat="infantry") as qt:
            sample = await asyncio.to_thread(qt.wait, lambda s: s["subscriptionsReady"], "robot1 subscriptions")
            require(sample["qmlSeat"] == INFANTRY_LABEL and sample["actionAvailable"]
                    and sample["robotId"] == 1, "Non-infantry robot ID changed the configured operator seat")
            await asyncio.to_thread(qt.perform, "click-action", lambda s: s["qmlActionFeedback"] == INFANTRY_FEEDBACK,
                                    "infantry UI rejects for robot ID 1")
        await stop_broker()
        rows = wire["independent-id"]
        require([r["clientId"] for r in rows if r["kind"] == "connect"] == ["1"]
                and not any(r["kind"] == "client-publish" for r in rows),
                "Configured seat did not stay read-only with robot ID 1")

        # Exercise the normal application quit signal while the retry timer is
        # pending. No explicit stop or restart from the harness in this case.
        with QtProbe(executable, evidence, "qt-quit-during-retry", port) as qt:
            await wait_retry(qt, 500)
        for phase in ("before-loss", "after-loss"):
            require(all(row["clientId"] == "3" for row in wire[phase]), f"{phase}: unexpected client ID in capture")
            rows = wire[phase]
            connections = [row for row in rows if row["kind"] == "connect"]
            require(len(connections) == 1 and connections[0]["clientId"] == "3"
                    and connections[0]["cleanSession"], f"{phase}: expected one clean robot3 connection")
            subs = [row for row in rows if row["kind"] == "subscribe"]
            topics = [pair for row in subs for pair in row["topics"]]
            require(sorted(topics) == sorted((topic, 1) for topic in TOPICS),
                    f"{phase}: missing, duplicate or incorrect subscription")
            acks = [(row["id"], row["codes"]) for row in rows if row["kind"] == "suback"]
            require(sorted(acks) == sorted((row["id"], [1] * len(row["topics"])) for row in subs),
                    f"{phase}: subscriptions did not all receive the expected SUBACK")
            require({row["topic"] for row in rows if row["kind"] == "broker-publish"} == TOPICS,
                    f"{phase}: broker capture missing one of the five topics")
            require(not any(row["kind"] == "client-publish" for row in rows),
                    f"{phase}: read-only client sent a business PUBLISH")
        return [f"real AMQTT stop/restart: five resubscriptions in {recovery_ms} ms, "
                "all five fresh after new identity, QML HP 321 -> 323 unfocused -> missing -> 322",
                "one configured infantry Qt process: visible button/F6 refusal, key/mouse, focus transfer, stop and "
                "reconnect with zero client PUBLISH; explicit infantry seat also refused for robot ID 1",
                "bounded retries 500/1000/2000/4000/4000 ms; stop cancels, quit releases pending retry",
                "one clean robot3 CONNECT per live broker, five QoS1 subscriptions and ACKs per connection, "
                "zero client PUBLISH across recovery"]
    finally:
        await stop_broker()
        (evidence / "recovery-wire.json").write_text(
            json.dumps({"brokers": wire, "retries": retries}, indent=2), encoding="utf-8")


async def run(args, evidence):
    import uvicorn
    from amqtt.broker import Broker
    from simulator.server.app import create_app
    from simulator.server.main import build_parser
    from simulator.tools.smoke_test import check_stopped

    checks = []
    broker_packets = []
    broker = server = server_task = application = None
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    videos = tempfile.TemporaryDirectory(prefix="rm27-mqtt-check-videos-")
    try:
        broker = Broker({
            "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
            "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
                        f"{__name__}.RecoveryPacketLog": {}},
        })
        broker_packets = broker.plugins_manager.get_plugin("RecoveryPacketLog").packets
        await broker.start()
        port = broker._servers["default"].instance.sockets[0].getsockname()[1]
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        web_port = listener.getsockname()[1]
        service_args = build_parser().parse_args([
            "--web-host", "127.0.0.1", "--web-port", str(web_port),
            "--mqtt-host", "127.0.0.1", "--mqtt-port", str(port), "--current-robot-id", "3"])
        application = create_app(service_args)
        server = uvicorn.Server(uvicorn.Config(application, log_level="error", access_log=False))
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        deadline = time.monotonic() + 10
        while not server.started:
            if server_task.done():
                await server_task
                raise RuntimeError("Simulator exited during startup")
            require(time.monotonic() < deadline, "Simulator startup timed out")
            await asyncio.sleep(0.05)
        runtime = application.fastapi_app.state.simulator
        for component in (runtime.video_streamer, runtime.industrial_camera_streamer):
            component.video_resource_path = videos.name
            component.video_dir = videos.name
        checks += await asyncio.to_thread(exercise_console, args.client_check, evidence,
                                         f"http://127.0.0.1:{web_port}", port, args.cycles)
        await asyncio.to_thread(runtime.mqtt_publisher.stop)
        check_stopped(runtime.mqtt_publisher)
        checks += await asyncio.to_thread(exercise_injection, args.client_check, evidence, port)
    finally:
        try:
            if server is not None and server_task is not None:
                server.should_exit = True
                await asyncio.wait_for(server_task, timeout=15)
        finally:
            listener.close()
            try:
                if broker is not None:
                    await broker.shutdown()
            finally:
                videos.cleanup()
                (evidence / "console-broker-packets.json").write_text(json.dumps(broker_packets), encoding="utf-8")
    require(all(row["clientId"] for row in broker_packets), "Unattributed packets in broker capture")
    for client_id in ("3", "103"):
        packets = [row for row in broker_packets if row["clientId"] == client_id]
        require({row["topic"] for row in packets if row["kind"] == "broker-publish"} == TOPICS
                and any(row["kind"] == "client-puback" for row in packets)
                and not any(row["kind"] == "client-publish" for row in packets),
                f"Client {client_id}: expected five-topic receiving, PUBACK and zero business PUBLISH")
    require(TOPICS.issubset({row["topic"] for row in broker_packets if row["kind"] == "client-publish"
                             and row["clientId"] == f"rm27_simulator_{os.getpid()}"}),
            "Broker capture did not distinguish actual simulator publications from Qt connections")
    checks.append("simulator published all five topics; client IDs 3/103 received and acknowledged, "
                  "both sent zero business PUBLISH; blue infantry HP remained live while unfocused")
    runtime = application.fastapi_app.state.simulator
    for component in (runtime.state_manager, runtime.mqtt_publisher,
                      runtime.video_streamer, runtime.industrial_camera_streamer):
        check_stopped(component)
    require(runtime.video_streamer.sock.fileno() == -1, "Simulator video socket leaked")
    checks.append("normal simulator workers and sockets released")

    for mode in ("empty", "reject", "timeout", "delayed", "disconnect", "overflow", "abandoned"):
        fixture = FaultBroker(mode)
        fault_server = await asyncio.start_server(fixture.accept, "127.0.0.1", 0)
        port = fault_server.sockets[0].getsockname()[1]
        try:
            await asyncio.to_thread(exercise_fault, args.client_check, evidence, mode, port, fixture)
        finally:
            fault_server.close()
            await fault_server.wait_closed()
            await fixture.close()
            (evidence / f"fault-{mode}-wire.json").write_text(
                json.dumps(fixture.observed, indent=2), encoding="utf-8")
        require(not fixture.errors, f"Fault broker errors: {fixture.errors}")
        require(any(x.get("clientId") == "3" for x in fixture.observed),
                "MQTT client ID was not the decimal robot ID")
        if mode == "disconnect":
            require(sum(x["kind"] == "connect" for x in fixture.observed) == 2,
                    "Repeated connection loss did not create exactly one automatic replacement")
        if mode == "abandoned":
            require(fixture.accept_count == 2, "Expected exactly two connection attempts")
            for attempt, confirmed in ((1, 4), (2, 5)):
                rows = [row for row in fixture.observed if row["attempt"] == attempt]
                require([r["clientId"] for r in rows if r["kind"] == "connect"] == ["3"],
                        f"Attempt {attempt}: expected one robot 3 CONNECT")
                require(sorted(r["topic"] for r in rows if r["kind"] == "subscribe") == sorted(TOPICS),
                        f"Attempt {attempt}: expected five exact subscriptions")
                require([code for r in rows if r["kind"] == "suback" for code in r["codes"]] == [1] * confirmed,
                        f"Attempt {attempt}: expected {confirmed} QoS1 acknowledgments")
            require(sorted(row["packetId"] for row in fixture.observed if row["kind"] == "old-puback") == [1, 2],
                    "Old identity and HP were not both acknowledged before connection loss")
        if mode != "timeout":
            subscriptions = [x for x in fixture.observed if x["kind"] == "subscribe"]
            require({x["topic"] for x in subscriptions} == TOPICS,
                    "Client subscriptions were not exactly the five supported topics")
            require(all(x["qos"] <= 1 for x in subscriptions), "Subscription exceeded QoS 1")
        checks.append(f"wire fixture: {mode}")
    # Reserve a bound but non-listening port, avoiding races with another service.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as refused:
        refused.bind(("127.0.0.1", 0))
        await asyncio.to_thread(exercise_fault, args.client_check, evidence,
                                "refused", refused.getsockname()[1])
    checks.append("TCP connection refusal is visible")
    checks += await exercise_recovery(args.client_check, evidence)
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-check", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--cycles", type=int, default=100)
    args = parser.parse_args(argv)
    require(args.client_check.is_file(), f"Build the Qt MQTT check executable first: {args.client_check}")
    require(1 <= args.cycles <= 1000, "cycles must be 1..1000")
    evidence = args.evidence_dir or ROOT / "logs" / ("check-mqtt-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    evidence = evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(level=logging.ERROR)
    result = {"scope": "local AMQTT, simulator console and real Qt/QML; no official hardware or Mosquitto claim",
              "cycles": args.cycles, "passed": False, "checks": []}
    print(f"MQTT evidence: {evidence}", flush=True)
    try:
        with (evidence / "service.log").open("w", encoding="utf-8") as service_log:
            with contextlib.redirect_stdout(service_log), contextlib.redirect_stderr(service_log):
                result["checks"] = asyncio.run(run(args, evidence))
        result["passed"] = True
    except Exception as error:
        result["error"] = str(error)
        (evidence / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"MQTT check failed: {error}", file=sys.stderr)
    finally:
        (evidence / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if result["passed"]:
        print(f"MQTT checks passed ({len(result['checks'])} scenarios). Evidence: {evidence}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
