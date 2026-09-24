"""expense_service: 지출 목록 N+1/쓰기 방지, 품목 삭제, mime 검증 예외 경로.

DB 없이 `repo`를 대역으로 세운다(test_api_smoke.py와 같은 방식).
"""

import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from ninja.errors import HttpError  # noqa: E402

from services import expense_service  # noqa: E402


def _expense(**overrides) -> dict:
    base = {
        "id": 1,
        "receipt_id": 10,
        "user_id": 1,
        "category": "사무용품",
        "amount": 18000,
        "date": date(2026, 9, 1),
        "deductible": True,
        "deductible_confidence": 0.9,
        "deductible_tier": "high",
        "proof_valid": True,
        "missing_fields": [],
    }
    base.update(overrides)
    return base


class ListExpensesBatchQueryTest(unittest.TestCase):
    """목록 조회는 영수증 수와 무관하게 정해진 횟수만 쿼리하고, DB에 쓰지 않는다."""

    def test_fetches_extractions_and_metas_in_one_batch_call_each(self):
        rows = [_expense(id=i, receipt_id=100 + i) for i in range(1, 4)]
        repo = MagicMock()
        repo.list_expenses.return_value = rows
        repo.get_extractions.return_value = {
            100 + i: {"vendor": f"상호{i}", "items": [], "proof_type": "unknown"} for i in range(1, 4)
        }
        repo.get_receipt_metas.return_value = {100 + i: {"created_at": None} for i in range(1, 4)}

        with patch.object(expense_service, "repo", repo):
            result = expense_service.list_expenses(user_id=1)

        self.assertEqual(len(result), 3)
        # 영수증이 몇 건이든 배치 조회는 한 번씩만 나가야 한다(N+1이면 여기서 3번씩 호출됨).
        repo.get_extractions.assert_called_once()
        repo.get_receipt_metas.assert_called_once()
        self.assertEqual(sorted(repo.get_extractions.call_args[0][0]), [101, 102, 103])
        # 목록 조회(GET)는 읽기 전용이어야 한다.
        repo.update_expense.assert_not_called()

    def test_legacy_category_is_recalculated_without_writing(self):
        # "식비"는 새 지출항목 규칙에 없는 예전 분류다.
        rows = [_expense(category="식비")]
        repo = MagicMock()
        repo.list_expenses.return_value = rows
        repo.get_extractions.return_value = {
            10: {"vendor": "김밥천국", "items": [], "proof_type": "unknown"}
        }
        repo.get_receipt_metas.return_value = {10: {"created_at": None}}

        with patch.object(expense_service, "repo", repo):
            result = expense_service.list_expenses(user_id=1)

        # 화면에는 새 분류(복리후생비)로 보여주되,
        self.assertEqual(result[0]["category"], "복리후생비")
        # DB의 예전 분류는 그대로 두고 저장을 시도하지 않는다.
        repo.update_expense.assert_not_called()


class DeleteItemTest(unittest.TestCase):
    def test_removes_item_by_index(self):
        repo = MagicMock()
        repo.get_expense.return_value = _expense()
        repo.get_extraction.return_value = {
            "items": [{"name": "노트", "price": 3000}, {"name": "펜", "price": None}],
            "read_meta": {},
            "vendor": "예시상점",
            "proof_type": "unknown",
        }

        with patch.object(expense_service, "repo", repo):
            expense_service.delete_item(expense_id=1, user_id=1, item_index=0)

        saved_items = repo.update_extraction_items.call_args[0][1]
        self.assertEqual(saved_items, [{"name": "펜", "price": None}])

    def test_out_of_range_index_is_404(self):
        repo = MagicMock()
        repo.get_expense.return_value = _expense()
        repo.get_extraction.return_value = {"items": [{"name": "노트", "price": None}]}

        with patch.object(expense_service, "repo", repo):
            with self.assertRaises(HttpError) as ctx:
                expense_service.delete_item(expense_id=1, user_id=1, item_index=5)
        self.assertEqual(ctx.exception.status_code, 404)
        repo.update_extraction_items.assert_not_called()

    def test_other_users_expense_is_404(self):
        repo = MagicMock()
        repo.get_expense.return_value = _expense(user_id=2)

        with patch.object(expense_service, "repo", repo):
            with self.assertRaises(HttpError) as ctx:
                expense_service.delete_item(expense_id=1, user_id=1, item_index=0)
        self.assertEqual(ctx.exception.status_code, 404)
        repo.update_extraction_items.assert_not_called()


if __name__ == "__main__":
    unittest.main()
