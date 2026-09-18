"""repo.recent_chats: 사용자·카테고리 격리와 시간순 반환."""

import unittest
from unittest.mock import patch

from core import repo


class RecentChatsTest(unittest.TestCase):
    def test_query_filters_user_and_category(self):
        with patch.object(repo.db, "fetchall", return_value=[]) as fetchall:
            repo.recent_chats(7, "tax", 10)
        sql, params = fetchall.call_args[0]
        self.assertIn("WHERE user_id = ? AND category = ?", sql)
        self.assertIn("ORDER BY created_at DESC, id DESC LIMIT ?", sql)
        self.assertEqual(params, (7, "tax", 10))

    def test_rows_are_returned_oldest_first(self):
        rows = [{"id": 3}, {"id": 2}, {"id": 1}]
        with patch.object(repo.db, "fetchall", return_value=rows):
            result = repo.recent_chats(1, "tax")
        self.assertEqual([row["id"] for row in result], [1, 2, 3])

    def test_default_limit_is_ten(self):
        with patch.object(repo.db, "fetchall", return_value=[]) as fetchall:
            repo.recent_chats(1, "policy")
        self.assertEqual(fetchall.call_args[0][1][2], 10)


if __name__ == "__main__":
    unittest.main()
