"""Exercise the backup shell script without Docker, AWS, or production settings."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "backup_db.sh"
GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(GIT_BASH) if GIT_BASH.exists() else shutil.which("bash")


@unittest.skipUnless(BASH, "Bash is required")
class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SCRIPT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.state = self.root / "state"
        self.calls = self.root / "calls"
        self.env_file = self.root / "backup.env"
        self.env_file.write_text(
            "POSTGRES_USER=test\nPOSTGRES_DB=test\nBACKUP_BUCKET=test\n", encoding="utf-8"
        )
        commands = {
            "flock": "exit 0\n",
            "docker": '''echo "docker $*" >> "$FAKE_CALLS"
case "$*" in
  *pg_dump*) printf PGDMP; [ "${FAIL_DUMP:-0}" = 0 ] ;;
  *pg_restore*) cat >/dev/null; [ "${FAIL_RESTORE:-0}" = 0 ] ;;
  *) exit 2 ;;
esac
''',
            "aws": '''echo "aws $*" >> "$FAKE_CALLS"
case "$1 $2" in
  "s3 cp") [ "${FAIL_UPLOAD:-0}" = 0 ] ;;
  "s3api head-object") echo "${REMOTE_SIZE:-5}" ;;
  "sns publish") exit 0 ;;
  *) exit 2 ;;
esac
''',
        }
        for name, body in commands.items():
            path = self.bin / name
            path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
            path.chmod(0o755)
        self.env = os.environ.copy()
        self.env.update(
            PATH=self.bin.as_posix() + os.pathsep + self.env["PATH"],
            BACKUP_ENV_FILE=self.env_file.as_posix(),
            BACKUP_STATE_DIR=self.state.as_posix(),
            BACKUP_ALERT_TOPIC_ARN="arn:test:backup",
            AWS_BIN=(self.bin / "aws").as_posix(),
            FAKE_CALLS=self.calls.as_posix(),
        )

    def run_backup(self, *args, **env):
        result = subprocess.run(
            [BASH, SCRIPT.as_posix(), *args], env={**self.env, **env},
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertFalse(list(self.state.glob("dump.*")), "temporary dump leaked")
        return result

    def test_success_records_only_verified_upload(self):
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.state / "last_success").exists())
        calls = self.calls.read_text()
        self.assertLess(calls.index("pg_restore"), calls.index("aws s3 cp"))
        self.assertIn("head-object", calls)
        self.assertNotIn("sns publish", calls)

    def test_dump_or_validation_failure_never_uploads(self):
        for failure in ("FAIL_DUMP", "FAIL_RESTORE"):
            with self.subTest(failure=failure):
                self.calls.write_text("")
                result = self.run_backup(**{failure: "1"})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.state / "last_success").exists())
                self.assertNotIn("aws s3 cp", self.calls.read_text())
                self.assertIn("sns publish", self.calls.read_text())

    def test_failed_upload_or_size_mismatch_preserves_last_success(self):
        self.state.mkdir()
        (self.state / "last_success").write_text("123\n")
        for failure in ({"FAIL_UPLOAD": "1"}, {"REMOTE_SIZE": "999"}):
            with self.subTest(failure=failure):
                result = self.run_backup(**failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((self.state / "last_success").read_text(), "123\n")
                self.assertTrue((self.state / "last_failure").exists())

    def test_missing_recent_backup_alerts(self):
        result = self.run_backup("--check-freshness")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sns publish", self.calls.read_text())

    def test_stale_or_future_timestamp_alerts(self):
        self.state.mkdir()
        for timestamp in (1, int(time.time()) + 3600):
            with self.subTest(timestamp=timestamp):
                (self.state / "last_success").write_text(str(timestamp))
                result = self.run_backup("--check-freshness")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("sns publish", self.calls.read_text())

    def test_recent_backup_is_fresh_without_docker(self):
        self.state.mkdir()
        (self.state / "last_success").write_text(str(int(time.time())))
        result = self.run_backup("--check-freshness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
