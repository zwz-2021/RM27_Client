"""Step-1 offline contract and Python/C++ interoperability checks; no broker."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from simulator.protocol import rm27_base_pb2 as pb

# Independently transcribed from fixed local PDF chapter 2, not read from .proto.
# A shared wrong schema must not make interoperability look correct.
CONTRACT = {
    "GameStatus": [
        ("current_round", 1, "uint32"), ("total_rounds", 2, "uint32"),
        ("red_score", 3, "uint32"), ("blue_score", 4, "uint32"),
        ("current_stage", 5, "uint32"), ("stage_countdown_sec", 6, "int32"),
        ("stage_elapsed_sec", 7, "int32"), ("is_paused", 8, "bool"),
        ("game_result", 9, "uint32"), ("end_reason", 10, "uint32"),
    ],
    "GlobalUnitStatus": [
        ("base_health", 1, "uint32"), ("base_status", 2, "uint32"),
        ("base_shield", 3, "uint32"), ("outpost_R_health", 4, "uint32"),
        ("outpost_R_status", 5, "uint32"), ("enemy_base_health", 6, "uint32"),
        ("enemy_base_status", 7, "uint32"), ("enemy_base_shield", 8, "uint32"),
        ("outpost_B_health", 9, "uint32"), ("outpost_B_status", 10, "uint32"),
        ("robot_health", 11, "repeated uint32"), ("robot_bullets", 12, "repeated int32"),
        ("total_damage_ally", 13, "uint32"), ("total_damage_enemy", 14, "uint32"),
        ("total_CP_ally", 15, "uint32"), ("total_CP_enemy", 16, "uint32"),
    ],
    "GlobalLogisticsStatus": [
        ("remaining_economy", 1, "uint32"), ("total_economy_obtained", 2, "uint64"),
        ("tech_level", 3, "uint32"), ("encryption_level", 4, "uint32"),
    ],
    "RobotStaticStatus": [
        ("connection_state", 1, "uint32"), ("field_state", 2, "uint32"),
        ("alive_state", 3, "uint32"), ("robot_id", 4, "uint32"),
        ("robot_type", 5, "uint32"), ("performance_system_shooter", 6, "uint32"),
        ("performance_system_chassis", 7, "uint32"), ("level", 8, "uint32"),
        ("max_health", 9, "uint32"), ("max_heat", 10, "uint32"),
        ("heat_cooldown_rate", 11, "float"), ("max_power", 12, "uint32"),
        ("max_buffer_energy", 13, "uint32"), ("max_chassis_energy", 14, "uint32"),
    ],
    "RobotDynamicStatus": [
        ("current_health", 1, "uint32"), ("current_heat", 2, "float"),
        ("last_projectile_fire_rate", 3, "float"), ("reserved", 4, "uint32"),
        ("current_buffer_energy", 5, "uint32"), ("current_experience", 6, "uint32"),
        ("experience_for_upgrade", 7, "uint32"), ("total_projectiles_fired", 8, "uint32"),
        ("remaining_ammo", 9, "uint32"), ("is_out_of_combat", 10, "bool"),
        ("out_of_combat_countdown", 11, "uint32"), ("can_remote_heal", 12, "bool"),
        ("can_remote_ammo", 13, "bool"),
    ],
}


def require(condition, description):
    if not condition:
        raise AssertionError(description)


def inspect(executable, topic, path, *, with_role=False):
    result = subprocess.run([str(executable), "--decode-role" if with_role else "--decode", topic, str(path)],
                            check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-check", type=Path, required=True)
    args = parser.parse_args()
    executable = args.client_check.resolve(strict=True)
    types = {"uint32": 13, "uint64": 4, "int32": 5, "float": 2, "bool": 8}
    with tempfile.TemporaryDirectory(prefix="rm27-basic-data-") as temp:
        directory = Path(temp)
        for topic, contract in CONTRACT.items():
            message = getattr(pb, topic)()
            fields = message.DESCRIPTOR.fields_by_name
            require(set(fields) == {item[0] for item in contract}, f"{topic}: field names")
            expected = {}
            for name, number, datatype in contract:
                field = fields[name]
                repeated = datatype.startswith("repeated ")
                require(field.number == number and field.type == types[datatype.split()[-1]],
                        f"{topic}.{name}: field number/type")
                require(field.is_repeated == repeated and field.has_presence != repeated,
                        f"{topic}.{name}: optional/repeated presence")
                if repeated:
                    value = list(range(321, 329)) if name == "robot_health" else [-1, 0, 33, 44, 66, 77]
                    getattr(message, name).extend(value)
                else:
                    value = {"uint32": 4294967295, "uint64": 18446744073709551615,
                             "int32": -2147483648, "float": 12.5, "bool": False}[datatype]
                    setattr(message, name, value)
                expected[name] = str(value) if datatype == "uint64" else value
            path = directory / f"python-{topic}.bin"
            path.write_bytes(message.SerializeToString())
            require(inspect(executable, topic, path) == expected, f"{topic}: Python -> C++ all fields")
            message.Clear()
            path.write_bytes(message.SerializeToString())
            empty_expected = {"robot_health": [], "robot_bullets": []} if topic == "GlobalUnitStatus" else {}
            require(inspect(executable, topic, path) == empty_expected, f"{topic}: missing remains missing")
            # Explicit 0/false must survive for every optional field.
            for name, _, datatype in contract:
                if datatype.startswith("repeated "):
                    continue
                setattr(message, name, False if datatype == "bool" else 0)
                empty_expected[name] = "0" if datatype == "uint64" else (False if datatype == "bool" else 0)
            path.write_bytes(message.SerializeToString())
            require(inspect(executable, topic, path) == empty_expected, f"{topic}: explicit zero presence")

        subprocess.run([str(executable), "--emit-fixtures", str(directory)], check=True)
        cpp_expected = {
            "GameStatus": {"current_stage": 4, "stage_countdown_sec": -1, "is_paused": False,
                           "game_result": 255, "end_reason": 255},
            "GlobalUnitStatus": {"robot_health": list(range(321, 329)),
                                 "robot_bullets": [-1, 0, 333, 334, 336, 337],
                                 "outpost_R_health": 123, "outpost_B_health": 456,
                                 "total_CP_ally": 12, "total_CP_enemy": 34},
            "GlobalLogisticsStatus": {"remaining_economy": 0, "total_economy_obtained": 18446744073709551615},
            "RobotStaticStatus": {"robot_id": 103, "robot_type": 3, "max_health": 600, "max_heat": 240, "heat_cooldown_rate": 12.5},
            "RobotDynamicStatus": {"current_health": 321, "current_heat": 12.5,
                                   "remaining_ammo": 4294967295, "reserved": 0},
        }
        for topic, expected in cpp_expected.items():
            message = getattr(pb, topic)()
            message.ParseFromString((directory / f"{topic}.bin").read_bytes())
            actual = {field.name: list(value) if field.is_repeated else value
                      for field, value in message.ListFields()}
            require(actual == expected, f"{topic}: C++ -> Python fixtures")

        # P-003 semantic fixtures use the user-designated RM26 convention,
        # adapted using the 2027 appendix. This is not RobotStatus.type's enum.
        roles = {1: "重装", 2: "保留", 3: "步兵", 4: "步兵", 5: "步兵",
                 6: "空中", 7: "哨兵", 8: "飞镖", 9: "雷达"}
        path = directory / "static-role.bin"
        for type_number, name in roles.items():
            message = pb.RobotStaticStatus(robot_type=type_number)
            path.write_bytes(message.SerializeToString())
            decoded = inspect(executable, "RobotStaticStatus", path, with_role=True)
            require(decoded == {"robot_type": type_number, "role": name}, "type fallback cannot invent identity")
            for offset in (0, 100):
                message.robot_id = offset + type_number
                message.robot_type = 900
                path.write_bytes(message.SerializeToString())
                decoded = inspect(executable, "RobotStaticStatus", path, with_role=True)
                require(decoded["robot_id"] == offset + type_number and decoded["role"] == name
                        and decoded["robot_type"] == 900, "known red/blue ID wins without rewriting raw type")
        for value in (0, 10, 11, 900, 4294967295):
            message = pb.RobotStaticStatus(robot_type=value)
            path.write_bytes(message.SerializeToString())
            require(inspect(executable, "RobotStaticStatus", path, with_role=True)
                    == {"robot_type": value, "role": "未知"}, "unknown static type remains raw and unknown")
        path.write_bytes(pb.RobotStaticStatus().SerializeToString())
        require(inspect(executable, "RobotStaticStatus", path, with_role=True) == {"role": "未知"},
                "missing ID/type remains missing")
        path.write_bytes(pb.RobotStaticStatus(robot_id=999, robot_type=6).SerializeToString())
        require(inspect(executable, "RobotStaticStatus", path, with_role=True)["role"] == "空中",
                "unknown ID uses type fallback")

        # Verify the actual simulator encoder against the client interpreter,
        # without replacing this check with two matching handwritten fixtures.
        from simulator.server.state_manager import StateManager
        from simulator.server.mqtt_publisher import MQTTPublisher
        with contextlib.redirect_stdout(io.StringIO()):
            simulator = StateManager()
            publisher = MQTTPublisher(simulator)
            captured = {}
            publisher._publish = lambda topic, payload, qos=1: captured.update({topic: payload})
            for robot_id in (1, 3, 4, 5, 6, 7, 101, 103, 104, 105, 106, 107):
                simulator.select_robot(robot_id)
                publisher.current_robot_id = robot_id
                publisher.publish_robot_static_status()
                path.write_bytes(captured["RobotStaticStatus"])
                decoded = inspect(executable, "RobotStaticStatus", path, with_role=True)
                require(decoded["robot_id"] == robot_id and decoded["robot_type"] == robot_id % 100
                        and decoded["role"] == roles[robot_id % 100],
                        f"simulator -> C++ static role for robot {robot_id}")
    print("PASS: five PDF contracts, Python -> C++ all fields/unknown/zero, C++ -> Python fixtures; no MQTT.")
    print("PASS: P-003 static roles, red/blue precedence, missing/zero/unknown values; no MQTT.")
    print("PASS: actual simulator payload -> C++ roles for all 12 step-1 robots; no MQTT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
