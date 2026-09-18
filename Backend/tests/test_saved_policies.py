"""policy_service 관심 정책 저장·해제 계약."""

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from services import policy_service


class SavePolicyTest(unittest.TestCase):
    def test_save_unknown_policy_is_404(self):
        repo = MagicMock()
        repo.get_policy.return_value = None
        with patch.object(policy_service, "repo", repo):
            with self.assertRaises(HTTPException) as ctx:
                policy_service.save_policy(1, 999)
        self.assertEqual(ctx.exception.status_code, 404)
        repo.save_policy.assert_not_called()

    def test_save_known_policy_writes(self):
        repo = MagicMock()
        repo.get_policy.return_value = {"id": 7}
        with patch.object(policy_service, "repo", repo):
            policy_service.save_policy(1, 7)
        repo.save_policy.assert_called_once_with(1, 7)

    def test_unsave_delegates_to_repo(self):
        repo = MagicMock()
        with patch.object(policy_service, "repo", repo):
            policy_service.unsave_policy(1, 7)
        repo.unsave_policy.assert_called_once_with(1, 7)

    def test_open_announcements_carry_policy_id(self):
        # 홈 마감 임박 패널이 공고 id가 아니라 정책 id로 저장해야 한다.
        repo = MagicMock()
        repo.open_announcements.return_value = [
            {"id": 3, "policy_id": 7, "title": "예비창업패키지", "apply_end_date": None}
        ]
        with patch.object(policy_service, "repo", repo):
            items = policy_service.list_open_announcements(4)
        self.assertEqual(items[0]["id"], 3)
        self.assertEqual(items[0]["policyId"], 7)


if __name__ == "__main__":
    unittest.main()
