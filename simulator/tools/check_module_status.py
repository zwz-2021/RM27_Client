r"""Independent RobotModuleStatus bytes, console input and periodic lifecycle checks.

Run: .\simulator\.venv\Scripts\python.exe -m simulator.tools.check_module_status
The fixed communication PDF 63–64 defines scalar fields 1..11; armor is one
scalar, and field 11 is an installation permission, never a laser switch.
"""
from __future__ import annotations

import contextlib
import io
import time
import unittest
from unittest.mock import patch

from simulator.protocol import rm27_base_pb2 as pb
from simulator.server.mqtt_publisher import MQTTPublisher
from simulator.server.state_manager import StateManager


FIELDS = (
    "power_manager", "rfid", "light_strip", "small_shooter", "big_shooter",
    "uwb", "armor", "video_transmission", "capacitor", "main_controller",
    "modular_42mm",
)


class ModuleStatusChecks(unittest.TestCase):
    def setUp(self):
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.state = StateManager()
        self.publisher = MQTTPublisher(self.state)
        self.packets = []
        self.publisher.connected = True

        class CaptureClient:
            def publish(client, topic, payload, qos):
                self.packets.append((topic, payload, qos, time.monotonic()))

        self.publisher.client = CaptureClient()

    def tearDown(self):
        self.quiet.__exit__(None, None, None)

    def publish(self):
        self.publisher.publish_robot_module_status(self.state.get_state())
        topic, payload, qos, _ = self.packets[-1]
        self.assertEqual((topic, qos), ("RobotModuleStatus", 1))
        return payload

    def test_official_tags_values_and_zero_presence_from_actual_publish_path(self):
        # Literal independently authored Protobuf varints; no project serializer
        # constructs the expected bytes. Field 7 is ONE armor scalar, value 2.
        values = (0, 1, 2, 0, 1, 2, 2, 0, 1, 2, 1)
        self.state.set_robot_module_status(dict(zip(FIELDS, values)))
        expected = bytes.fromhex("08 00 10 01 18 02 20 00 28 01 30 02 38 02 40 00 48 01 50 02 58 01")
        self.assertEqual(self.publish(), expected)
        message = pb.RobotModuleStatus.FromString(expected)
        self.assertEqual(tuple(getattr(message, field) for field in FIELDS), values)
        self.assertTrue(all(message.HasField(field) for field in FIELDS))
        self.assertEqual(len(message.DESCRIPTOR.fields), 11)
        self.assertEqual(message.DESCRIPTOR.fields_by_name["armor"].number, 7)
        self.assertFalse(message.DESCRIPTOR.fields_by_name["armor"].is_repeated)
        self.assertNotIn("laser_detection_module", message.DESCRIPTOR.fields_by_name)

    def test_every_status_value_and_permission_value(self):
        for number, field in enumerate(FIELDS, 1):
            for value in range(2 if field == "modular_42mm" else 3):
                self.state.set_robot_module_status({field: value})
                self.assertEqual(self.publish(), bytes((number << 3, value)))

    def test_missing_is_omitted_and_replacing_fixture_clears_old_fields(self):
        self.assertEqual(self.publish(), b"")
        self.state.set_robot_module_status({"armor": 2, "modular_42mm": 0})
        self.assertEqual(self.publish(), bytes.fromhex("38 02 58 00"))
        self.state.set_robot_module_status({"power_manager": 0, "armor": None})
        self.assertEqual(self.publish(), bytes.fromhex("08 00"))
        self.state.set_robot_module_status({})
        self.assertEqual(self.publish(), b"")

    def test_bad_values_rejected_atomically_and_no_clamping(self):
        self.state.set_robot_module_status({"armor": 1})
        before = self.state.get_robot_module_status()
        for field in FIELDS:
            for value in (-1, 3, 1.5, True, "garbage", [], {}, 4294967296):
                with self.assertRaises((TypeError, ValueError)):
                    self.state.set_robot_module_status({"power_manager": 2, field: value})
                self.assertEqual(self.state.get_robot_module_status(), before)
        for bad in ({"modular_42mm": 2}, {"laser_detection_module": 1}, {"armor": [0, 1, 2, 1]}):
            with self.assertRaises(ValueError):
                self.state.set_robot_module_status(bad)
            self.assertEqual(self.state.get_robot_module_status(), before)
        with self.assertRaises(ValueError):
            self.state.set_robot_module_publishing(0)
        self.assertTrue(self.state.get_state()["robotModulePublishing"])

    def test_robot_switch_preserves_separate_fixtures_and_rejects_old_draft(self):
        self.state.select_robot(3)
        self.state.set_robot_module_status({"armor": 2, "expected_robot_id": 3})
        old = self.state.get_state()
        self.state.select_robot(101)
        self.assertEqual(self.publish(), b"")
        with self.assertRaises(ValueError):
            self.state.set_robot_module_status({"armor": 0, "expected_robot_id": 3})
        self.state.set_robot_module_status({"modular_42mm": 1, "expected_robot_id": 101})
        self.assertEqual(self.publish(), bytes.fromhex("58 01"))
        self.state.select_robot(3)
        self.assertEqual(self.publish(), bytes.fromhex("38 02"))
        self.state.set_robot_module_status({"armor": 0})
        self.assertEqual(old["robotModuleStatus"]["armor"], 2)

    def test_publish_boundary_refuses_corrupt_state(self):
        for field, value in (("modular_42mm", 2), ("armor", 3), ("rfid", True)):
            with self.assertRaises(ValueError):
                self.publisher.publish_robot_module_status({"robotModuleStatus": {field: value}})
        self.assertEqual(self.packets, [])

    def test_periodic_one_hz_topic_can_pause_resume_and_stop(self):
        self.publisher.connect = lambda: True
        self.publisher.disconnect = lambda: None
        try:
            self.assertTrue(self.publisher.start())
            deadline = time.monotonic() + 4
            while sum(packet[0] == "RobotModuleStatus" for packet in self.packets) < 3:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.02)
            module = [packet for packet in self.packets if packet[0] == "RobotModuleStatus"]
            self.assertTrue(all(0.98 <= b[3] - a[3] <= 1.5 for a, b in zip(module, module[1:])), module)
            self.state.set_robot_module_publishing(False)
            time.sleep(0.1)  # Let a previously sampled snapshot finish.
            count = sum(packet[0] == "RobotModuleStatus" for packet in self.packets)
            dynamic_count = sum(packet[0] == "RobotDynamicStatus" for packet in self.packets)
            time.sleep(1.2)
            self.assertEqual(sum(packet[0] == "RobotModuleStatus" for packet in self.packets), count)
            self.assertGreater(sum(packet[0] == "RobotDynamicStatus" for packet in self.packets), dynamic_count)
            self.state.set_robot_module_publishing(True)
            deadline = time.monotonic() + 2
            while sum(packet[0] == "RobotModuleStatus" for packet in self.packets) == count:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.02)
        finally:
            self.publisher.stop()
        self.assertFalse(any(worker.is_alive() for worker in self.publisher._workers))
        count = len(self.packets)
        time.sleep(0.12)
        self.assertEqual(len(self.packets), count)


