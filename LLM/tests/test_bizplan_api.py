"""사업계획서 API(/rag/business-plan*)와 영수증 OCR→Vision 대체 경로의 HTTP 계약."""

from pathlib import Path

import pytest

from src.features.receipt_ocr import OcrLine, OcrResult
from src.rag.backend_tasks import (
    BusinessPlanEvaluation,
    BusinessPlanGeneration,
    ReceiptExtractionGeneration,
)
from src.rag.bizplan_coach import BizplanCoachResult
from src.serving import rag_routes
from tests.fakes import FakeStructuredChatModel
from tests.test_rag_api import build_client

PSST_SECTIONS = [
    {"key": "problem", "label": "Problem · 문제인식", "content": "문제 설명"},
    {"key": "solution", "label": "Solution · 실현가능성", "content": "해결 방안"},
    {"key": "scaleUp", "label": "Scale-up · 성장전략", "content": "성장 전략"},
    {"key": "team", "label": "Team · 팀구성", "content": "팀 소개"},
]


# ---- 초안 생성 ----


def test_business_plan_follows_pasted_template(tmp_path: Path) -> None:
    template_sections = [
        {"key": "s1", "label": "1. 창업아이템 개요", "content": "개요"},
        {"key": "s2", "label": "2. 시장분석", "content": "시장"},
    ]
    model = FakeStructuredChatModel(
        {BusinessPlanGeneration: {"sections": template_sections, "summary": "요약"}}
    )
    client = build_client(tmp_path / "index.json", llm_factory=lambda: model)
    template = "1. 창업아이템 개요\n2. 시장분석"

    response = client.post("/rag/business-plan", json={"templateText": template})

    assert response.status_code == 200
    assert [s["label"] for s in response.json()["sections"]] == [
        "1. 창업아이템 개요",
        "2. 시장분석",
    ]
    # 양식 원문이 모델 지시문에 그대로 들어가야 그 항목 구성을 따른다.
    assert "1. 창업아이템 개요" in model.last_prompt_text


def test_business_plan_model_failure_is_upstream_error(tmp_path: Path) -> None:
    def broken_factory() -> FakeStructuredChatModel:
        raise TimeoutError("sensitive timeout detail")

    client = build_client(tmp_path / "index.json", llm_factory=broken_factory)

    response = client.post("/rag/business-plan", json={"businessName": "x"})

    assert response.status_code == 504
    assert "sensitive" not in response.text


# ---- 예비진단 ----


def test_business_plan_evaluate_returns_scores(tmp_path: Path) -> None:
    model = FakeStructuredChatModel(
        {
            BusinessPlanEvaluation: {
                "overall_score": 72,
                "overall_comment": "전반적으로 양호",
                "sections": [
                    {
                        "key": "problem",
                        "label": "Problem · 문제인식",
                        "score": 80,
                        "strengths": "문제가 구체적",
                        "improvements": "근거 수치 보완",
                    }
                ],
            }
        }
    )
    client = build_client(tmp_path / "index.json", llm_factory=lambda: model)

    response = client.post("/rag/business-plan-evaluate", json={"sections": PSST_SECTIONS})

    assert response.status_code == 200
    body = response.json()
    assert body["overallScore"] == 72
    assert body["sections"][0] == {
        "key": "problem",
        "label": "Problem · 문제인식",
        "score": 80,
        "strengths": "문제가 구체적",
        "improvements": "근거 수치 보완",
    }
    assert body["llmUsed"] is True


# ---- 아이디어 어시스턴트 ----


def test_bizplan_coach_answers_in_scope_question(tmp_path: Path) -> None:
    model = FakeStructuredChatModel(
        {BizplanCoachResult: {"in_scope": True, "redirect": "none", "answer": "타깃을 좁혀 보세요."}}
    )
    client = build_client(tmp_path / "index.json", llm_factory=lambda: model)

    response = client.post(
        "/rag/business-plan-coach",
        json={"question": "고객을 어떻게 정할까요?", "sections": PSST_SECTIONS[:1]},
    )

    assert response.status_code == 200
    assert response.json() == {"answer": "타깃을 좁혀 보세요.", "inScope": True, "redirect": "none"}


@pytest.mark.parametrize(
    ("redirect", "expected_answer"),
    [
        ("tax", "이 질문은 AI 세무 Assistant에서 확인해 주세요."),
        ("policy", "이 질문은 공고지원 AI에서 확인해 주세요."),
    ],
)
def test_bizplan_coach_redirects_out_of_scope_questions(
    tmp_path: Path, redirect: str, expected_answer: str
) -> None:
    # 범위 밖 질문은 모델이 쓴 답변 대신 정해진 안내 문구로 바꿔 돌려준다.
    model = FakeStructuredChatModel(
        {BizplanCoachResult: {"in_scope": False, "redirect": redirect, "answer": "모델이 쓴 답"}}
    )
    client = build_client(tmp_path / "index.json", llm_factory=lambda: model)

    response = client.post("/rag/business-plan-coach", json={"question": "부가세 신고는?"})

    assert response.status_code == 200
    assert response.json() == {"answer": expected_answer, "inScope": False, "redirect": redirect}


# ---- 영수증: OCR 결과로 아무것도 못 채우면 Vision으로 다시 읽는다 ----


def test_receipt_falls_back_to_vision_when_ocr_text_yields_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    garbage = OcrResult(
        lines=[OcrLine(1, "SHS y OF 7 aed Qn He", 40.0, 0, 0, 10, 10)],
        image_width=100,
        image_height=100,
    )
    monkeypatch.setattr(rag_routes, "run_ocr", lambda _data: garbage)

    async def empty_from_ocr(_llm, *, ocr_text: str) -> ReceiptExtractionGeneration:
        return ReceiptExtractionGeneration()

    async def filled_from_vision(_llm, *, image_data_url: str) -> ReceiptExtractionGeneration:
        return ReceiptExtractionGeneration(date="2026-07-27", amount=29210)

    monkeypatch.setattr(rag_routes, "extract_receipt_from_ocr", empty_from_ocr)
    monkeypatch.setattr(rag_routes, "extract_receipt", filled_from_vision)
    client = build_client(tmp_path / "index.json")

    response = client.post(
        "/ocr/receipt",
        files={"image": ("receipt.jpg", b"fake-jpeg", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "vision"
    assert body["amount"] == 29210
    assert body["ocrConfidence"] is None


def test_receipt_keeps_ocr_result_when_it_found_something(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    readable = OcrResult(
        lines=[OcrLine(1, "결제금액 29,210", 90.0, 0, 0, 10, 10)],
        image_width=100,
        image_height=100,
    )
    monkeypatch.setattr(rag_routes, "run_ocr", lambda _data: readable)

    async def filled_from_ocr(_llm, *, ocr_text: str) -> ReceiptExtractionGeneration:
        return ReceiptExtractionGeneration(amount=29210)

    async def vision_must_not_run(_llm, *, image_data_url: str) -> ReceiptExtractionGeneration:
        raise AssertionError("OCR로 값을 채웠으면 Vision을 부르지 않아야 한다")

    monkeypatch.setattr(rag_routes, "extract_receipt_from_ocr", filled_from_ocr)
    monkeypatch.setattr(rag_routes, "extract_receipt", vision_must_not_run)
    client = build_client(tmp_path / "index.json")

    response = client.post(
        "/ocr/receipt",
        files={"image": ("receipt.jpg", b"fake-jpeg", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "ocr_llm"
    assert body["ocrConfidence"] == 90.0
