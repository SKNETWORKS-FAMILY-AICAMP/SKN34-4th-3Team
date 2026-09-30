"""사업계획서 파일 보관 API·제한·원본 반환 계약."""

import base64
import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from urllib.parse import quote

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from ninja.errors import HttpError  # noqa: E402
from ninja.testing import TestClient  # noqa: E402

from api import deps  # noqa: E402
from config.api import api  # noqa: E402
from core.llm_client import LLMRequestError  # noqa: E402
from core.security import create_token  # noqa: E402
from services import bizplan_service  # noqa: E402


BODY = {
    "title": "한글 사업계획서", "format": "pdf",
    "sections": [{"key": "problem", "label": "문제", "content": "고객의 문제"}],
}
RAW = b"%PDF-business-plan"
RENDERED = {
    "fileName": "한글 사업계획서.pdf", "mimeType": "application/pdf",
    "contentBase64": base64.b64encode(RAW).decode(),
}
ROW = {
    "id": 3, "title": BODY["title"], "file_name": RENDERED["fileName"],
    "format": "pdf", "size_bytes": len(RAW), "created_at": datetime(2026, 9, 30, 10),
}


def headers(user_id=1):
    return {"Authorization": f"Bearer {create_token(user_id, 'user')}"}


class BizplanDocumentRouteTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api)
        self.auth_repo = MagicMock()
        self.auth_repo.get_user.side_effect = lambda user_id: {"id": user_id, "status": "active"}
        self.repo = MagicMock()
        self.repo.count_bizplan_documents.return_value = 0
        self.repo.get_bizplan_draft_summary.return_value = None
        self.repo.insert_bizplan_document.return_value = ROW
        self.addCleanup(patch.stopall)
        patch.object(deps, "repo", self.auth_repo).start()
        patch.object(bizplan_service, "repo", self.repo).start()
        self.render = patch.object(bizplan_service, "render", return_value=RENDERED).start()

    def test_all_routes_require_login(self):
        responses = [
            self.client.post("/bizplan/documents", json=BODY),
            self.client.get("/bizplan/documents"),
            self.client.get("/bizplan/documents/3/file"),
            self.client.delete("/bizplan/documents/3"),
        ]
        self.assertEqual([response.status_code for response in responses], [401] * 4)
        self.render.assert_not_called()
        self.repo.insert_bizplan_document.assert_not_called()

    def test_save_list_download_delete_contract(self):
        saved = self.client.post("/bizplan/documents", json=BODY, headers=headers(7))
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["fileName"], RENDERED["fileName"])
        self.assertEqual(set(saved.json()), {"id", "title", "fileName", "format", "sizeBytes", "createdAt"})
        self.repo.insert_bizplan_document.assert_called_once_with(
            7, BODY["title"], RENDERED["fileName"], "pdf", "application/pdf", RAW, 8,
        )
        self.repo.list_bizplan_documents.return_value = [ROW]
        listed = self.client.get("/bizplan/documents", headers=headers(7))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json(), {"draft": None, "documents": [saved.json()]})
        self.repo.list_bizplan_documents.assert_called_once_with(7)

        self.repo.get_bizplan_document.return_value = {
            "file_data": memoryview(RAW), "mime_type": "application/pdf",
            "file_name": RENDERED["fileName"],
        }
        downloaded = self.client.get("/bizplan/documents/3/file", headers=headers(7))
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, RAW)
        self.assertEqual(downloaded["Content-Type"], "application/pdf")
        self.assertEqual(downloaded["Content-Disposition"],
                         "attachment; filename*=utf-8''" + quote(RENDERED["fileName"]))
        self.repo.get_bizplan_document.assert_called_once_with(7, 3)

        self.repo.delete_bizplan_document.return_value = True
        deleted = self.client.delete("/bizplan/documents/3", headers=headers(7))
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"deleted": True})
        self.repo.delete_bizplan_document.assert_called_once_with(7, 3)

    def test_empty_list(self):
        self.repo.list_bizplan_documents.return_value = []
        response = self.client.get("/bizplan/documents", headers=headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"draft": None, "documents": []})

    def test_list_includes_draft_metadata_for_authenticated_user(self):
        self.repo.get_bizplan_draft_summary.return_value = {
            "title": "작성 중인 사업", "updated_at": datetime(2026, 9, 30, 11),
        }
        self.repo.list_bizplan_documents.return_value = [ROW]
        response = self.client.get("/bizplan/documents", headers=headers(7))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["draft"], {
            "title": "작성 중인 사업", "updatedAt": "2026-09-30T11:00:00",
        })
        self.assertEqual(len(response.json()["documents"]), 1)
        self.repo.get_bizplan_draft_summary.assert_called_once_with(7)

    def test_untitled_draft_still_appears_without_files(self):
        self.repo.list_bizplan_documents.return_value = []
        for title in (None, "", "   "):
            with self.subTest(title=title):
                self.repo.get_bizplan_draft_summary.return_value = {
                    "title": title, "updated_at": datetime(2026, 9, 30, 11),
                }
                response = self.client.get("/bizplan/documents", headers=headers())
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["draft"]["title"], "사업계획서")
                self.assertEqual(response.json()["documents"], [])

    def test_missing_or_other_users_document_is_404(self):
        self.repo.get_bizplan_document.return_value = None
        self.repo.delete_bizplan_document.return_value = False
        for user_id in (1, 2):
            with self.subTest(user_id=user_id):
                self.assertEqual(self.client.get("/bizplan/documents/3/file", headers=headers(user_id)).status_code, 404)
                self.assertEqual(self.client.delete("/bizplan/documents/3", headers=headers(user_id)).status_code, 404)
                self.repo.get_bizplan_document.assert_called_with(user_id, 3)
                self.repo.delete_bizplan_document.assert_called_with(user_id, 3)

    def test_full_storage_rejects_before_render(self):
        self.repo.count_bizplan_documents.return_value = 8
        response = self.client.post("/bizplan/documents", json=BODY, headers=headers())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], bizplan_service.DOCUMENT_LIMIT_MESSAGE)
        self.render.assert_not_called()
        self.repo.insert_bizplan_document.assert_not_called()

    def test_limit_reached_during_render_is_409(self):
        self.repo.insert_bizplan_document.return_value = None
        response = self.client.post("/bizplan/documents", json=BODY, headers=headers())
        self.assertEqual(response.status_code, 409)
        self.render.assert_called_once()

    def test_duplicate_saves_create_distinct_documents(self):
        self.repo.insert_bizplan_document.side_effect = [ROW, {**ROW, "id": 4}]
        first = self.client.post("/bizplan/documents", json=BODY, headers=headers())
        second = self.client.post("/bizplan/documents", json=BODY, headers=headers())
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual((first.json()["id"], second.json()["id"]), (3, 4))
        self.assertEqual(self.render.call_count, 2)

    def test_bad_or_empty_rendered_base64_is_not_saved(self):
        for content in ("not base64!", "", "한글", None):
            with self.subTest(content=content):
                self.render.return_value = {**RENDERED, "contentBase64": content}
                response = self.client.post("/bizplan/documents", json=BODY, headers=headers())
                self.assertEqual(response.status_code, 503)
        self.repo.insert_bizplan_document.assert_not_called()

    def test_render_failure_is_not_saved(self):
        self.render.side_effect = HttpError(504, "문서 출력 시간 초과")
        response = self.client.post("/bizplan/documents", json=BODY, headers=headers())
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["detail"], "문서 출력 시간 초과")
        self.repo.insert_bizplan_document.assert_not_called()

    def test_fifty_mib_boundary(self):
        self.assertEqual(bizplan_service.MAX_DOCUMENT_BYTES, 50 * 1024 * 1024)
        for extra, expected in ((0, 200), (1, 413)):
            with self.subTest(extra=extra):
                self.repo.insert_bizplan_document.reset_mock()
                self.render.return_value = {
                    **RENDERED,
                    "contentBase64": base64.b64encode(b"x" * (bizplan_service.MAX_DOCUMENT_BYTES + extra)).decode(),
                }
                response = self.client.post("/bizplan/documents", json=BODY, headers=headers())
                self.assertEqual(response.status_code, expected)
                if extra:
                    self.repo.insert_bizplan_document.assert_not_called()
                else:
                    self.assertEqual(len(self.repo.insert_bizplan_document.call_args.args[5]), bizplan_service.MAX_DOCUMENT_BYTES)


