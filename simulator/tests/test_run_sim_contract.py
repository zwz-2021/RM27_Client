#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_SCRIPT = PROJECT_ROOT / "simulator" / "run_sim.sh"
BASH = shutil.which("bash")
if os.name == "nt":
    BASH = next((str(path) for path in (
        Path("D:/Git/bin/bash.exe"),
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe",
    ) if path.is_file()), None)


def shell_path(path):
    """Convert absolute Windows paths for the Git Bash fixture shell."""
    path = Path(path).resolve()
    if os.name == "nt":
        return "/" + path.drive[0].lower() + path.as_posix()[2:]
    return str(path)


@unittest.skipUnless(BASH, "POSIX Bash or Git Bash is required for the upstream launcher contracts")
class RunSimContractTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="rm26-run-sim-")
        self.sandbox = Path(self.temp_dir.name)
        self.project_root = self.sandbox / "project"
        self.sim_root = self.project_root / "simulator"
        self.bin_dir = self.sandbox / "bin"
        self.invocation_log = self.sandbox / "python-invocations.log"
        self.lsof_log = self.sandbox / "lsof.log"

        (self.sim_root / "server").mkdir(parents=True)
        (self.sim_root / "tools").mkdir(parents=True)
        (self.sim_root / "resources" / "videos").mkdir(parents=True)
        self.bin_dir.mkdir(parents=True)

        shutil.copy2(RUN_SCRIPT, self.sim_root / "run_sim.sh")
        shutil.copy2(PROJECT_ROOT / "simulator" / "pyproject.toml", self.sim_root / "pyproject.toml")
        (self.sim_root / "server" / "main.py").write_text("# test stub\n", encoding="utf-8")
        (self.sim_root / "tools" / "video_sender.py").write_text(
            "# test stub\n", encoding="utf-8"
        )
        self.video_file = self.sim_root / "resources" / "videos" / "demo.mp4"
        self.video_file.write_bytes(b"test-video")

        self._write_executable("uname", """
            #!/bin/bash
            printf 'Linux\n'
        """)
        self._write_executable("docker", """
            #!/bin/bash
            exit 1
        """)
        self._write_executable("docker-compose", """
            #!/bin/bash
            exit 1
        """)
        self._write_executable("ffmpeg", """
            #!/bin/bash
            exit 0
        """)
        self._write_executable("lsof", """
            #!/bin/bash
            printf '%s\n' "$*" >> "$RM_SIM_TEST_LSOF_LOG"
            if [[ -n "${RM_SIM_TEST_OCCUPIED_PID:-}" ]]; then
                printf '%s\n' "$RM_SIM_TEST_OCCUPIED_PID"
                exit 0
            fi
            exit 1
        """)
        self._write_executable("python3", """
            #!/bin/bash
            if [[ "${1:-}" == "-m" && "${2:-}" == "simulator.server.main" && "${3:-}" == "--probe-mqtt" ]]; then
                exit 0
            fi
            (
                IFS='|'
                printf '%s\n' "$*" >> "$RM_SIM_TEST_INVOCATIONS"
            )
            if [[ "${1:-}" == "-c" ]]; then
                exit 0
            fi
            if [[ "${1:-}" == "-m" ]]; then
                sleep 4
            else
                sleep 1.5
            fi
        """)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_executable(self, name, source):
        path = self.bin_dir / name
        path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
        path.chmod(0o755)

    def _run_script(self, *arguments, occupied_pid=None):
        environment = os.environ.copy()
        environment.pop("VIRTUAL_ENV", None)
        environment["PATH"] = os.environ.get("PATH", "")
        environment["RM_SIM_TEST_INVOCATIONS"] = shell_path(self.invocation_log)
        environment["RM_SIM_TEST_LSOF_LOG"] = shell_path(self.lsof_log)
        if occupied_pid is not None:
            environment["RM_SIM_TEST_OCCUPIED_PID"] = str(occupied_pid)
        else:
            environment.pop("RM_SIM_TEST_OCCUPIED_PID", None)

        completed = subprocess.run(
            [BASH, "-c", 'export PATH="$1:/usr/bin:/bin"; shift; exec "$@"',
             "rm27-launcher-test", shell_path(self.bin_dir),
             shell_path(self.sim_root / "run_sim.sh"),
             *(shell_path(argument) if os.path.isabs(argument) and Path(argument).exists() else argument
               for argument in arguments)],
            cwd=self.project_root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=12,
            check=False,
        )
        # 视频发送器的运行日志属于临时工件，测试结束前一并清理。
        for line in completed.stdout.splitlines():
            marker = "日志文件: "
            if marker in line:
                log_path = line.split(marker, 1)[1].strip()
                if os.name != "nt":
                    Path(log_path).unlink(missing_ok=True)
        return completed

    def _python_invocations(self):
        if not self.invocation_log.exists():
            return []
        return self.invocation_log.read_text(encoding="utf-8").splitlines()

    def test_selected_web_port_conflict_does_not_kill_owner(self):
        owner = subprocess.Popen([BASH, "-c", "sleep 30"])
        try:
            completed = self._run_script(
                "--no-video", "--web-port", "9123", occupied_pid=owner.pid
            )
            self.assertNotEqual(0, completed.returncode)
            self.assertIn("Web 端口 9123 已被其他进程占用", completed.stdout)
            self.assertIsNone(owner.poll())
            self.assertIn("tcp:9123", self.lsof_log.read_text(encoding="utf-8"))
            self.assertEqual([], self._python_invocations())
        finally:
            owner.terminate()
            owner.wait(timeout=5)

    def test_video_only_starts_only_video_sender(self):
        completed = self._run_script(
            "--video-only", "--video-file", str(self.video_file)
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        invocations = self._python_invocations()
        self.assertTrue(any(line.startswith("-u|") for line in invocations))
        self.assertFalse(any(line.startswith("-m|simulator.server.main|") for line in invocations))

    def test_default_keeps_video_disabled(self):
        completed = self._run_script(
            "--mqtt-host", "192.0.2.1", "--web-port", "9126"
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        invocations = self._python_invocations()
        self.assertTrue(any(line.startswith("-m|simulator.server.main|") for line in invocations))
        self.assertFalse(any(line.startswith("-u|") for line in invocations))

    def test_video_file_enables_video_alongside_server(self):
        completed = self._run_script(
            "--video-file",
            str(self.video_file),
            "--mqtt-host",
            "192.0.2.1",
            "--web-port",
            "9124",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        invocations = self._python_invocations()
        self.assertTrue(any(line.startswith("-u|") for line in invocations))
        server_call = next(
            line for line in invocations if line.startswith("-m|simulator.server.main|")
        )
        self.assertIn("|--web-port|9124", server_call)

    def test_no_video_starts_only_protocol_server(self):
        completed = self._run_script(
            "--no-video", "--mqtt-host", "192.0.2.1", "--web-port", "9125"
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        invocations = self._python_invocations()
        self.assertTrue(any(line.startswith("-m|simulator.server.main|") for line in invocations))
        self.assertFalse(any(line.startswith("-u|") for line in invocations))

    def test_cleanup_has_no_broad_process_scan(self):
        source = RUN_SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("pkill ", source)
        self.assertNotIn("Get-CimInstance", source)
        self.assertNotIn("cleanup_port_8000", source)
        self.assertNotIn("lsof -i :8000 -t", source)


if __name__ == "__main__":
    unittest.main()
