import asyncio

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src.core.config import Settings
from src.data import get_rag_chunks
from src.features import build_mock_vector_index
from src.rag.contracts import EligibilityDecision
from src.rag.guardrails import INSUFFICIENT_EVIDENCE_ANSWER, RagInputError
from src.rag.service import RagService
from tests.fakes import make_grounded_fake_model


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "langsmith_tracing": False,
        "min_relevance_score": 0.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_grounded_answer_contains_sources() -> None:
    index = build_mock_vector_index(DeterministicFakeEmbedding(size=32))
    llm = make_grounded_fake_model(answer="근거 기반 답변입니다. [출처 1]")
    service = RagService(
        vector_search=index,
        llm_factory=lambda: llm,
        settings=make_settings(),
    )

    result = asyncio.run(
        service.answer(get_rag_chunks()[0]["content"], policy_id=101, top_k=2)
    )

    assert result.grounded is True
    assert result.answer == "근거 기반 답변입니다. [출처 1]"
    assert result.sources
    assert all(source.policy_id == 101 for source in result.sources)


def test_no_search_results_returns_guardrail_answer_without_creating_llm() -> None:
    class EmptyVectorSearch:
        def add_chunks(self, _chunks: list) -> list[str]:
            return []

        def search(self, *_args: object, **_kwargs: object) -> list:
            return []

    llm_factory_calls = 0

    def llm_factory() -> FakeListChatModel:
        nonlocal llm_factory_calls
        llm_factory_calls += 1
        return FakeListChatModel(responses=["호출되면 안 됨"])

    service = RagService(
        vector_search=EmptyVectorSearch(),
        llm_factory=llm_factory,
        settings=make_settings(),
    )

    result = asyncio.run(service.answer("관련 지원 정책을 알려줘"))

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.grounded is False
    assert result.sources == ()
    assert llm_factory_calls == 0


def test_low_score_result_does_not_call_llm() -> None:
    class LowScoreVectorSearch:
        def add_chunks(self, _chunks: list) -> list[str]:
            return []

        def search(self, *_args: object, **_kwargs: object) -> list:
            result = get_rag_chunks()[0].copy()
            result["score"] = 0.1
            return [result]

    llm = FakeListChatModel(responses=["호출되면 안 됨"])
    service = RagService(
        vector_search=LowScoreVectorSearch(),
        llm_factory=lambda: llm,
        settings=make_settings(min_relevance_score=0.5),
    )

    result = asyncio.run(service.answer("낮은 관련성 질문", policy_id=101))

    assert result.grounded is False
    assert llm.i == 0


def test_backend_decision_is_returned_unchanged() -> None:
    index = build_mock_vector_index(DeterministicFakeEmbedding(size=32))
    decision = EligibilityDecision(
        eligible=True,
        reasons=("연령 조건 충족", "지역 조건 충족"),
    )
    service = RagService(
        vector_search=index,
        llm_factory=lambda: make_grounded_fake_model(
            answer="판정 근거 설명 [출처 1]"
        ),
        settings=make_settings(),
    )

    result = asyncio.run(
        service.answer(
            get_rag_chunks()[0]["content"],
            policy_id=101,
            decision=decision,
        )
    )

    assert result.decision is decision
    assert result.decision.eligible is True
    assert result.decision.reasons == ("연령 조건 충족", "지역 조건 충족")


def test_invalid_top_k_is_rejected_instead_of_using_default() -> None:
    service = RagService(
        vector_search=build_mock_vector_index(DeterministicFakeEmbedding(size=16)),
        llm_factory=lambda: FakeListChatModel(responses=["호출되면 안 됨"]),
        settings=make_settings(),
    )

    with pytest.raises(RagInputError, match="top_k must be between 1 and 20"):
        asyncio.run(service.answer("질문", top_k=0))


def test_out_of_scope_question_skips_search_and_llm() -> None:
    calls = {"search": 0, "llm": 0}

    class TrackingVectorSearch:
        def add_chunks(self, _chunks: list) -> list[str]:
            return []

        def search(self, *_args: object, **_kwargs: object) -> list:
            calls["search"] += 1
            return []

    def llm_factory() -> FakeListChatModel:
        calls["llm"] += 1
        return FakeListChatModel(responses=["호출되면 안 됨"])

    service = RagService(
        vector_search=TrackingVectorSearch(),
        llm_factory=llm_factory,
        settings=make_settings(),
    )

    result = asyncio.run(service.answer("오늘 서울 날씨가 어때?"))

    assert result.answer == "그 질문에는 답변할 수 없습니다"
    assert result.grounded is False
    assert result.sources == ()
    assert calls == {"search": 0, "llm": 0}


def test_invalid_generated_citation_returns_safe_fallback() -> None:
    service = RagService(
        vector_search=build_mock_vector_index(DeterministicFakeEmbedding(size=16)),
        llm_factory=lambda: make_grounded_fake_model(cited_source_numbers=[99]),
        settings=make_settings(invalid_generation_answer="안전한 대체 답변"),
    )

    result = asyncio.run(
        service.answer(get_rag_chunks()[0]["content"], policy_id=101)
    )

    assert result.answer == "안전한 대체 답변"
    assert result.grounded is False
    assert result.sources == ()
    assert result.guardrail_reason == "generation_validation_failed"


def test_only_cited_prompt_chunk_is_returned_as_source() -> None:
    first_chunk = get_rag_chunks()[0].copy()
    second_chunk = get_rag_chunks()[1].copy()
    first_chunk["score"] = 0.9
    second_chunk["score"] = 0.8

    class OrderedVectorSearch:
        def add_chunks(self, _chunks: list) -> list[str]:
            return []

        def search(self, *_args: object, **_kwargs: object) -> list:
            return [first_chunk, second_chunk]

    service = RagService(
        vector_search=OrderedVectorSearch(),
        llm_factory=lambda: make_grounded_fake_model(cited_source_numbers=[2]),
        settings=make_settings(),
    )

    result = asyncio.run(service.answer("지원 정책의 신청 기간을 알려줘"))

    assert result.grounded is True
    assert len(result.sources) == 1
    assert result.sources[0].chunk_id == second_chunk["chunk_id"]
