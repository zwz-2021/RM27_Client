"""Real loopback HTTP/WebSocket/MQTT and UDP smoke checks.

Default: isolated AMQTT broker on a random local port (not Docker validation).
--mqtt-port 3333: reuse an explicitly supplied Mosquitto broker instead.
No Qt client, client build artifacts, fixed Web port, or real video is required.
Install optional test dependencies: python -m pip install -e "simulator[test]".
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time
import uuid


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_stopped(component):
    require(not component.running, f"Component still running: {type(component).__name__}")
    workers = list(getattr(component, "_workers", []))
    worker = getattr(component, "_worker", None)
    if worker is not None:
        workers.append(worker)
    require(all(not worker.is_alive() for worker in workers),
            f"Worker still alive: {type(component).__name__}")


def exercise_udp():
    """Receive actual RM26 simplified status and CRC-protected command frames."""
    from simulator.server import crc, protocol
    from simulator.server.state_manager import StateManager
    from simulator.server.udp_receiver import UDPReceiver
    from simulator.server.udp_sender import UDPSender

    state = StateManager()
    sender = receiver = None
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as capture:
        capture.bind(("127.0.0.1", 0))
        capture.settimeout(3)
        try:
            sender = UDPSender(state, host="127.0.0.1", port=capture.getsockname()[1])
            sender.start()
            frame, _ = capture.recvfrom(65535)
            cmd_id, length = struct.unpack("<HH", frame[:4])
            require(cmd_id == protocol.CmdID.GAME_STATUS, "Unexpected UDP status command")
            require(length == len(frame) - 4 and length > 0, "UDP status length mismatch")

            receiver = UDPReceiver(state, host="127.0.0.1", port=0)
            receiver.start()
            payload = struct.pack(protocol.ROBOT_CONTROL_FMT, 1, 3)
            header = bytearray(protocol.pack_header(len(payload), 0, protocol.CmdID.ROBOT_CONTROL))
            header[4] = crc.get_crc8_check_sum(header, 4, 0xff)
            command = header + payload
            crc.append_crc16_check_sum(command)
            capture.sendto(command, receiver.sock.getsockname())
            deadline = time.monotonic() + 3
            while not any(entry["source"] == "UDP" and "Type=1, ID=3" in entry["message"]
                          for entry in state.logs):
                require(time.monotonic() < deadline, "CRC-protected UDP command was not received")
                time.sleep(0.02)
        finally:
            for component in (receiver, sender):
                if component is not None:
                    component.stop()
    for component in (receiver, sender):
        check_stopped(component)
        require(component.sock.fileno() == -1, "UDP socket was not released")


def exercise_clients(base_url, mqtt_host, mqtt_port, video_directory):
    """Synchronous clients run outside the loop hosting the service and broker."""
    import paho.mqtt.client as mqtt
    import requests
    import socketio
    from simulator import robomaster_pb2 as pb

    session = requests.Session()
    session.trust_env = False
    console = socketio.Client(reconnection=False, request_timeout=3, http_session=session)
    peer = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                       client_id=f"rm27_smoke_{uuid.uuid4().hex}")
    subscribed = threading.Event()
    received = threading.Condition()
    latest, decode_errors = {}, []
    messages = {"GameStatus": pb.GameStatus, "GlobalUnitStatus": pb.GlobalUnitStatus,
                "RobotDynamicStatus": pb.RobotDynamicStatus,
                "RobotPerformanceSelectionSync": pb.RobotPerformanceSelectionSync}
    uploaded_file = None

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe([(topic, 1) for topic in messages])

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        if all(code < 128 for code in reason_codes):
            subscribed.set()

    def on_message(client, userdata, message):
        try:
            decoded = messages[message.topic].FromString(message.payload)
            with received:
                latest[message.topic] = decoded
                received.notify_all()
        except Exception as error:
            with received:
                decode_errors.append(str(error))
                received.notify_all()

    def wait_message(topic, predicate=lambda message: True):
        with received:
            ready = received.wait_for(
                lambda: decode_errors or (topic in latest and predicate(latest[topic])), timeout=5)
            require(not decode_errors, f"Protobuf decoding failed: {decode_errors}")
            require(ready, f"Expected MQTT payload did not arrive: {topic}")
            return latest[topic]

    def get_json(path):
        response = session.get(base_url + path, timeout=3)
        response.raise_for_status()
        return response.json()

    def wait_state(predicate, description):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = get_json("/api/state")
            if predicate(state):
                return state
            time.sleep(0.05)
        raise RuntimeError(f"State change did not arrive: {description}")

    peer.on_connect, peer.on_subscribe, peer.on_message = on_connect, on_subscribe, on_message
    try:
        for path in ("/", "/app.js", "/style.css", "/minimap_bg.png",
                     "/vendor/vue.min.js", "/vendor/socket.io.min.js"):
            response = session.get(base_url + path, timeout=3)
            require(response.status_code == 200 and response.content,
                    f"Web asset unavailable: {path} ({response.status_code})")
        deadline = time.monotonic() + 5
        while not get_json("/api/health")["mqttConnected"]:
            require(time.monotonic() < deadline, "Simulator did not connect to MQTT broker")
            time.sleep(0.05)
        peer.connect(mqtt_host, mqtt_port, keepalive=10)
        peer.loop_start()
        require(subscribed.wait(timeout=5), "MQTT subscriptions were not acknowledged")
        require(wait_message("GameStatus").total_rounds >= 1, "GameStatus has no round data")

        console.connect(base_url, transports=["websocket"], wait_timeout=5)
        console.call("referee_command", {"command": "set_hp", "robot_id": 0, "hp": 321}, timeout=5)
        wait_state(lambda state: state["globalUnitStatus"]["robot_health"][0] == 321,
                   "Web referee HP command")
        wait_message("GlobalUnitStatus", lambda message: bool(message.robot_health)
                     and message.robot_health[0] == 321)
        # The RM26 dynamic status panel is an independent manually sent test message.
        console.call("referee_command", {"command": "send_robot_dynamic_status", "current_health": 321}, timeout=5)
        wait_message("RobotDynamicStatus", lambda message: message.current_health == 321)

        selection = pb.RobotPerformanceSelectionCommand(shooter=2, chassis=3, sentry_control=1)
        delivery = peer.publish("RobotPerformanceSelectionCommand", selection.SerializeToString(), qos=1)
        delivery.wait_for_publish(timeout=5)
        require(delivery.is_published(), "MQTT upstream command was not acknowledged")
        expected_selection = {"shooter": 2, "chassis": 3, "sentry_control": 1}
        wait_state(lambda state: state["robotPerformanceSelectionSync"] == expected_selection,
                   "MQTT upstream performance selection")
        wait_message("RobotPerformanceSelectionSync", lambda message:
                     (message.shooter, message.chassis, message.sentry_control) == (2, 3, 1))
        for action, expected in (("start", "running"), ("pause", "paused"),
                                 ("resume", "running"), ("stop", "stopped")):
            result = console.call("simulation_control", {"action": action, "mode": "quick"}, timeout=5)
            require(isinstance(result, dict) and result.get("status") == expected,
                    f"Unexpected simulation acknowledgement for {action}: {result}")

        name = f"smoke-{uuid.uuid4().hex}.mp4"
        uploaded_file = Path(video_directory) / name
        require(not uploaded_file.exists(), "Unique upload filename already exists")
        sample = b"RM27 simulator upload route smoke test\n"
        response = session.post(base_url + "/upload", files={"file": (name, sample, "video/mp4")}, timeout=5)
        response.raise_for_status()
        require("error" not in response.json(), f"Upload failed: {response.text}")
        require(uploaded_file.is_file() and uploaded_file.read_bytes() == sample,
                "Upload was not saved inside the isolated video directory")
        require(name in get_json("/api/state")["videos"], "Uploaded video is not listed")
    finally:
        try:
            if console.connected:
                console.disconnect()
        finally:
            try:
                peer.disconnect()
                peer.loop_stop()
            finally:
                session.close()
                if uploaded_file is not None:
                    uploaded_file.unlink(missing_ok=True)


async def run_smoke(mqtt_host="127.0.0.1", mqtt_port=None):
    import uvicorn
    from simulator.server.app import create_app
    from simulator.server.main import build_parser

    broker = None
    server = server_task = application = None
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    videos = tempfile.TemporaryDirectory(prefix="rm27-smoke-videos-")
    try:
        if mqtt_port is None:
            from amqtt.broker import Broker
            broker = Broker({
                "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
                "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}},
            })
            await broker.start()
            mqtt_port = broker._servers["default"].instance.sockets[0].getsockname()[1]
            mqtt_host = "127.0.0.1"
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        web_port = listener.getsockname()[1]
        args = build_parser().parse_args([
            "--web-host", "127.0.0.1", "--web-port", str(web_port),
            "--mqtt-host", mqtt_host, "--mqtt-port", str(mqtt_port), "--current-robot-id", "1",
        ])
        application = create_app(args)
        server = uvicorn.Server(uvicorn.Config(application, log_level="error", access_log=False))
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        deadline = asyncio.get_running_loop().time() + 10
        while not server.started:
            if server_task.done():
                await server_task
                raise RuntimeError("Web server stopped before startup completed")
            require(asyncio.get_running_loop().time() < deadline, "Web startup timed out")
            await asyncio.sleep(0.05)
        runtime = application.fastapi_app.state.simulator
        for component in (runtime.video_streamer, runtime.industrial_camera_streamer):
            component.video_resource_path = videos.name
            component.video_dir = videos.name
        await asyncio.to_thread(exercise_clients, f"http://127.0.0.1:{web_port}",
                                mqtt_host, mqtt_port, videos.name)
    finally:
        try:
            if server is not None and server_task is not None:
                server.should_exit = True
                await asyncio.wait_for(server_task, timeout=15)
        finally:
            try:
                listener.close()
                if broker is not None:
                    await broker.shutdown()
            finally:
                videos.cleanup()
    runtime = application.fastapi_app.state.simulator
    for component in (runtime.state_manager, runtime.mqtt_publisher,
                      runtime.video_streamer, runtime.industrial_camera_streamer):
        check_stopped(component)
    require(runtime.video_streamer.sock.fileno() == -1, "Video socket was not closed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, help="reuse an explicit external broker (e.g. 3333)")
    parser.add_argument("--udp-only", action="store_true", help="run standard-library UDP checks only")
    args = parser.parse_args(argv)
    if not args.udp_only:
        try:
            modules = ["requests", "websocket", "socketio", "paho.mqtt.client"]
            if args.mqtt_port is None:
                modules.append("amqtt.broker")
            for module in modules:
                importlib.import_module(module)
        except ImportError as error:
            print(f"Smoke dependency missing: {error}", file=sys.stderr)
            print('Install: python -m pip install -e "simulator[test]"', file=sys.stderr)
            return 1
    logging.basicConfig(level=logging.ERROR)
    try:
        exercise_udp()
        if not args.udp_only:
            asyncio.run(run_smoke(args.mqtt_host, args.mqtt_port))
    except Exception as error:
        print(f"Simulator smoke check failed: {error}", file=sys.stderr)
        return 1
    broker_mode = "external broker" if args.mqtt_port is not None else "isolated AMQTT (not Docker verification)"
    print("UDP smoke check passed." if args.udp_only else
          f"Simulator smoke passed: HTTP, WebSocket, MQTT/Protobuf both ways ({broker_mode}), UDP, controls, upload, shutdown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
