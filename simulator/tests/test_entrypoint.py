"""Basic process-level checks for the standalone simulator entry point."""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from server.main import main


SIMULATOR_ROOT = Path(__file__).resolve().parents[1]


class EntrypointTests(unittest.TestCase):
    def run_entrypoint(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "server.main", *args],
            cwd=SIMULATOR_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_check_exits_successfully(self) -> None:
        result = self.run_entrypoint("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Entry point check passed", result.stderr)
        self.assertIn("Simulator skeleton stopped", result.stderr)

    def test_unknown_argument_is_rejected(self) -> None:
        result = self.run_entrypoint("--unknown-option")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--unknown-option", result.stderr)

    def test_keyboard_interrupt_exits_cleanly(self) -> None:
        with patch("server.main.time.sleep", side_effect=KeyboardInterrupt):
            with self.assertLogs("rm27.simulator", level="INFO") as logs:
                self.assertEqual(main([]), 0)
        self.assertTrue(any("Simulator skeleton stopped" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
