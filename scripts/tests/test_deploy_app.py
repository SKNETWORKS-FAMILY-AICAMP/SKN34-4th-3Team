"""Deployment order/failure tests using only fake Git and Docker commands."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_backup_db import BASH


SCRIPT = Path(__file__).resolve().parents[1] / "deploy_app.sh"
SHA = "a" * 40


@unittest.skipUnless(BASH, "Bash is required")
class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SCRIPT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        self.script = self.root / "scripts/deploy_app.sh"
        self.script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "calls"
        self.config = self.root / ".env"
        self.initial = 'TOKEN_SECRET=keep-this-value\nCOMPOSE_PROFILES="presentation"\n'
        self.config.write_text(self.initial, encoding="utf-8", newline="\n")
        commands = {
            "git": 'echo "$FAKE_SHA"\n',
            "sleep": "exit 0\n",
            "docker": '''echo "$*" >> "$FAKE_CALLS"
case "$*" in
  *"config --quiet"*) exit "${FAIL_CONFIG:-0}" ;;
  *"pull backend"*) exit "${FAIL_PULL:-0}" ;;
  *"run --rm db-migrate"*) exit "${FAIL_MIGRATE:-0}" ;;
  *"exec -T backend"*) exit "${FAIL_READY:-0}" ;;
  "image ls"*) printf '%s' "${FAKE_IMAGES:-}" ;;
  *) exit 0 ;;
esac
''',
        }
        for name, body in commands.items():
            p = self.bin / name
            p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
            p.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": self.bin.as_posix() + os.pathsep + os.environ["PATH"],
            "RELEASE_SHA": SHA, "FAKE_SHA": SHA,
            "GHCR_REPOSITORY": "Owner/Repo", "GHCR_TOKEN": "",
            "DEPLOY_READY_ATTEMPTS": "2", "DEPLOY_MIN_FREE_GB": "0",
            "FAKE_CALLS": self.calls.as_posix(),
            "TEST_SCRIPT": self.script.as_posix(),
            "TEST_BIN": ("/" + self.bin.drive[0].lower() + self.bin.as_posix()[2:]) if os.name == "nt" else self.bin.as_posix(),
        }

    def run_deploy(self, **env):
        return subprocess.run(
            [BASH, "-c", 'export PATH="$TEST_BIN:$PATH"; exec bash "$TEST_SCRIPT"'], env={**self.env, **env},
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )

    def test_pull_before_migration_and_no_build(self):
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls.read_text()
        self.assertLess(calls.index("pull backend"), calls.index("run --rm db-migrate"))
        self.assertIn("pull backend frontend llm presentation", calls)
        self.assertIn("--no-build --wait", calls)
        self.assertNotIn("--build", calls)
        self.assertIn("TOKEN_SECRET=keep-this-value", self.config.read_text())
        self.assertIn("APP_IMAGE_TAG=" + SHA, self.config.read_text())
        self.assertIn("ghcr.io/owner/repo", self.config.read_text())

    def test_invalid_config_or_pull_does_not_migrate_or_change_env(self):
        for failure in ("FAIL_CONFIG", "FAIL_PULL"):
            with self.subTest(failure=failure):
                self.calls.write_text("")
                result = self.run_deploy(**{failure: "1"})
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("db-migrate", self.calls.read_text())
                self.assertEqual(self.config.read_text(), self.initial)

    def test_failed_migration_does_not_replace_containers(self):
        result = self.run_deploy(FAIL_MIGRATE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("up -d", self.calls.read_text())

    def test_revision_mismatch_stops_before_docker(self):
        result = self.run_deploy(FAKE_SHA="b" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_readiness_failure_does_not_prune_images(self):
        result = self.run_deploy(FAIL_READY="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("image prune", self.calls.read_text())
        self.assertNotIn("image rm", self.calls.read_text())
        self.assertIn("readiness check failed", result.stderr)

    def test_low_disk_stops_before_pull(self):
        result = self.run_deploy(DEPLOY_MIN_FREE_GB="999999")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("pull", self.calls.read_text())
        self.assertEqual(self.config.read_text(), self.initial)
        self.assertIn("여유 공간", result.stderr)

    def test_removes_old_release_images_but_keeps_current_and_previous(self):
        previous, old = "b" * 40, "c" * 40
        self.config.write_text(self.initial + f"APP_IMAGE_TAG={previous}\n", encoding="utf-8", newline="\n")
        registry = "ghcr.io/owner/repo"
        images = [f"{registry}/llm:{SHA}", f"{registry}/llm:{previous}", f"{registry}/llm:{old}",
                  f"{registry}/backend:{old}", "pgvector/pgvector:pg16", "<none>:<none>"]
        result = self.run_deploy(FAKE_IMAGES="\n".join(images) + "\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        removed = [line.removeprefix("image rm ") for line in self.calls.read_text().splitlines()
                   if line.startswith("image rm ")]
        self.assertEqual(removed, [f"{registry}/llm:{old}", f"{registry}/backend:{old}"])
        calls = self.calls.read_text()
        self.assertLess(calls.index("image rm"), calls.index("image prune"))


if __name__ == "__main__":
    unittest.main()
