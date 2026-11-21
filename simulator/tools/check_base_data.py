"""Offline checks of the simulator's actual step-1 payloads and console events.

Run from the repository root: python -m simulator.tools.check_base_data
No Broker, Qt GUI or robot is required.
"""
from __future__ import annotations

import asyncio
from collections import Counter
import contextlib
import io
import time
import unittest
from unittest.mock import patch

from simulator.protocol import rm27_base_pb2 as pb
from simulator.server.mqtt_publisher import MQTTPublisher
from simulator.server.state_manager import StateManager


class BaseDataChecks(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.quiet = contextlib.redirect_stdout(self.output)
        self.quiet.__enter__()
        self.state = StateManager()
        self.publisher = MQTTPublisher(self.state)
        self.payloads = {}
        self.publisher._publish = lambda topic, payload, qos=1: self.payloads.update({topic: payload})

    def tearDown(self):
        self.quiet.__exit__(None, None, None)

    def decode(self, topic):
        return getattr(pb, topic).FromString(self.payloads[topic])

    def test_health_order_is_documented_eight_and_p002_is_six(self):
        for index, rid in enumerate(self.state.robot_ids):
            self.state.set_basic_robot_values(index, {"health": rid * 10, "bullets": -rid})
        self.publisher._publish_global_unit_status(self.state.get_state())
        message = self.decode("GlobalUnitStatus")
        self.assertEqual(list(message.robot_health), [10, 30, 40, 70, 1010, 1030, 1040, 1070])
        self.assertEqual(list(message.robot_bullets), [-1, 0, -3, -4, -6, -7])
        self.assertFalse(message.HasField("base_shield"))
        self.assertFalse(message.HasField("total_CP_ally"))
        self.publisher.current_robot_id = 101
        self.publisher._publish_global_unit_status(self.state.get_state())
        blue = self.decode("GlobalUnitStatus")
        self.assertEqual(list(blue.robot_health), [1010, 1030, 1040, 1070, 10, 30, 40, 70])
        self.assertEqual(list(blue.robot_bullets), [-101, 0, -103, -104, -106, -107])

    def test_r_b_outposts_do_not_swap_with_perspective(self):
        self.state.global_unit_status.update(red_outpost_health=123, blue_outpost_health=456)
        for rid in (1, 101):
            self.publisher.current_robot_id = rid
            self.publisher._publish_global_unit_status(self.state.get_state())
            message = self.decode("GlobalUnitStatus")
            self.assertEqual((message.outpost_R_health, message.outpost_B_health), (123, 456))

    def test_selected_robot_core_and_switches_share_authority(self):
        self.state.select_robot(104)
        self.state.set_basic_robot_values(self.state.robot_ids.index(104), {"health": 321, "heat": 12.5, "bullets": -8})
        self.state.set_robot_dynamic_status({"remaining_ammo": 4294967295})
        self.state.set_robot_static_status({"max_health": 800, "max_heat": 300})
        self.state.select_robot(1)
        self.state.select_robot(104)
        snapshot = self.state.get_state()
        self.publisher._publish_robot_static_status(snapshot)
        self.publisher._publish_robot_dynamic_status(snapshot)
        static, dynamic = self.decode("RobotStaticStatus"), self.decode("RobotDynamicStatus")
        self.assertEqual((static.robot_id, static.max_health, static.max_heat), (104, 800, 300))
        self.assertTrue(static.HasField("robot_type"))
        self.assertEqual(static.robot_type, 4)
        self.assertEqual((dynamic.current_health, dynamic.current_heat, dynamic.remaining_ammo), (321, 12.5, 4294967295))
        self.assertEqual(dynamic.reserved, 0)
        # Distinct signed cumulative and unsigned remaining fields stay distinct.
        self.assertEqual(snapshot["globalUnitStatus"]["robot_bullets"][self.state.robot_ids.index(104)], -8)

    def test_p003_defaults_switches_and_actual_field_five_for_all_twelve_robots(self):
        expected = ((1, 1), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7),
                    (101, 1), (103, 3), (104, 4), (105, 5), (106, 6), (107, 7))
        self.assertEqual(tuple(self.state.robot_ids), tuple(rid for rid, _ in expected))
        for rid, robot_type in expected:
            self.assertEqual(self.state.robot_static_by_id[rid]["robot_type"], robot_type)
            self.state.select_robot(rid)
            selected = self.state.get_robot_static_status()
            self.assertEqual((selected["robot_id"], selected["robot_type"]), (rid, robot_type))
            # The console's read-only type is included in its normal submission.
            self.state.set_robot_static_status({"robot_type": robot_type, "max_heat": 300 + robot_type})
            self.publisher._publish_robot_static_status(self.state.get_state())
            message = self.decode("RobotStaticStatus")
            self.assertTrue(message.HasField("robot_type"))
            self.assertEqual((message.robot_id, message.robot_type), (rid, robot_type))
            self.assertIn(bytes((0x28, robot_type)), self.payloads["RobotStaticStatus"])
        self.state.select_robot(1)
        before = self.state.get_robot_static_status()
        for bad in (None, "not-a-number", -1, 1.5, 4294967296, 0, 2, 7):
            with self.assertRaises(ValueError):
                self.state.set_robot_static_status({"robot_type": bad, "max_heat": 999})
            self.assertEqual(self.state.get_robot_static_status(), before)
        self.state.select_robot(101)
        self.assertEqual(self.state.get_robot_static_status()["robot_type"], 1)

    def test_signed_times_zero_presence_and_undefined_result(self):
        self.state.set_base_game_status({"current_stage": 4, "stage_countdown_sec": -2147483648,
                                         "stage_elapsed_sec": 2147483647, "is_paused": True})
        self.publisher._publish_game_status(self.state.get_state())
        message = self.decode("GameStatus")
        self.assertEqual((message.stage_countdown_sec, message.stage_elapsed_sec), (-2147483648, 2147483647))
        self.assertEqual(message.game_result, 255)
        with self.assertRaises(ValueError):
            self.state.set_base_game_status({"stage_countdown_sec": 2147483648})
        self.state.set_base_game_status({"current_stage": 5, "stage_countdown_sec": 0})
        self.publisher._publish_game_status(self.state.get_state())
        message = self.decode("GameStatus")
        self.assertTrue(message.HasField("stage_countdown_sec"))
        self.assertFalse(message.HasField("game_result"))

    def test_uint64_economy_survives_json_console_and_wire(self):
        maximum = "18446744073709551615"
        self.state.set_economy("red", 4294967295)
        self.state.set_logistics_protocol_state("red", total_economy_obtained=maximum)
        exported = self.state.get_state()["globalLogisticsStatus"]
        self.assertEqual(exported["red_total_economy_obtained"], maximum)
        self.publisher._publish_global_logistics_status(exported)
        self.assertEqual(self.decode("GlobalLogisticsStatus").total_economy_obtained, int(maximum))
        self.assertEqual(self.decode("GlobalLogisticsStatus").remaining_economy, 4294967295)
        with self.assertRaises(ValueError):
            self.state.set_logistics_protocol_state("red", total_economy_obtained="18446744073709551616")

    def test_basic_input_boundaries_do_not_use_legacy_hp_clamping(self):
        self.state.set_basic_robot_values(0, {"health": 4294967295, "bullets": -2147483648})
        exported = self.state.get_state()["globalUnitStatus"]
        self.assertEqual(exported["robot_health"][0], 4294967295)
        self.assertEqual(exported["robot_bullets"][0], -2147483648)
        for bad in ({"health": -1}, {"health": 1.5}, {"bullets": 2147483648}, {"heat": float("nan")}):
            with self.assertRaises(ValueError):
                self.state.set_basic_robot_values(0, bad)

    def test_status_and_logistics_validation_is_atomic_and_float32_bounded(self):
        before = self.state.get_state()
        for method, payload in (
            (self.state.set_robot_static_status, {"max_health": 777, "heat_cooldown_rate": 1e50}),
            (self.state.set_robot_static_status, {"level": 1.5}),
            (self.state.set_robot_static_status, {"max_health": 4294967296}),
            (self.state.set_robot_dynamic_status, {"current_health": 123, "current_heat": float("inf")}),
            (self.state.set_robot_dynamic_status, {"last_projectile_fire_rate": 1e50}),
            (self.state.set_robot_dynamic_status, {"remaining_ammo": -1}),
            (self.state.set_robot_dynamic_status, {"current_experience": 1.5}),
        ):
            with self.assertRaises(ValueError):
                method(payload)
            current = self.state.get_state()
            self.assertEqual(current["robotStaticStatus"], before["robotStaticStatus"])
            self.assertEqual(current["robotDynamicStatus"], before["robotDynamicStatus"])
        for bad in (1.5, -1, 4294967296):
            with self.assertRaises(ValueError):
                self.state.set_logistics_protocol_state("red", total_economy_obtained="123", tech_level=bad)
            with self.assertRaises(ValueError):
                self.state.set_logistics_protocol_state("red", encryption_level=bad)
        self.assertEqual(self.state.get_state()["globalLogisticsStatus"], before["globalLogisticsStatus"])
        # The largest finite float32 remains serializable after rejected values.
        maximum = 3.4028234663852886e38
        self.state.set_robot_dynamic_status({"current_heat": maximum})
        self.publisher._publish_robot_dynamic_status(self.state.get_state())
        self.assertEqual(self.decode("RobotDynamicStatus").current_heat, maximum)

    def test_periodic_workers_publish_only_six_migrated_topics(self):
        counts = Counter()
        self.publisher._publish = lambda topic, payload, qos=1: counts.update([topic])
        self.publisher.connect = lambda: setattr(self.publisher, "connected", True) or True
        self.publisher.disconnect = lambda: setattr(self.publisher, "connected", False)
        try:
            self.assertTrue(self.publisher.start())
            time.sleep(1.15)
        finally:
            self.publisher.stop()
        self.assertEqual(set(counts), {"GameStatus", "GlobalUnitStatus", "GlobalLogisticsStatus", "RobotStaticStatus", "RobotDynamicStatus", "RobotModuleStatus"})
        self.assertTrue(5 <= counts["GameStatus"] <= 8, counts)
        self.assertTrue(9 <= counts["RobotDynamicStatus"] <= 15, counts)
        self.assertTrue(1 <= counts["GlobalUnitStatus"] <= 3, counts)
        self.assertTrue(1 <= counts["RobotModuleStatus"] <= 3, counts)
        self.assertFalse(any(worker.is_alive() for worker in self.publisher._workers))


