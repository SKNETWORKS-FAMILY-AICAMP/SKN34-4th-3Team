"""bizplan_service 보관함: 제목·단계·점수 추출, 소유자 확인, 삭제 시 작성 화면 정리, 예전 임시저장 이관.

DB 없이 `repo`를 대역으로 세운다(test_expense_service.py와 같은 방식).
"""

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from ninja.errors import HttpError  # noqa: E402

from services import bizplan_service  # noqa: E402


class PlanMetaTest(unittest.TestCase):
    def test_writing_without_plan(self):
        title, status, score = bizplan_service.plan_meta({"form": {"businessName": "  재고 관리  "}})
        self.assertEqual((title, status, score), ("재고 관리", "writing", None))

    def test_untitled_and_final_score_wins(self):
        data = {
            "form": {},
            "plan": {"sections": []},
            "evalResult": {"overallScore": 61},
            "finalPlan": {"sections": []},
            "finalEvalResult": {"overallScore": 78},
        }
        self.assertEqual(bizplan_service.plan_meta(data), ("제목 없는 사업계획서", "done", 78))

    def test_evaluated_uses_first_score(self):
        data = {"form": {"businessName": "A"}, "plan": {}, "evalResult": {"overallScore": 70}}
        self.assertEqual(bizplan_service.plan_meta(data)[1:], ("evaluated", 70))


class SavePlanTest(unittest.TestCase):
    def test_new_plan_is_inserted_without_plan_id(self):
        repo = MagicMock()
        repo.insert_bizplan.return_value = 7
        with patch.object(bizplan_service, "repo", repo):
            result = bizplan_service.save_plan(1, None, {"form": {"businessName": "A"}, "planId": 3})
        self.assertEqual(result, {"id": 7})
        saved = repo.insert_bizplan.call_args[0][4]
        self.assertNotIn("planId", saved)

    def test_other_users_plan_is_404(self):
        repo = MagicMock()
        repo.get_bizplan.return_value = {"id": 5, "user_id": 2}
        with patch.object(bizplan_service, "repo", repo):
            with self.assertRaises(HttpError) as ctx:
                bizplan_service.save_plan(1, 5, {"form": {}})
        self.assertEqual(ctx.exception.status_code, 404)
        repo.update_bizplan.assert_not_called()


class DeletePlanTest(unittest.TestCase):
    def test_clears_draft_when_deleting_open_plan(self):
        repo = MagicMock()
        repo.get_bizplan.return_value = {"id": 5, "user_id": 1}
        repo.get_bizplan_draft.return_value = {"data": {"planId": 5, "form": {"businessName": "A"}}}
        with patch.object(bizplan_service, "repo", repo):
            bizplan_service.delete_plan(1, 5)
        repo.delete_bizplan.assert_called_once_with(5)
        repo.delete_bizplan_draft.assert_called_once_with(1)

    def test_keeps_draft_of_other_plan(self):
        repo = MagicMock()
        repo.get_bizplan.return_value = {"id": 5, "user_id": 1}
        repo.get_bizplan_draft.return_value = {"data": {"planId": 9}}
        with patch.object(bizplan_service, "repo", repo):
            bizplan_service.delete_plan(1, 5)
        repo.delete_bizplan_draft.assert_not_called()


class ListPlansTest(unittest.TestCase):
    def test_legacy_draft_is_imported_once_and_linked(self):
        repo = MagicMock()
        legacy = {"form": {"businessName": "예전 초안"}}
        repo.get_bizplan_draft.side_effect = [{"data": legacy}, {"data": {**legacy, "planId": 11}}]
        repo.insert_bizplan.return_value = 11
        repo.list_bizplans.return_value = [
            {"id": 11, "title": "예전 초안", "status": "writing", "score": None, "created_at": None, "updated_at": None},
        ]
        with patch.object(bizplan_service, "repo", repo):
            result = bizplan_service.list_plans(1)
        repo.upsert_bizplan_draft.assert_called_once_with(1, {**legacy, "planId": 11})
        self.assertTrue(result["plans"][0]["isCurrent"])
        self.assertEqual(result["plans"][0]["statusLabel"], "작성 중")

    def test_empty_draft_is_not_imported(self):
        repo = MagicMock()
        repo.get_bizplan_draft.return_value = {"data": {}}
        repo.list_bizplans.return_value = []
        with patch.object(bizplan_service, "repo", repo):
            bizplan_service.list_plans(1)
        repo.insert_bizplan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