class BizplanDocumentRenderValidationTest(unittest.TestCase):
    def test_save_uses_existing_template_and_image_validation(self):
        cases = [
            ({**BODY, "template": {"fileName": "form.txt", "contentBase64": "YQ=="}}, 422),
            ({**BODY, "images": [{"key": "problem", "mimeType": "image/png", "contentBase64": "YQ=="}]}, 422),
        ]
        with patch.object(bizplan_service.repo, "count_bizplan_documents", return_value=0), patch.object(
            bizplan_service.repo, "insert_bizplan_document"
        ) as insert, patch.object(bizplan_service, "render_business_plan") as render:
            for body, status in cases:
                with self.subTest(body=body), self.assertRaises(HttpError) as raised:
                    bizplan_service.save_document(1, body)
                self.assertEqual(raised.exception.status_code, status)
            insert.assert_not_called()
            render.assert_not_called()

    def test_document_api_failure_preserves_status(self):
        with patch.object(bizplan_service.repo, "count_bizplan_documents", return_value=0), patch.object(
            bizplan_service.repo, "insert_bizplan_document"
        ) as insert, patch.object(
            bizplan_service, "render_business_plan", side_effect=LLMRequestError(503, "출력 불가")
        ), self.assertRaises(HttpError) as raised:
            bizplan_service.save_document(1, BODY)
        self.assertEqual(raised.exception.status_code, 503)
        insert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
