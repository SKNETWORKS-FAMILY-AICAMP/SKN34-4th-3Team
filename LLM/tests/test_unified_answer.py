import asyncio

import pytest

from src.rag.answer import UnifiedAnswerResult, fallback_answer, generate_unified_answer
from tests.fakes import FakeStructuredChatModel


def test_unified_answer_uses_structured_output_and_valid_sources() -> None:
    model = FakeStructuredChatModel(
        {
            UnifiedAnswerResult: {
                "answer": "정책 문서에 따르면 지원 대상입니다.",
                "status": "success",
                "cited_source_numbers": [2, 2],
            }
        }
    )

    result = asyncio.run(
        generate_unified_answer(
            model,  # type: ignore[arg-type]
            query="지원 대상은?",
            route="policy",
            personalized=False,
            user_context=None,
            route_context={"documents": [{"title": "정책"}]},
            status="success",
            source_count=2,
        )
    )

    assert result.status == "success"
    assert result.cited_source_numbers == [2]
    assert "출처 번호는 cited_source_numbers에만 기록" in model.last_prompt_text
    assert "source_id·문서 ID·조문 번호는 인용 번호가 아닙니다" in model.last_prompt_text
    assert "기계적인 제목을 붙이지 마세요" in model.last_prompt_text
    assert "이해를 돕기 위해 예를 들면" in model.last_prompt_text
    assert "조건부 사례를 반드시 한 문단에 포함하세요" in model.last_prompt_text
    assert "조건을 되풀이하는 사례는 피하고" in model.last_prompt_text
    assert "내부 상태 값을 쓰지 마세요" in model.last_prompt_text


def test_unified_answer_rejects_invented_source_number() -> None:
    model = FakeStructuredChatModel(
        {
            UnifiedAnswerResult: {
                "answer": "근거 답변",
                "status": "success",
                "cited_source_numbers": [3],
            }
        }
    )

    with pytest.raises(ValueError, match="unavailable source"):
        asyncio.run(
            generate_unified_answer(
                model,  # type: ignore[arg-type]
                query="질문",
                route="tax",
                personalized=False,
                user_context=None,
                route_context={"evidence": []},
                status="success",
                source_count=1,
            )
        )


def test_unified_answer_treats_conversation_as_context_not_evidence() -> None:
    model = FakeStructuredChatModel(
        {
            UnifiedAnswerResult: {
                "answer": "현재 계산 결과를 기준으로 답변합니다.",
                "status": "success",
                "cited_source_numbers": [],
            }
        }
    )

    asyncio.run(
        generate_unified_answer(
            model,  # type: ignore[arg-type]
            query="가족이 두 명이면?",
            standalone_query="월급 320만원이고 가족이 두 명일 때 세금은?",
            conversation_history=[
                {"role": "user", "content": "월급은 320만원이야"},
                {"role": "assistant", "content": "이전 답변"},
            ],
            route="tax",
            personalized=False,
            user_context=None,
            route_context={"calculation_result": {"tax": "10000"}},
            status="success",
            source_count=0,
        )
    )

    assert "월급은 320만원이야" in model.last_prompt_text
    assert "증거가 아닙니다" in model.last_prompt_text


def test_unified_answer_prompt_uses_only_compacted_recent_history() -> None:
    model = FakeStructuredChatModel(
        {
            UnifiedAnswerResult: {
                "answer": "최근 문맥을 반영한 답변",
                "status": "success",
                "cited_source_numbers": [],
            }
        }
    )
    history = [
        message
        for index in range(7)
        for message in (
            {"role": "user", "content": f"오래된질문-{index}"},
            {"role": "assistant", "content": f"최근답변-{index}"},
        )
    ]

    asyncio.run(
        generate_unified_answer(
            model,  # type: ignore[arg-type]
            query="이어서 알려줘",
            conversation_history=history,
            route="tax",
            personalized=False,
            user_context=None,
            route_context={},
            status="success",
            source_count=0,
        )
    )

    assert "오래된질문-0" not in model.last_prompt_text
    assert "오래된질문-2" in model.last_prompt_text
    assert "최근답변-6" in model.last_prompt_text


def test_missing_context_fallback_names_required_fields() -> None:
    result = fallback_answer(
        "need_more_info",
        missing_user_context=["창업일", "업종"],
    )

    assert result.status == "need_more_info"
    assert "창업일" in result.answer
    assert "업종" in result.answer
