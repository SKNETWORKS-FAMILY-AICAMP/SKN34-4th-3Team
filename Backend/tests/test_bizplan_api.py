"""사업계획서 신규 Backend 계약과 LLM 전달 내용을 검증한다."""

import base64
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from ninja.testing import TestClient  # noqa: E402

from api import deps  # noqa: E402
from config.api import api  # noqa: E402
from core.llm_client import LLMRequestError  # noqa: E402
from core.security import create_token  # noqa: E402
from services import bizplan_service  # noqa: E402
from schemas.bizplan import BusinessPlanRequest  # noqa: E402


client = TestClient(api)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(1, 'user')}"}


def _active_user_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_user.return_value = {"id": 1, "status": "active"}
    return repo


class BusinessPlanRouteTest(unittest.TestCase):
    def test_new_contract_requires_login(self):
        response = client.post(
            "/bizplan/refine",
            json={"input": {"problem": "문제", "solution": "해결"}},
        )
        self.assertEqual(response.status_code, 401)

    def test_refine_route_passes_structured_input(self):
        refined = {
            "refined": {
                "businessName": "정리된 사업명", "tagline": "", "targetCustomer": "고객",
                "problem": "문제", "solution": "해결", "differentiator": "",
                "team": "", "extraNotes": "",
            },
            "llmUsed": True,
        }
        service = MagicMock(return_value=refined)
        with patch.object(deps, "repo", _active_user_repo()), patch.object(
            bizplan_service, "refine", service
        ):
            response = client.post(
                "/bizplan/refine",
                json={"input": {"businessName": "사업명", "targetCustomer": "고객", "problem": "문제", "solution": "해결"}},
                headers=_headers(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["refined"]["businessName"], "정리된 사업명")
        self.assertEqual(service.call_args[0][0]["input"]["problem"], "문제")

    def test_template_error_reason_is_preserved(self):
        template = {
            "fileName": "form.pdf",
            "contentBase64": base64.b64encode(b"%PDF-form").decode(),
        }
        error = LLMRequestError(422, "입력 가능한 텍스트 필드가 없습니다.")
        with patch.object(deps, "repo", _active_user_repo()), patch.object(
            bizplan_service, "inspect_business_plan_template", side_effect=error
        ):
            response = client.post(
                "/bizplan/template-inspect", json=template, headers=_headers()
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "입력 가능한 텍스트 필드가 없습니다.")

    def test_render_route_returns_download_contract(self):
        rendered = {
            "fileName": "business-plan.pdf",
            "mimeType": "application/pdf",
            "contentBase64": base64.b64encode(b"%PDF-result").decode(),
        }
        service = MagicMock(return_value=rendered)
        with patch.object(deps, "repo", _active_user_repo()), patch.object(
            bizplan_service, "render", service
        ):
            response = client.post(
                "/bizplan/render",
                json={
                    "title": "사업명",
                    "sections": [{"key": "problem", "label": "문제인식", "content": "내용"}],
                    "format": "pdf",
                },
                headers=_headers(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), rendered)
        self.assertEqual(service.call_args[0][0]["format"], "pdf")

    def test_render_route_forwards_image_bound_to_a_template_field(self):
        service = MagicMock(return_value={
            "fileName": "business-plan.pdf", "mimeType": "application/pdf",
            "contentBase64": base64.b64encode(b"%PDF-result").decode(),
        })
        image = base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode()
        with patch.object(deps, "repo", _active_user_repo()), patch.object(
            bizplan_service, "render", service
        ):
            response = client.post("/bizplan/render", json={
                "sections": [{"key": "section_1", "label": "제품 사진 [유형: image]", "content": ""}],
                "format": "pdf",
                "template": {"fileName": "form.pdf", "contentBase64": base64.b64encode(b"%PDF-form").decode()},
                "images": [{"key": "section_1", "mimeType": "image/png", "contentBase64": image}],
            }, headers=_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(service.call_args[0][0]["images"][0]["contentBase64"], image)


class BusinessPlanServiceTest(unittest.TestCase):
    def test_render_rejects_image_with_mismatched_file_signature(self):
        with self.assertRaises(Exception) as raised:
            bizplan_service.render({
                "template": {"fileName": "form.pdf",
                             "contentBase64": base64.b64encode(b"%PDF-form").decode()},
                "sections": [{"key": "section_1", "label": "제품 사진", "content": ""}],
                "images": [{"key": "section_1", "mimeType": "image/png",
                            "contentBase64": base64.b64encode(b"not a png").decode()}],
            })
        self.assertEqual(raised.exception.status_code, 422)

    def test_missing_announcement_is_404(self):
        with patch.object(bizplan_service.repo, "get_announcement", return_value=None):
            with self.assertRaises(Exception) as raised:
                bizplan_service.generate({"announcementId": 999})
        self.assertEqual(raised.exception.status_code, 404)

    def test_generate_adds_announcement_and_template_context(self):
        with patch.object(
            bizplan_service.repo,
            "get_announcement",
            return_value={"policy_id": 7, "raw_content": "시장성 40점"},
        ), patch.object(
            bizplan_service.repo, "get_policy", return_value={"title": "예비창업패키지"}
        ), patch.object(
            bizplan_service,
            "generate_business_plan",
            return_value={"sections": [], "summary": "요약", "llmUsed": True},
        ) as generate:
            bizplan_service.generate({
                "announcementId": 3,
                "targetProgram": "잘못된 이름",
                "templateFields": ["개발 동기"],
                "startupStatus": "예비창업자",
                "coreFeatures": "발주 추천",
                "revenueModel": "월 구독",
            })
        payload = generate.call_args[0][0]
        self.assertEqual(payload["targetProgram"], "예비창업패키지")
        self.assertEqual(payload["announcementCriteria"], "시장성 40점")
        self.assertEqual(payload["templateFields"], ["개발 동기"])
        self.assertEqual(payload["coreFeatures"], "발주 추천")

    def test_generate_without_announcement_keeps_template_context(self):
        with patch.object(bizplan_service.repo, "get_announcement") as announcement, patch.object(
            bizplan_service, "generate_business_plan",
            return_value={"sections": [], "summary": "요약", "llmUsed": True},
        ) as generate:
            bizplan_service.generate({"templateFields": ["시장 분석"]})
        payload = generate.call_args[0][0]
        self.assertEqual(payload["announcementCriteria"], "")
        self.assertEqual(payload["templateFields"], ["시장 분석"])
        announcement.assert_not_called()

    def test_generate_passes_authenticated_name_to_template_analysis(self):
        with patch.object(bizplan_service.repo, "get_user", return_value={"name": "신대호"}), patch.object(
            bizplan_service, "generate_business_plan",
            return_value={"sections": [], "summary": "요약", "llmUsed": True},
        ) as generate:
            bizplan_service.generate({"templateFields": ["신청자 성명 [유형: metadata]"]}, user_id=7)
        self.assertEqual(generate.call_args[0][0]["applicantName"], "신대호")

    def test_generate_forwards_reviewed_sections(self):
        body = BusinessPlanRequest.model_validate({
            "reviewedSections": [{"key": "section_1", "label": "시장 분석", "content": "고객 조사 20건"}],
        }).model_dump()
        with patch.object(
            bizplan_service, "generate_business_plan",
            return_value={"sections": [], "summary": "요약", "llmUsed": True},
        ) as generate:
            bizplan_service.generate(body)
        self.assertEqual(generate.call_args[0][0]["reviewedSections"][0]["content"], "고객 조사 20건")

    def test_evaluate_adds_announcement_and_template_criteria(self):
        with patch.object(
            bizplan_service.repo,
            "get_announcement",
            return_value={"policy_id": 7, "raw_content": "실현가능성 30점"},
        ), patch.object(
            bizplan_service.repo, "get_policy", return_value={"title": "공고"}
        ), patch.object(
            bizplan_service,
            "evaluate_business_plan",
            return_value={"overallScore": 50, "overallComment": "보완", "sections": [], "llmUsed": True},
        ) as evaluate:
            bizplan_service.evaluate({
                "announcementId": 3,
                "templateFields": ["개발 동기", "목표시장"],
                "sections": [],
            })
        payload = evaluate.call_args[0][0]
        self.assertEqual(payload["announcementCriteria"], "실현가능성 30점")
        self.assertIn("개발 동기", payload["templateCriteria"])

    def test_without_announcement_uses_uploaded_or_default_template(self):
        result = {"overallScore": 50, "overallComment": "보완", "sections": [], "llmUsed": True}
        with patch.object(bizplan_service.repo, "get_announcement") as announcement, patch.object(
            bizplan_service, "evaluate_business_plan", return_value=result
        ) as evaluate:
            bizplan_service.evaluate({"sections": [], "templateFields": ["시장 분석"]})
            uploaded = evaluate.call_args[0][0]
            self.assertEqual(uploaded["announcementCriteria"], "")
            self.assertIn("시장 분석", uploaded["templateCriteria"])

            bizplan_service.evaluate({"sections": []})
            default = evaluate.call_args[0][0]
            self.assertEqual(default["announcementCriteria"], "")
            self.assertIn("기본 PSST", default["templateCriteria"])
            announcement.assert_not_called()

    def test_oversized_template_is_rejected_before_llm_call(self):
        body = {
            "fileName": "form.hwpx",
            "contentBase64": base64.b64encode(b"x" * (4 * 1024 * 1024 + 1)).decode(),
        }
        with patch.object(bizplan_service, "inspect_business_plan_template") as inspect:
            with self.assertRaises(Exception) as raised:
                bizplan_service.inspect_template(body)
        self.assertEqual(raised.exception.status_code, 413)
        inspect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
