"""Verify the moved simulator releases only its own workers and I/O resources."""

import socket
import subprocess
import sys
import threading
import unittest
from unittest.mock import Mock, patch

from simulator.server.industrial_camera_streamer import IndustrialCameraStreamer
from simulator.server.mqtt_publisher import MQTTPublisher
from simulator.server.state_manager import StateManager
from simulator.server.udp_receiver import UDPReceiver
from simulator.server.udp_sender import UDPSender
from simulator.server.video_streamer import VideoStreamer


class LifecycleTest(unittest.TestCase):
    def test_state_clock_stops_and_start_is_idempotent(self):
        state = StateManager()
        try:
            state.start()
            original_worker = state._worker
            state.start()
            self.assertIs(original_worker, state._worker)
        finally:
            state.stop()
        self.assertFalse(original_worker.is_alive())

    def test_udp_receiver_stop_unblocks_read_and_closes_socket(self):
        receiver = UDPReceiver(StateManager(), host="127.0.0.1", port=0)
        try:
            receiver.start()
        finally:
            receiver.stop()
        self.assertFalse(receiver._worker.is_alive())
        self.assertEqual(-1, receiver.sock.fileno())

    def test_udp_sender_stop_releases_worker_and_socket(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as destination:
            destination.bind(("127.0.0.1", 0))
            destination.settimeout(2)
            sender = UDPSender(StateManager(), host="127.0.0.1", port=destination.getsockname()[1])
            try:
                sender.start()
                packet, _ = destination.recvfrom(8192)
                self.assertGreater(len(packet), 4)
            finally:
                sender.stop()
        self.assertFalse(sender._worker.is_alive())
        self.assertEqual(-1, sender.sock.fileno())

    def test_failed_udp_bind_closes_the_allocated_socket(self):
        allocated = Mock()
        allocated.bind.side_effect = OSError("occupied")
        with patch("simulator.server.udp_receiver.socket.socket", return_value=allocated):
            with self.assertRaisesRegex(OSError, "occupied"):
                UDPReceiver(StateManager())
        allocated.close.assert_called_once()

    def test_mqtt_stop_handles_publish_workers_and_unconnected_client(self):
        publisher = MQTTPublisher(StateManager())
        publisher.client = Mock()
        with patch.object(publisher, "connect", return_value=True):
            try:
                self.assertTrue(publisher.start())
            finally:
                publisher.stop()
        self.assertTrue(all(not worker.is_alive() for worker in publisher._workers))
        publisher.client.disconnect.assert_called_once()
        publisher.client.loop_stop.assert_called_once()
        never_started = MQTTPublisher(StateManager())
        never_started.stop()
        self.assertFalse(never_started.running)

    def _exercise_blocked_video(self, component, probe=False):
        created = threading.Event()
        spawned = []
        real_popen = subprocess.Popen

        def start_blocked_process(*args, **kwargs):
            process = real_popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            spawned.append(process)
            created.set()
            return process

        component.current_video = "test-source.mp4"
        component.is_streaming = True
        if isinstance(component, IndustrialCameraStreamer) and not probe:
            component._chosen_encoder = ("libx264", [])
        try:
            with patch("subprocess.Popen", start_blocked_process):
                component.start()
                self.assertTrue(created.wait(timeout=3), "Worker did not reach FFmpeg/probe")
                component.stop()
            self.assertFalse(component._worker.is_alive())
            self.assertTrue(spawned)
            self.assertTrue(all(process.poll() is not None for process in spawned))
            self.assertTrue(all(process.stdout.closed for process in spawned))
        finally:
            component.stop()
            for process in spawned:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)
                if process.stdout:
                    process.stdout.close()

    def test_hevc_stop_interrupts_blocked_encoder_read(self):
        component = VideoStreamer()
        self._exercise_blocked_video(component)
        self.assertEqual(-1, component.sock.fileno())

    def test_industrial_camera_stop_interrupts_blocked_encoder_read(self):
        self._exercise_blocked_video(IndustrialCameraStreamer(mqtt_publisher=None))

    def test_industrial_camera_stop_interrupts_encoder_probe(self):
        self._exercise_blocked_video(IndustrialCameraStreamer(mqtt_publisher=None), probe=True)
