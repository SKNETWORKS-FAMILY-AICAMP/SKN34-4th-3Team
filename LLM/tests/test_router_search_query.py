import asyncio

import pytest
from pydantic import ValidationError

from src.core.config import Settings
from src.rag import graph as graph_module
from src.rag.answer import UnifiedAnswerResult
from src.rag.discovery import build_policy_initial_search_queries
from src.rag.graph import RouteDecision, build_graph, route_question
from src.rag.tax import (
    TaxEvidenceDecision,
    TaxIntentDecision,
    TaxNextQuery,
    build_tax_initial_search_queries,
)
from tests.fakes import FakeStructuredChatModel


class RecordingSearch:
    def __init__(self, *, tax=False):
        self.queries = []
        self.document = {
            "chunk_id": "tax-1" if tax else "policy-1",
            "policy_id": None if tax else 1,
            "title": "세액감면" if tax else "시설자금 융자",
            "content": "음식점업 감면 요건" if tax else "제조업 시설자금 융자를 지원합니다.",
            "source": "db://test/1", "page": 1, "score": 0.9,
        }

    def search_stages(self, query, **kwargs):
        self.queries.append(query)
        docs = [self.document]
        return docs, docs, docs


def router_model(route, search_query):
    return FakeStructuredChatModel({RouteDecision: {
        "route": route, "personalized": False, "search_query": search_query,
    }})


@pytest.fixture
def answer_inputs(monkeypatch):
    calls = []

    async def generate(_llm, **kwargs):
        calls.append(kwargs)
        return UnifiedAnswerResult(
            status=kwargs["status"], answer="확인된 근거를 안내합니다.",
            cited_source_numbers=[1] if kwargs["source_count"] else [],
        )

    monkeypatch.setattr(graph_module, "generate_unified_answer", generate)
    return calls


@pytest.mark.parametrize("payload", [
    {"route": "policy", "personalized": False},
    {"route": "policy", "personalized": False, "search_query": None},
    {"route": "tax", "personalized": False, "search_query": "  "},
    {"route": "out_of_scope", "personalized": False, "search_query": "지원사업"},
])
def test_router_rejects_missing_or_inappropriate_search_queries(payload):
    with pytest.raises(ValidationError):
        RouteDecision.model_validate(payload)


def test_router_rewrites_contextualized_question_in_the_same_call():
    original = "그거 제조업도 가능해?"
    standalone = "서울 청년 시설자금 융자에 제조업도 신청할 수 있나요?"
    compact = "서울 청년 제조업 시설자금 융자 신청 대상"
    model = router_model("policy", "  " + compact + "  ")

    update = asyncio.run(route_question({
        "query": original, "standalone_query": standalone, "category": "policy",
    }, llm=model))

    assert model.call_count == 1
    assert "질문: " + standalone in model.last_prompt_text
    assert update["router_search_query"] == compact
    assert "query" not in update and "standalone_query" not in update


def test_policy_retrieval_uses_compact_query_and_keeps_full_intent(answer_inputs):
    original = (
        "서울에 사는 청년이고 제조업 개인사업자로 개업한 지 2년입니다. "
        "업력 3년 이내 시설자금 융자를 찾아주세요. 보조금은 제외하고 "
        "어떻게 신청하는지도 알려주세요."
    )
    compact = "서울 청년 제조업 개인사업자 업력 3년 이내 시설자금 융자 보조금 제외 신청 방법"
    model = router_model("policy", compact)
    search = RecordingSearch()
    rerank_queries = []

    def rerank(query, documents, top_n):
        rerank_queries.append(query)
        return documents[:top_n]

    result = asyncio.run(build_graph(
        model, policy_search=search, rerank=rerank,
        settings=Settings(_env_file=None),
    ).ainvoke({"query": original}))

    assert set(search.queries) == set(build_policy_initial_search_queries(compact))
    assert rerank_queries == [original]
    assert result["query"] == result["standalone_query"] == original
    assert result["router_search_query"] == result["search_query"] == compact
    assert result["missing_information"] == ["신청 방법"]
    assert answer_inputs[0]["query"] == original
    assert answer_inputs[0]["standalone_query"] == original
    assert model.call_count == 1  # 재작성을 위한 별도 모델 호출이 없다.


def test_tax_initial_query_is_rewritten_but_intent_and_followup_are_preserved(answer_inputs):
    original = "저는 29살이고 서울에서 음식점을 창업했어요. 청년창업 세액감면 업종 요건을 알려주세요."
    compact = "청년창업 세액감면 서울 음식점업 29세 업종 요건"
    next_query = "청년창업 세액감면 음식점업 제외 업종"
    model = router_model("tax", compact)
    search = RecordingSearch(tax=True)
    intent_queries, rerank_queries = [], []
    evidence_calls = 0

    async def intent(state):
        intent_queries.append(state["standalone_query"])
        return TaxIntentDecision(calculation_required=False, calculation_type=None, reason="법령 설명")

    async def evidence(state):
        nonlocal evidence_calls
        evidence_calls += 1
        return TaxEvidenceDecision(
            sufficient=evidence_calls == 2,
            missing_information=[] if evidence_calls == 2 else ["제외 업종"],
            missing_user_context=[], calculation_required=False,
            resolved_category=None, resolved_region=None, resolved_rate_percent=None,
            cited_source_numbers=[1], reason="test",
        )

    async def followup(state):
        return TaxNextQuery(query=next_query, reason="제외 업종 확인")

    def rerank(query, documents, top_n):
        rerank_queries.append(query)
        return documents[:top_n]

    result = asyncio.run(build_graph(
        model, tax_search=search, rerank=rerank,
        tax_intent_classifier=intent, tax_evidence_evaluator=evidence,
        tax_next_query_generator=followup,
        settings=Settings(_env_file=None, tax_cache_enabled=False),
    ).ainvoke({"query": original}))

    assert set(search.queries[:-1]) == set(build_tax_initial_search_queries(compact))
    assert search.queries[-1] == next_query
    assert intent_queries == [original]
    assert rerank_queries == [original, next_query]
    assert result["router_search_query"] == compact
    assert result["search_query"] == next_query
    assert answer_inputs[0]["query"] == original
    assert model.call_count == 1


def test_notice_callback_receives_rewritten_search_query_without_overwriting_question():
    original = "서울에서 지금 신청할 수 있는 청년 창업 공고의 마감일을 알려주세요."
    compact = "서울 청년 창업 현재 모집 공고 신청 마감일"
    received = []

    def notice(state):
        received.append(state)
        return []

    model = router_model("notice", compact)
    result = asyncio.run(build_graph(model, notice_search=notice).ainvoke({"query": original}))

    assert received[0]["query"] == original
    assert received[0]["search_query"] == compact
    assert result["search_query"] == compact
    assert model.call_count == 1