class ModuleConsoleChecks(unittest.IsolatedAsyncioTestCase):
    async def test_save_ack_errors_pause_and_no_immediate_extra_publish(self):
        from simulator.server.app import create_app
        from simulator.server.main import build_parser
        with contextlib.redirect_stdout(io.StringIO()), patch.object(MQTTPublisher, "start", return_value=False):
            application = create_app(build_parser().parse_args([]))
            async with application.fastapi_app.router.lifespan_context(application.fastapi_app):
                command = application.engineio_server.handlers["/"]["referee_command"]
                with patch.object(MQTTPublisher, "publish_robot_module_status") as publish:
                    for _ in range(3):
                        result = await command("offline-test", {"command": "send_robot_module_status", "armor": 2, "modular_42mm": 1})
                        self.assertTrue(result["ok"], result)
                    publish.assert_not_called()
                for bad in ({"modular_42mm": 2}, {"armor": [0, 1, 2, 1]}, {"laser_detection_module": 1}):
                    result = await command("offline-test", {"command": "send_robot_module_status", **bad})
                    self.assertFalse(result["ok"], result)
                    self.assertTrue(result["error"])
                for enabled in (False, True):
                    result = await command("offline-test", {"command": "set_robot_module_publishing", "enabled": enabled})
                    self.assertTrue(result["ok"], result)
                result = await command("offline-test", {"command": "set_robot_module_publishing", "enabled": "false"})
                self.assertFalse(result["ok"], result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
