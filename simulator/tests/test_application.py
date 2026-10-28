"""Exercise port-specific assembly without changing upstream match semantics."""

import asyncio
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


async def request(app, method, path, body=b"", headers=(), peer="127.0.0.1"):
    messages = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "headers": list(headers),
        "server": ("127.0.0.1", 8000), "client": (peer, 12345),
    }, receive, send)
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    payload = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, payload


class ApplicationTest(unittest.IsolatedAsyncioTestCase):
    def create_app(self, *options):
        main = importlib.import_module("simulator.server.main")
        module = importlib.import_module("simulator.server.app")
        return module.create_app(main.build_parser().parse_args(list(options)))

    async def test_import_and_factory_do_not_start_network_or_workers(self):
        with (
            patch.object(socket.socket, "connect", side_effect=AssertionError("connect")),
            patch.object(socket.socket, "bind", side_effect=AssertionError("bind")),
            patch.object(threading.Thread, "start", side_effect=AssertionError("thread")),
        ):
            application = self.create_app()
        runtime = application.fastapi_app.state.simulator
        self.assertFalse(runtime.state_manager.running)
        self.assertIsNone(runtime.mqtt_publisher)
        self.assertIsNone(runtime.video_streamer)

    async def test_unavailable_broker_keeps_console_without_implicit_udp(self):
        application = self.create_app("--current-robot-id", "101")
        module = importlib.import_module("simulator.server.app")
        fastapi = application.fastapi_app
        before = set(asyncio.all_tasks())
        with patch.object(module.MQTTPublisher, "start", return_value=False):
            async with fastapi.router.lifespan_context(fastapi):
                status, payload = await request(application, "GET", "/api/health")
                health = json.loads(payload)
                self.assertEqual(200, status)
                self.assertEqual("rm26-compat", health["protocol"])
                self.assertEqual(101, health["currentRobotId"])
                self.assertFalse(health["mqttConnected"])
                self.assertFalse(health["transports"]["udpEnabled"])
                self.assertIsNone(fastapi.state.simulator.udp_sender)
                status, payload = await request(application, "GET", "/api/state")
                self.assertEqual(200, status)
                self.assertIn("gameStatus", json.loads(payload))
        runtime = fastapi.state.simulator
        for component in (runtime.state_manager, runtime.mqtt_publisher,
                          runtime.video_streamer, runtime.industrial_camera_streamer):
            self.assertFalse(component.running)
        self.assertEqual(-1, runtime.video_streamer.sock.fileno())
        self.assertEqual(before, set(asyncio.all_tasks()))

    async def test_upload_reaches_api_and_uses_configured_video_directory(self):
        application = self.create_app()
        status, _ = await request(application, "POST", "/upload")
        self.assertEqual(422, status)  # A root StaticFiles mount would return 405.
        module = importlib.import_module("simulator.server.app")
        fastapi = application.fastapi_app
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(module.MQTTPublisher, "start", return_value=False):
                async with fastapi.router.lifespan_context(fastapi):
                    runtime = fastapi.state.simulator
                    for component in (runtime.video_streamer, runtime.industrial_camera_streamer):
                        component.video_resource_path = directory
                        component.video_dir = directory
                    body = (b'--boundary\r\nContent-Disposition: form-data; name="file"; '
                            b'filename="..\\sample.mp4"\r\nContent-Type: video/mp4\r\n\r\n'
                            b'fixture\r\n--boundary--\r\n')
                    status, payload = await request(application, "POST", "/upload", body,
                        [(b"content-type", b"multipart/form-data; boundary=boundary")])
                    self.assertEqual(200, status)
                    self.assertNotIn("error", json.loads(payload))
                    self.assertEqual(b"fixture", (Path(directory) / "sample.mp4").read_bytes())

    async def test_shutdown_requires_local_peer_and_secret(self):
        application = self.create_app()
        callbacks = []
        application.fastapi_app.state.request_exit = lambda: callbacks.append(True)
        with patch.dict(os.environ, {"RM_SIM_SHUTDOWN_TOKEN": "test-token"}):
            for peer, token in (("127.0.0.1", b"wrong"), ("192.0.2.1", b"test-token")):
                status, _ = await request(application, "POST", "/api/shutdown",
                    headers=[(b"x-simulator-token", token)], peer=peer)
                self.assertEqual(403, status)
            status, _ = await request(application, "POST", "/api/shutdown",
                headers=[(b"x-simulator-token", b"test-token")])
            self.assertEqual(200, status)
            await asyncio.sleep(0)
        self.assertEqual([True], callbacks)

    async def test_partial_startup_failure_closes_allocated_resources(self):
        application = self.create_app("--enable-receiver")
        fastapi = application.fastapi_app
        module = importlib.import_module("simulator.server.app")
        with patch.object(module.UDPReceiver, "__init__", side_effect=OSError("occupied")):
            with self.assertRaisesRegex(OSError, "occupied"):
                async with fastapi.router.lifespan_context(fastapi):
                    self.fail("startup must fail")
        self.assertEqual(-1, fastapi.state.simulator.video_streamer.sock.fileno())
        self.assertFalse(fastapi.state.simulator.state_manager.running)


class EntrypointTest(unittest.TestCase):
    def test_fresh_import_does_not_parse_arguments_or_start_io(self):
        code = """
import argparse, socket, threading
from unittest.mock import patch
with patch.object(argparse.ArgumentParser, 'parse_args', side_effect=AssertionError('parse')), \\
     patch.object(socket.socket, 'connect', side_effect=AssertionError('connect')), \\
     patch.object(socket.socket, 'bind', side_effect=AssertionError('bind')), \\
     patch.object(threading.Thread, 'start', side_effect=AssertionError('thread')):
    import simulator.server.main
    import simulator.server.app
"""
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                cwd=Path(__file__).resolve().parents[2], timeout=15)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_occupied_web_port_is_not_reclaimed(self):
        with socket.socket() as owner:
            owner.bind(("127.0.0.1", 0))
            owner.listen()
            port = owner.getsockname()[1]
            result = subprocess.run([sys.executable, "-m", "simulator.server.main", "--web-port", str(port)],
                capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2], timeout=15)
            self.assertNotEqual(0, result.returncode)
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                client, _ = owner.accept()
                client.close()


if __name__ == "__main__":
    unittest.main()
