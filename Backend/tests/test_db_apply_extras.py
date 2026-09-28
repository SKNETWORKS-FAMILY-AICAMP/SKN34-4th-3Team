"""db._apply_extras: app_extras.sql을 한 번에 실행하고, 실패해도 기동을 막지 않는다."""

import unittest
from unittest.mock import MagicMock

from core import db


class ApplyExtrasTest(unittest.TestCase):
    def test_whole_file_is_executed_once(self):
        conn = MagicMock()
        db._apply_extras(conn)
        conn.execute.assert_called_once()
        sql = conn.execute.call_args[0][0]
        self.assertIn("DO $$", sql)
        self.assertIn("END $$;", sql)
        conn.rollback.assert_not_called()

    def test_failure_rolls_back_without_raising(self):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError("boom")
        db._apply_extras(conn)
        conn.rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
