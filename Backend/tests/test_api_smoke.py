"""Django Ninja 라우팅·인증·검증의 HTTP 계약 (DB 없이 repo를 대역으로)."""

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from ninja.testing import TestClient  # noqa: E402

from api import deps  # noqa: E402
from config.api import api  # noqa: E402
from core.security import create_token  # noqa: E402
from services import expense_service, policy_service  # noqa: E402

client = TestClient(api)


class AuthTest(unittest.TestCase):
    def test_missing_token_is_401(self):
        res = client.get("/users/me")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json(), {"detail": "로그인이 필요합니다."})

    def test_invalid_token_is_401(self):
        res = client.get("/users/me", headers={"Authorization": "Bearer nope"})
        self.assertEqual(res.status_code, 401)

    def test_admin_token_on_user_api_is_403(self):
        token = create_token(1, "admin")
        res = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 403)

    def test_user_token_on_admin_api_is_403(self):
        token = create_token(1, "user")
        res = client.get("/admin/monitoring", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 403)

    def test_suspended_user_is_403(self):
        repo = MagicMock()
        repo.get_user.return_value = {"id": 1, "status": "suspended"}
        token = create_token(1, "user")
        with patch.object(deps, "repo", repo):
            res = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 403)


class ReceiptUploadTest(unittest.TestCase):
    def _post(self, content: bytes):
        repo = MagicMock()
        repo.get_user.return_value = {"id": 1, "status": "active"}
        create = MagicMock(return_value={"receiptId": 9, "status": "done"})
        token = create_token(1, "user")
        with patch.object(deps, "repo", repo), patch.object(
            expense_service, "create_receipt", create
        ):
            res = client.post(
                "/expenses/receipts",
                FILES={"image": SimpleUploadedFile("r.png", content, content_type="image/png")},
                headers={"Authorization": f"Bearer {token}"},
            )
        return res, create

    def test_upload_passes_base64_and_mime(self):
        res, create = self._post(b"abc")
        self.assertEqual(res.status_code, 200)
        create.assert_called_once_with(1, "r.png", image_base64="YWJj", mime_type="image/png")

    def test_oversized_upload_is_413(self):
        res, create = self._post(b"x" * (4 * 1024 * 1024 + 1))
        self.assertEqual(res.status_code, 413)
        create.assert_not_called()


class ValidationTest(unittest.TestCase):
    def test_invalid_body_is_422(self):
        res = client.post("/auth/login", json={})
        self.assertEqual(res.status_code, 422)
        self.assertIn("detail", res.json())


class PublicEndpointTest(unittest.TestCase):
    def test_announcements_without_login(self):
        repo = MagicMock()
        repo.open_announcements.return_value = [
            {"id": 3, "policy_id": 7, "title": "예비창업패키지", "apply_end_date": None}
        ]
        with patch.object(policy_service, "repo", repo):
            res = client.get("/announcements?limit=5")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["announcements"][0]["policyId"], 7)
        repo.open_announcements.assert_called_once_with(5)

    def test_query_bounds_are_422(self):
        res = client.get("/announcements?limit=0")
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
