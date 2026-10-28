"""Independent entry point for the preserved RM26 referee simulator."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import sys
import uuid


def port(value):
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("port must be in 1..65535")
    return number


def robot_id(value):
    number = int(value)
    if number not in (*range(1, 8), *range(101, 108)):
        raise argparse.ArgumentTypeError("robot ID must be 1..7 or 101..107")
    return number


def probe_mqtt(host, mqtt_port, timeout=2):
    """Require an accepted MQTT 3.1.1 CONNECT, rather than just an open TCP port."""
    client_id = ("rm27_probe_" + uuid.uuid4().hex[:12]).encode("ascii")
    body = b"\x00\x04MQTT\x04\x02\x00\x0a" + struct.pack("!H", len(client_id)) + client_id
    packet = b"\x10" + bytes([len(body)]) + body
    try:
        with socket.create_connection((host, int(mqtt_port)), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(packet)
            response = b""
            while len(response) < 4:
                chunk = connection.recv(4 - len(response))
                if not chunk:
                    return False
                response += chunk
            accepted = response == b"\x20\x02\x00\x00"
            if accepted:
                connection.sendall(b"\xe0\x00")
            return accepted
    except (OSError, ValueError):
        return False


def build_parser():
    parser = argparse.ArgumentParser(description="RM26 referee simulator for RM27 development (2026 compatibility)")
    parser.add_argument("--check", action="store_true", help="check Python dependencies and simulator assets without starting I/O")
    parser.add_argument("--probe-mqtt", nargs=2, metavar=("HOST", "PORT"), help="probe an existing broker using MQTT CONNECT and exit")
    parser.add_argument("--target-ip", default=os.getenv("RM_SIM_TARGET_IP", "127.0.0.1"))
    parser.add_argument("--mqtt-host", default=os.getenv("RM_SIM_MQTT_HOST", "127.0.0.1"))
    parser.add_argument("--mqtt-port", type=port, default=os.getenv("RM_SIM_MQTT_PORT", "3333"))
    parser.add_argument("--web-host", default=os.getenv("RM_SIM_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--web-port", type=port, default=os.getenv("RM_SIM_WEB_PORT", "8000"))
    parser.add_argument("--current-robot-id", type=robot_id, default=os.getenv("RM_SIM_CURRENT_ROBOT_ID", "1"))
    parser.add_argument("--enable-receiver", action="store_true", help="receive CRC-framed legacy UDP commands on 3333")
    parser.add_argument("--enable-udp-sender", action="store_true", help="also send legacy UDP status frames to target-ip:3333")
    return parser


def check_environment():
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required")
    for name in ("fastapi", "socketio", "uvicorn", "multipart", "cv2", "numpy",
                 "paho.mqtt.client", "simulator.robomaster_pb2", "simulator.server.app"):
        importlib.import_module(name)
    root = Path(__file__).resolve().parents[1]
    for relative in ("protocol/robomaster.proto", "server/config.json", "tools/video_sender.py",
                     "server/static/index.html", "server/static/app.js", "server/static/style.css",
                     "server/static/minimap_bg.png", "server/static/map_geometry.js",
                     "server/static/vendor/vue.min.js", "server/static/vendor/socket.io.min.js"):
        if not (root / relative).is_file():
            raise RuntimeError(f"Missing simulator asset: {relative}")
    json.loads((root / "server/config.json").read_text(encoding="utf-8"))


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.probe_mqtt:
        accepted = probe_mqtt(*args.probe_mqtt)
        print("MQTT CONNECT accepted" if accepted else "MQTT CONNECT failed")
        return 0 if accepted else 1
    try:
        check_environment()
        if args.check:
            print("Simulator dependency and asset check passed; no listeners or workers started.")
            print(f"FFmpeg: {shutil.which('ffmpeg') or 'not found (required for video)'}")
            print(f"Docker: {shutil.which('docker') or 'not found (required for Compose Broker deployment)'}")
            return 0
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((args.web_host, args.web_port))
        import uvicorn
        from .app import create_app
        application = create_app(args)
        server = uvicorn.Server(uvicorn.Config(application, host=args.web_host, port=args.web_port))
        application.fastapi_app.state.request_exit = lambda: setattr(server, "should_exit", True)
        print(f"Web: http://{args.web_host}:{args.web_port}; MQTT: {args.mqtt_host}:{args.mqtt_port}")
        print("2026 compatibility protocol; the current Qt client does not yet receive external match data.")
        server.run()
        return 0
    except (ImportError, RuntimeError, OSError, ValueError) as error:
        print(f"Simulator failed: {error}", file=sys.stderr)
        if isinstance(error, ImportError):
            print("Install: powershell -ExecutionPolicy Bypass -File simulator/scripts/start.ps1 -Install", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
