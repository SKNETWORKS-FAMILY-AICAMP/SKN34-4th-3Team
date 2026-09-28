"""사업계획서 임시저장 서버 저장 계약."""

import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from ninja.errors import HttpError  # noqa: E402
from ninja.testing import TestClient  # noqa: E402

from api import deps  # noqa: E402
from config.api import api  # noqa: E402
from core.security import create_token  # noqa: E402
from services import bizplan_service  # noqa: E402


client = TestClient(api)


def _headers(user_id: int = 1) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(user_id, 'user')}"}


def _active_user_repo(user_id: int = 1) -> MagicMock:
    repo = MagicMock()
    repo.get_user.return_value = {"id": user_id, "status": "active"}
    return repo


class BizplanDraftRouteTest(unittest.TestCase):
    def test_requires_login(self):
        self.assertEqual(client.get("/bizplan/draft").status_code, 401)
        self.assertEqual(client.put("/bizplan/draft", json={"data": {}}).status_code, 401)

    def test_missing_draft_returns_null(self):
        repo = MagicMock()
        repo.get_bizplan_draft.return_value = None
        with patch.object(deps, "repo", _active_user_repo()), patch.object(bizplan_service, "repo", repo):
            response = client.get("/bizplan/draft", headers=_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"data": None, "updatedAt": None})

    def test_get_returns_saved_draft(self):
        repo = MagicMock()
        repo.get_bizplan_draft.return_value = {
            "data": {"form": {"businessName": "창업"}, "supplementPage": 1},
            "updated_at": datetime(2026, 9, 25, 10, 0, 0),
        }
        with patch.object(deps, "repo", _active_user_repo()), patch.object(bizplan_service, "repo", repo):
            response = client.get("/bizplan/draft", headers=_headers())
        body = response.json()
        self.assertEqual(body["data"]["form"]["businessName"], "창업")
        self.assertTrue(body["updatedAt"].startswith("2026-09-25T10:00:00"))
        repo.get_bizplan_draft.assert_called_once_with(1)

    def test_put_saves_under_token_user(self):
        repo = MagicMock()
        data = {"form": {"businessName": "창업"}, "editedSectionKeys": ["section_1"]}
        with patch.object(deps, "repo", _active_user_repo(7)), patch.object(bizplan_service, "repo", repo):
            response = client.put("/bizplan/draft", json={"data": data}, headers=_headers(7))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"updated": True})
        repo.upsert_bizplan_draft.assert_called_once_with(7, data)

    def test_put_requires_object(self):
        with patch.object(deps, "repo", _active_user_repo()):
            response = client.put("/bizplan/draft", json={"data": "text"}, headers=_headers())
        self.assertEqual(response.status_code, 422)


class BizplanDraftSizeTest(unittest.TestCase):
    def test_max_template_and_images_fit(self):
        # 양식 4 MiB + 이미지 4 MiB를 Base64로 담은 크기(약 10.7 MB).
        base64_len = (4 * 1024 * 1024 + 2) // 3 * 4
        data = {
            "templateInfo": {"contentBase64": "A" * base64_len},
            "supplementImages": {"section_1": {"contentBase64": "B" * base64_len}},
        }
        repo = MagicMock()
        with patch.object(bizplan_service, "repo", repo):
            bizplan_service.save_draft(1, data)
        repo.upsert_bizplan_draft.assert_called_once()

    def test_over_limit_is_413(self):
        repo = MagicMock()
        with patch.object(bizplan_service, "repo", repo):
            with self.assertRaises(HttpError) as ctx:
                bizplan_service.save_draft(1, {"blob": "x" * bizplan_service.MAX_DRAFT_BYTES})
        self.assertEqual(ctx.exception.status_code, 413)
        repo.upsert_bizplan_draft.assert_not_called()


if __name__ == "__main__":
    unittest.main()
