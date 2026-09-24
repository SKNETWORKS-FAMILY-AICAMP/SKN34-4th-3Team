"""Django Ninja 라우팅·인증·검증의 HTTP 계약 (DB 없이 repo를 대역으로)."""

import base64
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
from services import chat_service, expense_service, policy_service  # noqa: E402

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


# 실제 PNG·JPEG 파일의 첫 바이트(매직 바이트). 업로드 시 Content-Type 헤더가 아니라
# 이 바이트로 형식을 판별하므로(스푸핑 방지), 업로드 성공 테스트는 진짜 이미지 바이트를 써야 한다.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


class ReceiptUploadTest(unittest.TestCase):
    def _post(self, content: bytes, *, declared_content_type: str = "image/png", filename: str = "r.png"):
        repo = MagicMock()
        repo.get_user.return_value = {"id": 1, "status": "active"}
        create = MagicMock(return_value={"receiptId": 9, "status": "done"})
        token = create_token(1, "user")
        with patch.object(deps, "repo", repo), patch.object(
            expense_service, "create_receipt", create
        ):
            res = client.post(
                "/expenses/receipts",
                FILES={
                    "image": SimpleUploadedFile(
                        filename, content, content_type=declared_content_type
                    )
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        return res, create

    def test_upload_passes_base64_and_mime(self):
        content = _PNG_MAGIC + b"...rest-of-file..."
        res, create = self._post(content)
        self.assertEqual(res.status_code, 200)
        create.assert_called_once_with(
            1,
            "r.png",
            image_base64=base64.b64encode(content).decode(),
            mime_type="image/png",
            image_bytes=content,
        )

    def test_oversized_upload_is_413(self):
        res, create = self._post(_PNG_MAGIC + b"x" * (4 * 1024 * 1024 + 1))
        self.assertEqual(res.status_code, 413)
        create.assert_not_called()

    def test_real_media_type_is_used_even_if_content_type_header_lies(self):
        # Content-Type 헤더는 "image/png"라고 주장하지만 실제 바이트는 JPEG다. 저장·응답에는
        # 헤더가 아니라 실제 바이트로 판별한 형식(image/jpeg)이 쓰여야 한다.
        content = _JPEG_MAGIC + b"...rest-of-file..."
        res, create = self._post(content, declared_content_type="image/png")
        self.assertEqual(res.status_code, 200)
        create.assert_called_once_with(
            1,
            "r.png",
            image_base64=base64.b64encode(content).decode(),
            mime_type="image/jpeg",
            image_bytes=content,
        )

    def test_non_image_upload_is_415(self):
        # 헤더가 뭐라고 주장하든(HTML·스크립트가 든 파일에도 "image/jpeg"를 붙여 보낼 수 있다)
        # 실제 바이트가 지원 형식(JPEG·PNG·WebP)이 아니면 저장하지 않고 거부한다.
        res, create = self._post(
            b"<script>alert(1)</script>", declared_content_type="image/jpeg"
        )
        self.assertEqual(res.status_code, 415)
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


class ChatClearTest(unittest.TestCase):
    def test_legacy_ids_param_is_400_and_deletes_nothing(self):
        repo = MagicMock()
        repo.get_user.return_value = {"id": 1, "status": "active"}
        token = create_token(1, "user")
        with patch.object(deps, "repo", repo), patch.object(chat_service, "clear_messages") as clear:
            res = client.delete(
                "/chat/messages?ids=1,2", headers={"Authorization": f"Bearer {token}"}
            )
        self.assertEqual(res.status_code, 400)
        clear.assert_not_called()


if __name__ == "__main__":
    unittest.main()
