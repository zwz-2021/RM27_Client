from __future__ import annotations

import sys
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch


RELEASE_DIR = Path(__file__).resolve().parents[1]
if str(RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(RELEASE_DIR))

import generate_sim_protobuf


class GenerateSimulatorProtobufTest(unittest.TestCase):
    def test_build_command_uses_canonical_schema_and_sim_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "protocol").mkdir(parents=True)
            (root / "protocol/robomaster.proto").write_text(
                'syntax = "proto3";\n', encoding="utf-8"
            )
            command = generate_sim_protobuf.build_command(root, "/tmp/protoc")

        self.assertEqual("/tmp/protoc", command[0])
        self.assertIn(f"--proto_path={root / 'protocol'}", command)
        self.assertIn(f"--python_out={root / 'protocol'}", command)
        self.assertEqual(str(root / "protocol/robomaster.proto"), command[-1])

    def test_missing_canonical_schema_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaisesRegex(
                generate_sim_protobuf.GenerationError,
                "robomaster.proto",
            ):
                generate_sim_protobuf.build_command(root, "protoc")

    def test_incompatible_generator_preserves_committed_pb2(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "protocol").mkdir()
            (root / "protocol/robomaster.proto").write_text('syntax = "proto3";\n', encoding="utf-8")
            committed = root / "protocol/robomaster_pb2.py"
            original = "_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 6, 33, 2, '', 'robomaster.proto')\n"
            committed.write_text(original, encoding="utf-8")

            def fake_old_protoc(command, **kwargs):
                output = Path(next(item.split("=", 1)[1] for item in command if item.startswith("--python_out=")))
                (output / "robomaster_pb2.py").write_text(original.replace("6, 33, 2", "5, 29, 3"), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch.object(generate_sim_protobuf.subprocess, "run", fake_old_protoc):
                with self.assertRaisesRegex(generate_sim_protobuf.GenerationError, "原 pb2 未修改"):
                    generate_sim_protobuf.generate(root, protoc="old-protoc")
            self.assertEqual(original, committed.read_text(encoding="utf-8"))

    def test_matching_generator_writes_beside_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            protocol = root / "protocol"
            protocol.mkdir()
            (protocol / "robomaster.proto").write_text('syntax = "proto3";\n', encoding="utf-8")
            committed = protocol / "robomaster_pb2.py"
            original = "_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 6, 33, 2, '', 'robomaster.proto')\n"
            committed.write_text(original, encoding="utf-8")
            regenerated = original + "# newly generated\n"

            def matching_protoc(command, **kwargs):
                output = Path(next(item.split("=", 1)[1] for item in command if item.startswith("--python_out=")))
                (output / "robomaster_pb2.py").write_text(regenerated, encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch.object(generate_sim_protobuf.subprocess, "run", matching_protoc):
                result = generate_sim_protobuf.generate(root, protoc="matching-protoc")
            self.assertEqual(committed, result)
            self.assertEqual(regenerated, committed.read_text(encoding="utf-8"))
            self.assertFalse((root / "robomaster_pb2.py").exists())


if __name__ == "__main__":
    unittest.main()
