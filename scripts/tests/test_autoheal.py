"""Autoheal restart tests using only a fake Docker command."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_backup_db import BASH


SCRIPT = Path(__file__).resolve().parents[1] / "autoheal.sh"


@unittest.skipUnless(BASH, "Bash is required")
class AutohealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SCRIPT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "calls"
        docker = self.bin / "docker"
        docker.write_text('''#!/usr/bin/env bash
echo "$*" >> "$FAKE_CALLS"
case "$1" in
  ps) [ -z "$FAKE_UNHEALTHY" ] || printf '%s\\n' $FAKE_UNHEALTHY ;;
  restart) exit 0 ;;
  *) exit 2 ;;
esac
''', encoding="utf-8", newline="\n")
        docker.chmod(0o755)
        self.env = {
            **os.environ,
            "FAKE_CALLS": self.calls.as_posix(),
            "TEST_SCRIPT": SCRIPT.as_posix(),
            "TEST_BIN": ("/" + self.bin.drive[0].lower() + self.bin.as_posix()[2:]) if os.name == "nt" else self.bin.as_posix(),
        }

    def run_autoheal(self, unhealthy):
        return subprocess.run(
            [BASH, "-c", 'export PATH="$TEST_BIN:$PATH"; exec bash "$TEST_SCRIPT"'],
            env={**self.env, "FAKE_UNHEALTHY": unhealthy},
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )

    def test_restarts_only_unhealthy_containers(self):
        # 멈춘 OCR로 llm /health가 503이 되면 compose healthcheck가 unhealthy로 바꾸고, 여기서 재시작한다.
        result = self.run_autoheal("app-llm-1")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls.read_text().splitlines()
        self.assertIn("--filter health=unhealthy", calls[0])
        self.assertEqual(calls[1:], ["restart app-llm-1"])
        self.assertIn("restart app-llm-1", result.stdout)

    def test_no_unhealthy_container_restarts_nothing(self):
        result = self.run_autoheal("")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("restart", self.calls.read_text())


if __name__ == "__main__":
    unittest.main()