class ConsoleEventChecks(unittest.IsolatedAsyncioTestCase):
    async def test_basic_commands_and_invalid_input_ack(self):
        from simulator.server.app import create_app
        from simulator.server.main import build_parser
        with contextlib.redirect_stdout(io.StringIO()), patch.object(MQTTPublisher, "start", return_value=False):
            application = create_app(build_parser().parse_args([]))
            async with application.fastapi_app.router.lifespan_context(application.fastapi_app):
                command = application.engineio_server.handlers["/"]["referee_command"]
                result = await command("offline-test", {"command": "set_basic_robot_values", "robot_index": 0,
                                                         "health": 321, "heat": 12.5, "bullets": -7})
                self.assertTrue(result["ok"], result)
                result = await command("offline-test", {"command": "set_base_game_status", "current_stage": 4,
                                                         "stage_countdown_sec": -1, "stage_elapsed_sec": 20,
                                                         "is_paused": True})
                self.assertTrue(result["ok"], result)
                result = await command("offline-test", {"command": "set_base_game_status", "stage_elapsed_sec": 2147483648})
                self.assertFalse(result["ok"])
                result = await command("offline-test", {"command": "send_robot_dynamic_status",
                                                         "current_health": 1, "current_heat": 1e50})
                self.assertFalse(result["ok"])
                result = await command("offline-test", {"command": "send_robot_static_status",
                                                         "robot_type": 1, "max_heat": 300})
                self.assertTrue(result["ok"], result)
                result = await command("offline-test", {"command": "send_robot_static_status",
                                                         "robot_type": 7, "max_heat": 999})
                self.assertFalse(result["ok"])
                snapshot = application.fastapi_app.state.simulator.state_manager.get_state()
                self.assertEqual(snapshot["robotDynamicStatus"]["current_health"], 321)
                self.assertEqual(snapshot["robotDynamicStatus"]["current_heat"], 12.5)
                self.assertEqual(snapshot["gameStatus"]["stage_countdown_sec"], -1)
                self.assertEqual(snapshot["robotStaticStatus"]["robot_type"], 1)
                self.assertEqual(snapshot["robotStaticStatus"]["max_heat"], 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)
