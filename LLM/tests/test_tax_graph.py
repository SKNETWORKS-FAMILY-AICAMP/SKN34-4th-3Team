import asyncio
import threading
import time

import pytest

import src.rag.graph as graph_module
from src.core.config import Settings
from src.data.contracts import VectorSearchResult
from src.rag.graph import (
    ContextualizedQuestion,
    RouteDecision,
    _answer_context,
    build_graph,
)
from src.rag.answer import UnifiedAnswerResult
from src.rag.tax import (
    TaxCalculationError,
    TaxCalculationInputPlan,
    TaxCalculationPlan,
    TaxEvidenceDecision,
    TaxIntentDecision,
    TaxNextQuery,
    _format_evidence,
    _format_evidence_for_evaluation,
    build_tax_initial_search_queries,
    calculate_tax_plan,
    classify_tax_intent,
    evaluate_tax_evidence,
    generate_tax_calculation_inputs,
    generate_tax_calculation_plan,
    generate_tax_next_query,
    normalize_tax_search_query,
    parse_exact_legal_query,
    resolve_legal_reference,
    resolve_missing_information_query,
)
from src.serving.tax_calculators_docstring import calculate_tax as serving_calculate_tax
from tests.fakes import FakeStructuredChatModel


def _tax_document(chunk_id: str, content: str) -> VectorSearchResult:
    return {
        "chunk_id": chunk_id,
        "policy_id": None,
        "title": "조세특례제한법",
        "source": f"db://tax_documents/{chunk_id}",
        "page": 1,
        "content": content,
        "score": 0.8,
    }


class SequentialTaxSearch:
    def __init__(self, results: list[list[VectorSearchResult]]) -> None:
        self.results = results
        self.call_count = 0
        self.queries: list[str] = []

    def search_stages(
        self,
        query: str,
        *,
        policy_id: int | None,
        source_types: tuple[str, ...] | None = None,
        top_k: int,
    ) -> tuple[
        list[VectorSearchResult],
        list[VectorSearchResult],
        list[VectorSearchResult],
    ]:
        assert source_types == ("tax_document",)
        self.queries.append(query)
        index = min(self.call_count, len(self.results) - 1)
        self.call_count += 1
        result = self.results[index][:top_k]
        return result, result, result


class ParallelTaxSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def search_stages(
        self,
        query: str,
        *,
        policy_id: int | None,
        source_types: tuple[str, ...] | None = None,
        top_k: int,
    ) -> tuple[
        list[VectorSearchResult],
        list[VectorSearchResult],
        list[VectorSearchResult],
    ]:
        assert source_types == ("tax_document",)
        with self.lock:
            self.queries.append(query)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            document = _tax_document(f"tax-{len(self.queries)}", query)
        time.sleep(0.03)
        with self.lock:
            self.active -= 1
        result = [document][:top_k]
        return result, result, result


def _router_llm(
    *,
    calculation_required: bool = False,
    calculation_type: str | None = None,
    cited_source_numbers: list[int] | None = None,
    answer: str = "누적 법령 근거 기반 답변",
    answer_status: str = "success",
) -> FakeStructuredChatModel:
    return FakeStructuredChatModel(
        {
            RouteDecision: {"route": "tax", "personalized": False},
            TaxIntentDecision: {
                "calculation_required": calculation_required,
                "calculation_type": calculation_type,
                "reason": "test",
            },
            UnifiedAnswerResult: {
                "answer": answer,
                "status": answer_status,
                "cited_source_numbers": (
                    [1] if cited_source_numbers is None else cited_source_numbers
                ),
            },
        }
    )


def _identity_rerank(
    _query: str,
    documents: list[VectorSearchResult],
    top_n: int,
) -> list[VectorSearchResult]:
    return documents[:top_n]


def _decision(
    *,
    sufficient: bool,
    missing_information: list[str] | None = None,
    missing_user_context: list[str] | None = None,
    calculation_required: bool = False,
    resolved_calculation_inputs: dict[str, object] | None = None,
    cited_source_numbers: list[int] | None = None,
) -> TaxEvidenceDecision:
    resolved = resolved_calculation_inputs or {}
    return TaxEvidenceDecision(
        sufficient=sufficient,
        missing_information=missing_information or [],
        missing_user_context=missing_user_context or [],
        calculation_required=calculation_required,
        resolved_category=resolved.get("category"),  # type: ignore[arg-type]
        resolved_region=resolved.get("region"),  # type: ignore[arg-type]
        resolved_rate_percent=(
            str(resolved["rate_percent"])
            if resolved.get("rate_percent") is not None
            else None
        ),
        cited_source_numbers=cited_source_numbers or [],
        reason="test",
    )


def test_tax_cache_miss_then_hit_skips_retrieval_and_evidence_llm() -> None:
    class FakeCache:
        def __init__(self) -> None:
            self.stored = False
            self.saved: list[tuple[list[int], list[str]]] = []

        def lookup(self, _question, _profile, _prior_evidence_ids=None):
            if self.stored:
                return [document], ["조세특례제한법 제6조"], None, None, "full"
            return [], [], [0.1] * 1536, None, None

        def save(self, _question, _profile, documents, queries, _embedding, **_kwargs):
            self.saved.append(([item["id"] for item in documents], queries))
            self.stored = True

    document = {**_tax_document("tax-323", "청년 창업 감면 요건"), "id": 323}
    search = SequentialTaxSearch([[document]])
    cache = FakeCache()
    evaluator_calls = 0

    async def evaluate(_state):
        nonlocal evaluator_calls
        evaluator_calls += 1
        return _decision(sufficient=True)

    graph = build_graph(
        _router_llm(), tax_search=search, rerank=_identity_rerank,
        tax_evidence_evaluator=evaluate, tax_cache=cache,  # type: ignore[arg-type]
        settings=Settings(_env_file=None, tax_cache_enabled=True),
    )
    request = {"query": "청년 창업 세액감면 대상인지 알려줘", "category": "tax"}
    first = asyncio.run(graph.ainvoke(request))
    search_count = search.call_count
    second = asyncio.run(graph.ainvoke(request))

    assert first["answer_status"] == second["answer_status"] == "success"
    assert cache.saved and cache.saved[0][0] == [323]
    assert cache.saved[0][1]
    assert search.call_count == search_count
    assert evaluator_calls == 1
    assert second["tax_cache_hit"] is True


def test_tax_retrieval_cache_hit_still_runs_evidence_evaluator() -> None:
    document = {**_tax_document("tax-323", "청년 창업 감면 요건"), "id": 323}

    class RetrievalOnlyCache:
        def lookup(self, *_args):
            return [document], ["청년 창업 감면 대상"], [0.1] * 1536, None, "retrieval"

        def save(self, *_args, **_kwargs):
            pass

    search = SequentialTaxSearch([])
    evaluator_calls = 0

    async def evaluate(_state):
        nonlocal evaluator_calls
        evaluator_calls += 1
        return _decision(sufficient=True)

    result = asyncio.run(build_graph(
        _router_llm(), tax_search=search, rerank=_identity_rerank,
        tax_evidence_evaluator=evaluate, tax_cache=RetrievalOnlyCache(),  # type: ignore[arg-type]
        settings=Settings(_env_file=None, tax_cache_enabled=True),
    ).ainvoke({
        "query": "제 조건이면 청년 창업 세액감면 대상인지 알려주세요",
        "category": "tax",
        "user_context": {"age": 29, "region": "경기"},
    }))

    assert result["answer_status"] == "success"
    assert result["tax_cache_retrieval_only"] is True
    assert result["tax_cache_decision_hit"] is False
    assert search.call_count == 0
    assert evaluator_calls == 1


def test_tax_cache_disabled_preserves_existing_retrieval() -> None:
    class NoLookupCache:
        def lookup(self, *_args):
            raise AssertionError("cache must be off")

    search = SequentialTaxSearch([[_tax_document("tax-1", "청년 창업 감면 요건")]])

    async def evaluate(_state):
        return _decision(sufficient=True)

    result = asyncio.run(build_graph(
        _router_llm(), tax_search=search, rerank=_identity_rerank,
        tax_evidence_evaluator=evaluate, tax_cache=NoLookupCache(),  # type: ignore[arg-type]
        settings=Settings(_env_file=None, tax_cache_enabled=False),
    ).ainvoke({"query": "청년 창업 세액감면 대상", "category": "tax"}))
    assert result["answer_status"] == "success"
    assert search.call_count > 0


def test_tax_cache_reuses_insufficient_evidence_decision() -> None:
    class CountingCache:
        def __init__(self) -> None:
            self.entry = None
            self.saves = 0

        def lookup(self, *_args):
            if self.entry is None:
                return [], [], [0.1] * 1536, None, None
            documents, queries, decision = self.entry
            return documents, queries, None, decision, "decision"

        def save(self, _question, _profile, documents, queries, _embedding, **kwargs):
            self.saves += 1
            decision = kwargs.get("evidence_decision")
            if decision is not None:
                self.entry = (documents, queries, decision)

    document = {**_tax_document("tax-323", "부분 근거"), "id": 323}
    search = SequentialTaxSearch([[document]])
    cache = CountingCache()

    evaluator_calls = 0

    async def evaluate(_state):
        nonlocal evaluator_calls
        evaluator_calls += 1
        return _decision(sufficient=False, missing_information=["시행령 요건"])

    graph = build_graph(
        _router_llm(), tax_search=search, rerank=_identity_rerank,
        tax_evidence_evaluator=evaluate, tax_cache=cache,  # type: ignore[arg-type]
        settings=Settings(_env_file=None, tax_cache_enabled=True, tax_max_hops=1),
    )
    request = {"query": "청년 창업 세액감면 대상", "category": "tax"}
    first = asyncio.run(graph.ainvoke(request))
    second = asyncio.run(graph.ainvoke(request))

    assert first["answer_status"] == second["answer_status"] == "insufficient_evidence"
    assert cache.saves == 1
    assert evaluator_calls == 1
    assert second["tax_cache_decision_hit"] is True


def test_tax_cache_does_not_save_no_result() -> None:
    class CountingCache:
        saves = 0

        def lookup(self, *_args):
            return [], [], None, None, None

        def save(self, *_args):
            self.saves += 1

    cache = CountingCache()
    search = SequentialTaxSearch([[]])
    result = asyncio.run(build_graph(
        _router_llm(), tax_search=search, rerank=_identity_rerank,
        tax_cache=cache,  # type: ignore[arg-type]
        settings=Settings(_env_file=None, tax_cache_enabled=True, tax_max_hops=1),
    ).ainvoke({"query": "청년 창업 세액감면 대상", "category": "tax"}))
    assert result["answer_status"] != "success"
    assert cache.saves == 0


def test_equivalent_tax_requests_use_same_normalized_search_query() -> None:
    first = normalize_tax_search_query("청년창업 세액감면 대상인지 알려줘")
    second = normalize_tax_search_query("청년창업 세액감면 대상인지 확인")

    assert first == second == "청년창업 세액감면 대상인지"
    conditioned = normalize_tax_search_query(
        "만 31세 서울 소프트웨어업 청년창업 세액감면 대상인지 알려주세요"
    )
    assert "만 31세" in conditioned
    assert "서울" in conditioned
    assert "소프트웨어업" in conditioned

    first_bundle = build_tax_initial_search_queries(first)
    second_bundle = build_tax_initial_search_queries(second)
    assert first_bundle == second_bundle
    assert len(first_bundle) == 5
    conditioned_bundle = build_tax_initial_search_queries(conditioned)
    assert all("만 31세" in query for query in conditioned_bundle)
    assert all("서울" in query for query in conditioned_bundle)
    assert all("소프트웨어업" in query for query in conditioned_bundle)


def test_independent_tax_question_skips_unrelated_history_contextualization() -> None:
    contextualizer_calls = 0

    async def contextualize(_state: object) -> ContextualizedQuestion:
        nonlocal contextualizer_calls
        contextualizer_calls += 1
        return ContextualizedQuestion(standalone_question="월급 소득세 질문")

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(sufficient=True)

    search = SequentialTaxSearch([[_tax_document("tax-1", "세액감면 요건")]])
    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=search,  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            question_contextualizer=contextualize,  # type: ignore[arg-type]
        ).ainvoke(
            {
                "query": "청년창업 세액감면 대상인지 확인",
                "category": "tax",
                "conversation_history": [
                    {"role": "user", "content": "월급 소득세는 얼마야?"},
                    {"role": "assistant", "content": "급여 조건이 필요합니다."},
                ],
            }
        )
    )

    assert contextualizer_calls == 0
    assert result["standalone_query"] == "청년창업 세액감면 대상인지 확인"
    assert set(search.queries) == set(
        build_tax_initial_search_queries("청년창업 세액감면 대상인지")
    )


@pytest.mark.parametrize(
    "question",
    [
        "기납부세액 80만원도 반영해줘.",
        "공제대상 가족은 본인 포함 2명이고 자녀는 없어.",
        "정보통신업으로 보고 기본 매출세액을 계산해줘.",
        "공제할 매입세액 150만원이고 다른 공제나 기납부세액은 없어.",
    ],
)
def test_tax_input_follow_up_uses_contextualization(question: str) -> None:
    assert graph_module._tax_question_needs_contextualization(question)


def test_independent_tax_calculation_question_skips_contextualization() -> None:
    assert not graph_module._tax_question_needs_contextualization(
        "직원 월급 280만원의 원천징수세액 알려줘."
    )


@pytest.mark.parametrize(
    ("question", "standalone_question"),
    [
        ("그럼 나는 대상인가요?", "청년창업 세액감면에서 나는 대상인가요?"),
        (
            "기납부세액 80만원도 반영해줘.",
            "앞서 계산한 부가세에 기납부세액 80만원을 반영해줘.",
        ),
    ],
)
def test_tax_follow_up_with_reference_still_uses_contextualization(
    question: str, standalone_question: str
) -> None:
    contextualizer_calls = 0

    async def contextualize(_state: object) -> ContextualizedQuestion:
        nonlocal contextualizer_calls
        contextualizer_calls += 1
        return ContextualizedQuestion(
            standalone_question=standalone_question
        )

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(sufficient=True)

    search = SequentialTaxSearch([[_tax_document("tax-1", "세액감면 요건")]])
    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=search,  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            question_contextualizer=contextualize,  # type: ignore[arg-type]
        ).ainvoke(
            {
                "query": question,
                "category": "tax",
                "conversation_history": [
                    {"role": "user", "content": "청년창업 감면 조건은?"},
                    {"role": "assistant", "content": "일반 조건입니다."},
                ],
            }
        )
    )

    assert contextualizer_calls == 1
    assert result["standalone_query"] == standalone_question
    assert search.queries[0] == standalone_question


def _input_plan_payload(
    calculation_inputs: dict[str, object],
    *,
    missing_required_inputs: list[str] | None = None,
    reason: str = "test",
) -> dict[str, object]:
    payload: dict[str, object] = {
        key: None
        for key in (
            "tax_base_krw",
            "tax_year",
            "monthly_salary_krw",
            "family_count",
            "child_count",
            "taxable_sales_supply_value_krw",
            "deductible_input_tax_krw",
            "tax_credit_krw",
            "prepaid_tax_krw",
            "penalty_tax_krw",
            "sales_amount_krw",
            "industry",
            "eligible_tax_krw",
            "startup_year",
            "age",
            "business_location",
            "first_startup",
            "base_amount",
        )
    }
    payload.update(calculation_inputs)
    for key in {
        "tax_base_krw",
        "monthly_salary_krw",
        "taxable_sales_supply_value_krw",
        "deductible_input_tax_krw",
        "tax_credit_krw",
        "prepaid_tax_krw",
        "penalty_tax_krw",
        "sales_amount_krw",
        "eligible_tax_krw",
        "base_amount",
    }:
        if payload[key] is not None:
            payload[key] = str(payload[key])
    payload["missing_required_inputs"] = missing_required_inputs or []
    payload["reason"] = reason
    return payload


def _input_plan(
    calculation_inputs: dict[str, object],
    *,
    missing_required_inputs: list[str] | None = None,
    reason: str = "test",
) -> TaxCalculationInputPlan:
    return TaxCalculationInputPlan.model_validate(
        _input_plan_payload(
            calculation_inputs,
            missing_required_inputs=missing_required_inputs,
            reason=reason,
        )
    )


def test_tax_single_hop_stops_when_evidence_is_sufficient() -> None:
    search = SequentialTaxSearch(
        [[_tax_document("tax-1", "청년창업 세액감면 요건")]]
    )

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(sufficient=True)

    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=search,  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            settings=Settings(_env_file=None),
        ).ainvoke({"query": "청년창업 세액감면이 뭐야?"})
    )

    assert search.call_count == 5
    assert result["evidence_sufficient"] is True
    assert result["hop_count"] == 1
    assert len(result["tax_retrieval_trace"]) == 1
    assert result["tax_retrieval_trace"][0]["query"] == "청년창업 세액감면이 뭐야?"
    assert result["tax_retrieval_trace"][0]["evidence_sufficient"] is True
    assert result["termination_reason"] == "evidence_sufficient"
    assert result["answer_status"] == "success"
    assert result["answer"] == "누적 법령 근거 기반 답변"
    assert result["answer_sources"][0]["chunk_id"] == "tax-1"


def test_tax_first_hop_retrieves_independent_facets_in_parallel() -> None:
    search = ParallelTaxSearch()
    rerank_calls: list[list[VectorSearchResult]] = []

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(sufficient=True)

    def rerank(
        _query: str,
        documents: list[VectorSearchResult],
        top_n: int,
    ) -> list[VectorSearchResult]:
        rerank_calls.append(documents)
        return documents[:top_n]

    model = _router_llm()
    result = asyncio.run(
        build_graph(
            model,
            tax_search=search,  # type: ignore[arg-type]
            rerank=rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            settings=Settings(_env_file=None),
        ).ainvoke(
            {"query": "청년창업 세액감면의 대상 요건, 감면율, 지역 조건, 적용 기간을 알려줘"}
        )
    )

    assert len(search.queries) == 5
    assert search.max_active > 1
    assert len(rerank_calls) == 1
    assert len(rerank_calls[0]) == 5
    assert result["hop_count"] == 1
    assert len(result["tax_retrieval_trace"][0]["initial_queries"]) == 5
    assert "같은 설명을 반복" in model.last_prompt_text


def test_tax_hop_search_timeout_stops_slow_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search = ParallelTaxSearch()
    monkeypatch.setattr(graph_module, "TAX_HOP_SEARCH_TIMEOUT_SECONDS", 0.01)
    started = time.perf_counter()

    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=search,  # type: ignore[arg-type]
            rerank=_identity_rerank,
            settings=Settings(_env_file=None),
        ).ainvoke({"query": "세액감면이 뭐야?"})
    )

    assert time.perf_counter() - started < 0.5
    assert result["hop_count"] == 1
    assert result["answer_status"] == "no_result"


def test_tax_answer_context_omits_only_same_article_duplicate_text() -> None:
    repeated = "청년창업 중소기업의 세액감면 요건과 적용 범위를 정한 법령 근거"
    first = _tax_document("tax-1", repeated)
    first.update(source_id=10, title="조세특례제한법 제6조")
    duplicate = _tax_document("tax-2", repeated)
    duplicate.update(source_id=10, title="조세특례제한법 제6조")
    other_article = _tax_document("tax-3", repeated)
    other_article.update(source_id=10, title="조세특례제한법 제30조")

    context = _answer_context(
        {"route": "tax", "reranked_docs": [first, duplicate, other_article]}
    )
    evidence = context["evidence"]

    assert evidence[0]["content"] == repeated
    assert evidence[1]["duplicate_of"] == 1
    assert "content" not in evidence[1]
    assert evidence[2]["content"] == repeated


def test_partial_tax_evidence_renumbers_selected_source_for_answer() -> None:
    documents = [
        _tax_document("tax-1", "관련 없는 조문"),
        _tax_document("tax-2", "관련 없는 해설"),
        _tax_document("tax-3", "청년창업 세액감면 대상 요건"),
    ]
    context = _answer_context(
        {
            "route": "tax",
            "reranked_docs": documents,
            "evidence_sufficient": False,
            "calculation_source_numbers": [3],
        }
    )

    assert len(context["evidence"]) == 1
    assert context["evidence"][0]["chunk_id"] == "tax-3"
    assert context["evidence"][0]["citation_number"] == 1


def test_tax_multi_hop_accumulates_new_evidence() -> None:
    search = SequentialTaxSearch(
        [
            *[
                [_tax_document("tax-1", "감면 대상 업종 확인 필요")]
                for _ in range(5)
            ],
            [_tax_document("tax-2", "음식점업의 감면 적용 요건")],
        ]
    )
    decisions = iter(
        [
            _decision(sufficient=False, missing_information=["업종 요건"]),
            _decision(sufficient=True),
        ]
    )

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return next(decisions)

    async def next_query(_state: object) -> TaxNextQuery:
        return TaxNextQuery(
            query="청년창업 세액감면 음식점업 요건",
            reason="업종 요건 필요",
        )

    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=search,  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            tax_next_query_generator=next_query,  # type: ignore[arg-type]
            settings=Settings(_env_file=None, tax_max_hops=3),
        ).ainvoke({"query": "27살 서울 음식점 창업 세액감면 대상이야?"})
    )

    assert result["hop_count"] == 2
    assert len(result["search_history"]) == 6
    assert result["search_history"][0] == "27살 서울 음식점 창업 세액감면 대상이야?"
    assert result["search_history"][-1] == "청년창업 세액감면 음식점업 요건"
    assert len(result["tax_retrieval_trace"]) == 2
    assert result["tax_retrieval_trace"][0]["evidence_sufficient"] is False
    assert result["tax_retrieval_trace"][1]["evidence_sufficient"] is True
    assert [doc["chunk_id"] for doc in result["reranked_docs"]] == [
        "tax-1",
        "tax-2",
    ]


def test_specific_missing_information_can_skip_next_query_llm() -> None:
    assert resolve_missing_information_query(
        "청년창업 세액감면 대상인가요?",
        ["대상 업종 요건"],
        search_history=["청년창업 세액감면 대상인가요?"],
    ) == "청년창업 세액감면 대상인가요? 대상 업종 요건"
    assert resolve_missing_information_query(
        "세액감면 대상인가요?",
        ["추가 법령"],
        search_history=[],
    ) is None


def test_explicit_reference_has_priority_over_next_query_generator() -> None:
    search = SequentialTaxSearch(
        [
            [_tax_document("tax-1", "조세특례제한법 제6조에 따른 감면")],
            [_tax_document("tax-2", "조세특례제한법 제6조 세부 요건")],
        ]
    )
    decisions = iter([_decision(sufficient=False), _decision(sufficient=True)])
    next_query_calls = 0

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return next(decisions)

    async def next_query(_state: object) -> TaxNextQuery:
        nonlocal next_query_calls
        next_query_calls += 1
        return TaxNextQuery(query="사용되면 안 됨", reason="test")

    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=search,  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            tax_next_query_generator=next_query,  # type: ignore[arg-type]
        ).ainvoke({"query": "세액감면 근거 알려줘"})
    )

    assert next_query_calls == 0
    assert result["search_history"][1] == "조세특례제한법 제6조"


def test_missing_article_takes_priority_over_unrelated_evidence_reference() -> None:
    query = resolve_legal_reference(
        [_tax_document("tax-1", "조세특례제한법 제63조에 따른 감면")],
        search_history=["청년창업 감면"],
        missing_information=["조세특례제한법 제6조의 청년창업 감면 근거"],
    )
    assert query == "조세특례제한법 제6조"
    assert parse_exact_legal_query(query) == ("조세특례제한법", "6")


def test_missing_prose_does_not_follow_unrelated_evidence_reference() -> None:
    assert resolve_legal_reference(
        [_tax_document("tax-1", "조세특례제한법 제63조에 따른 감면")],
        search_history=["청년창업 감면"],
        missing_information=["창업중소기업의 대상 업종 근거"],
    ) is None


def test_exact_article_is_added_to_next_hop_candidates() -> None:
    class ExactTaxSearch(SequentialTaxSearch):
        def search_legal_reference(
            self, law_name: str, article: str, *, top_k: int = 5
        ) -> list[VectorSearchResult]:
            assert (law_name, article) == ("조세특례제한법", "6")
            return [_tax_document("target", "창업 감면 요건")]

    search = ExactTaxSearch(
        [*[
            [_tax_document("unrelated", "조세특례제한법 제63조")]
            for _ in range(5)
         ],
         [_tax_document("other", "다른 법령")]]
    )
    decisions = iter([
        _decision(sufficient=False, missing_information=["조세특례제한법 제6조 근거"]),
        _decision(sufficient=True),
    ])

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return next(decisions)

    result = asyncio.run(build_graph(
        _router_llm(), tax_search=search, rerank=_identity_rerank,
        tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
    ).ainvoke({"query": "청년창업 감면 근거"}))

    assert result["search_history"][-1] == "조세특례제한법 제6조"
    assert result["tax_retrieval_trace"][1]["exact"][0]["chunk_id"] == "target"
    assert result["tax_retrieval_trace"][1]["rerank"][0]["chunk_id"] == "target"


def test_duplicate_query_stops_loop() -> None:
    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(sufficient=False)

    async def duplicate_query(_state: object) -> TaxNextQuery:
        return TaxNextQuery(query="세액감면 요건", reason="test")

    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=SequentialTaxSearch(
                [[_tax_document("tax-1", "추가 확인 필요")]]
            ),  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            tax_next_query_generator=duplicate_query,  # type: ignore[arg-type]
        ).ainvoke({"query": "세액감면 요건"})
    )

    assert result["hop_count"] == 1
    assert result["termination_reason"] == "duplicate_query"
    assert result["evidence_sufficient"] is False


def test_max_hops_keeps_insufficient_evidence_state() -> None:
    search = SequentialTaxSearch(
        [
            [_tax_document("tax-1", "첫 근거")],
            [_tax_document("tax-2", "두 번째 근거")],
        ]
    )
    next_queries = iter(["두 번째 검색", "세 번째 검색"])

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(sufficient=False, missing_information=["추가 근거"])

    async def next_query(_state: object) -> TaxNextQuery:
        return TaxNextQuery(query=next(next_queries), reason="test")

    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=search,  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            tax_next_query_generator=next_query,  # type: ignore[arg-type]
            settings=Settings(_env_file=None, tax_max_hops=2),
        ).ainvoke({"query": "세금 첫 검색"})
    )

    assert result["hop_count"] == 2
    assert result["termination_reason"] == "max_hops"
    assert result["evidence_sufficient"] is False
    assert result["answer_status"] == "insufficient_evidence"


def test_missing_user_context_returns_grounded_example_before_two_questions() -> None:
    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(
            sufficient=True,
            missing_user_context=["창업일", "사업장 지역", "업종"],
            cited_source_numbers=[1],
        )

    model = _router_llm(
        answer=(
            "확인된 일반 감면 조건을 설명합니다. 이해를 돕기 위해 예를 들면, "
            "법령상 조건을 충족한다고 가정한 사례이며 개인별 판정은 아닙니다. "
            "창업일과 사업장 지역을 알려주세요."
        )
    )
    result = asyncio.run(
        build_graph(
            model,
            tax_search=SequentialTaxSearch(
                [[_tax_document("tax-1", "법령 근거 충분")]]
            ),  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
        ).ainvoke({"query": "내가 감면 대상이야?", "category": "tax"})
    )

    assert result["hop_count"] == 1
    assert result["tax_general_explanation"] is True
    assert result["termination_reason"] == "evidence_sufficient"
    assert result["answer_status"] == "success"
    assert "이해를 돕기 위해 예를 들면" in result["answer"]
    assert "적용 모습을 보여주는 예시를 답변 앞부분에 반드시 쓰세요" in model.last_prompt_text
    assert "사용자가 판단할 수 없는 포괄적 가정은 쓰지 마세요" in model.last_prompt_text
    assert "목록에 없는 추가 정보를 새로 요구하지 마세요" in model.last_prompt_text
    assert "창업일" in model.last_prompt_text
    assert "사업장 지역" in model.last_prompt_text
    assert '"missing_user_context": ["창업일", "사업장 지역"]' in model.last_prompt_text


def test_general_tax_law_answers_with_sources_before_optional_personal_details() -> None:
    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(
            sufficient=True,
            missing_user_context=["실제 거래 형태"],
            cited_source_numbers=[1],
        )

    model = _router_llm(
        answer=(
            "장부 관련 일반 법적 기준입니다. 이해를 돕기 위해 예를 들면, "
            "실제 거래 형태가 법령상 조건을 충족한다고 가정한 사례이며 "
            "개인별 판정은 아닙니다."
        )
    )
    result = asyncio.run(
        build_graph(
            model,
            tax_search=SequentialTaxSearch(
                [[_tax_document("tax-1", "장부 기록 의무와 가산세의 일반 기준")]]
            ),  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
        ).ainvoke({"query": "장부를 작성하지 않으면 어떤 가산세가 붙나요?"})
    )

    assert result["tax_general_explanation"] is True
    assert result["termination_reason"] == "evidence_sufficient"
    assert result["answer_status"] == "success"
    assert result["answer_sources"][0]["chunk_id"] == "tax-1"
    assert "이해를 돕기 위해 예를 들면" in result["answer"]
    assert "개인별 판정은 아닙니다" in result["answer"]
    assert '"tax_general_explanation": true' in model.last_prompt_text
    assert "실제 거래 형태" in model.last_prompt_text
    assert "영향이 큰 항목 최대 두 개만 요청하세요" in model.last_prompt_text


def test_general_tax_law_keeps_searching_if_legal_evidence_is_insufficient() -> None:
    search = SequentialTaxSearch(
        [
            [_tax_document("tax-1", "관련 없는 법령")],
            [_tax_document("tax-2", "직접적인 법령 근거")],
        ]
    )
    decisions = iter(
        [
            _decision(
                sufficient=False,
                missing_information=["직접적인 법령 근거"],
                missing_user_context=["매출액"],
            ),
            _decision(sufficient=True, missing_user_context=["매출액"]),
        ]
    )

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return next(decisions)

    async def next_query(_state: object) -> TaxNextQuery:
        return TaxNextQuery(query="장부 불성실 가산세 법령", reason="근거 보강")

    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=search,  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            tax_next_query_generator=next_query,  # type: ignore[arg-type]
        ).ainvoke({"query": "장부 불성실 가산세 법적 기준은?"})
    )

    assert search.call_count == 2
    assert result["hop_count"] == 2
    assert result["answer_status"] == "success"
    assert result["answer_sources"]


def test_general_tax_law_keeps_safe_fallback_without_cited_partial_evidence() -> None:
    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(
            sufficient=False,
            missing_information=["직접적인 법령 근거"],
            missing_user_context=["매출액"],
        )

    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=SequentialTaxSearch(
                [[_tax_document("tax-1", "관련 없는 법령")]]
            ),  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            settings=Settings(_env_file=None, tax_max_hops=1),
        ).ainvoke({"query": "장부 불성실 가산세 법적 기준은?"})
    )

    assert result["termination_reason"] == "max_hops"
    assert result["answer_status"] == "insufficient_evidence"
    assert result["answer_sources"] == []
    assert result["answer"] == "현재 확인된 근거만으로는 확정하기 어렵습니다."


def test_tax_partial_evidence_explains_known_facts_and_keeps_status() -> None:
    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(
            sufficient=False,
            missing_information=["사업장 지역", "최초 창업 여부", "업종"],
            cited_source_numbers=[1],
        )

    model = _router_llm(
        answer=(
            "확인된 일반 감면 조건입니다. 지역과 최초 창업 여부는 확인이 필요합니다. "
            "이해를 돕기 위해 예를 들면, 법령상 요건을 충족한다고 가정한 "
            "사례이며 실제 판정은 아닙니다."
        ),
        answer_status="insufficient_evidence",
    )
    result = asyncio.run(
        build_graph(
            model,
            tax_search=SequentialTaxSearch(
                [[_tax_document("tax-1", "청년창업 세액감면의 일반 대상 요건")]]
            ),  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            settings=Settings(_env_file=None, tax_max_hops=1),
        ).ainvoke({"query": "청년창업 세액감면 대상인지 확인"})
    )

    assert result["answer_status"] == "insufficient_evidence"
    assert result["answer_sources"][0]["chunk_id"] == "tax-1"
    assert "이해를 돕기 위해 예를 들면" in result["answer"]
    assert "개인별 적용만 보류하세요" in model.last_prompt_text
    assert "사업장 지역" in model.last_prompt_text
    assert "최초 창업 여부" in model.last_prompt_text
    assert '"missing_information": ["사업장 지역", "최초 창업 여부"]' in model.last_prompt_text


def test_withholding_uses_disclosed_defaults_for_missing_family_values() -> None:
    search = SequentialTaxSearch([[_tax_document("tax-1", "사용되면 안 됨")]])

    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan(
            calculation_inputs={"monthly_salary_krw": 3_200_000},
            missing_required_inputs=["공제대상 가족 수"],
            reason="가족 수 필요",
        )

    result = asyncio.run(
        build_graph(
            _router_llm(
                calculation_required=True,
                calculation_type="withholding_tax",
                cited_source_numbers=[],
            ),
            tax_search=search,  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_calculation_planner=plan,  # type: ignore[arg-type]
        ).ainvoke({"query": "월급 320만원인데 소득세 얼마야?"})
    )

    assert search.call_count == 0
    assert result["calculation_result"]["withholding_income_tax_krw"] == "91460.00"
    assert result["calculation_result"]["calculation_method"] == "formula_reproduction"
    assert result["termination_reason"] == "calculation_complete"
    assert result["answer_status"] == "success"
    assert result["calculation_inputs"]["family_count"] == 1
    assert result["calculation_inputs"]["child_count"] == 0
    assert len(result["calculation_assumptions"]) == 2
    assert "본인 포함 1명으로 가정" in result["answer"]
    assert "자녀 수를 0명으로 가정" in result["answer"]
    assert "91,460원" in result["answer"]
    assert "신고용 확정 세액은 아닙니다" in result["answer"]


def test_general_vat_defaults_are_disclosed_and_not_treated_as_user_values() -> None:
    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan(
            {"taxable_sales_supply_value_krw": 1_000_000},
            missing_required_inputs=["공제 매입세액", "세액공제"],
        )

    result = asyncio.run(build_graph(
        _router_llm(calculation_required=True, calculation_type="general_vat",
                    cited_source_numbers=[]),
        tax_calculation_planner=plan,  # type: ignore[arg-type]
    ).ainvoke({"query": "공급가액 100만원이면 부가세는?"}))

    assert result["answer_status"] == "success"
    assert result["calculation_result"]["final_tax_krw"] == "100000.00"
    assert set(result["defaulted_calculation_inputs"]) == {
        "deductible_input_tax_krw", "tax_credit_krw",
        "prepaid_tax_krw", "penalty_tax_krw",
    }
    assert "공제 매입세액을 0원으로 가정" in result["answer"]
    assert "더 정확한 결과를 원하시면 공제 매입세액" in result["answer"]
    assert "100,000원" in result["answer"]


def test_general_vat_user_value_overrides_default_on_follow_up_turn() -> None:
    async def plan(state: object) -> TaxCalculationInputPlan:
        assert isinstance(state, dict)
        inputs = {"taxable_sales_supply_value_krw": 1_000_000}
        if state["query"].startswith("공제 매입세액"):
            inputs["deductible_input_tax_krw"] = 20_000
        return _input_plan(inputs)

    async def contextualize(_state: object) -> ContextualizedQuestion:
        return ContextualizedQuestion(
            standalone_question="공급가액 100만원, 공제 매입세액 2만원 부가세 계산"
        )

    graph = build_graph(
        _router_llm(calculation_required=True, calculation_type="general_vat",
                    cited_source_numbers=[]),
        tax_calculation_planner=plan,  # type: ignore[arg-type]
        question_contextualizer=contextualize,  # type: ignore[arg-type]
    )
    first = asyncio.run(graph.ainvoke({"query": "공급가액 100만원 부가세 계산"}))
    second = asyncio.run(graph.ainvoke({
        "query": "공제 매입세액은 2만원이야",
        "conversation_history": [
            {"role": "user", "content": "공급가액 100만원 부가세 계산"},
            {"role": "assistant", "content": first["answer"]},
        ],
    }))

    assert first["calculation_result"]["final_tax_krw"] == "100000.00"
    assert second["calculation_result"]["final_tax_krw"] == "80000.00"
    assert "deductible_input_tax_krw" not in second["defaulted_calculation_inputs"]
    assert "공제 매입세액을 0원으로 가정" not in second["answer"]
    assert "80,000원" in second["answer"]


def test_missing_tax_base_and_year_are_requested_without_guessing() -> None:
    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan({})

    result = asyncio.run(build_graph(
        _router_llm(calculation_required=True, calculation_type="income_tax",
                    cited_source_numbers=[]),
        tax_calculation_planner=plan,  # type: ignore[arg-type]
    ).ainvoke({"query": "종합소득세 계산해줘"}))

    assert result["answer_status"] == "need_more_info"
    assert result["missing_calculation_inputs"] == ["과세표준", "귀속연도"]
    assert result["calculation_result"] is None


def test_tax_answer_rejects_model_generated_amount() -> None:
    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan({"tax_base_krw": 50_000_000, "tax_year": 2025})

    model = FakeStructuredChatModel({
        RouteDecision: {"route": "tax", "personalized": False},
        TaxIntentDecision: {
            "calculation_required": True, "calculation_type": "income_tax",
            "reason": "test",
        },
        UnifiedAnswerResult: {
            "answer": "산출세액은 999,999원입니다.",
            "status": "success", "cited_source_numbers": [],
        },
    })
    result = asyncio.run(build_graph(
        model, tax_calculation_planner=plan,  # type: ignore[arg-type]
    ).ainvoke({"query": "2025년 과세표준 5천만원 산출세액?"}))

    assert result["answer_status"] == "success"
    assert "6,240,000원" in result["answer"]
    assert "999,999원" not in result["answer"]


def test_tax_answer_does_not_show_unrenderable_calculator_amount() -> None:
    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan({"tax_base_krw": 50_000_000, "tax_year": 2025})

    result = asyncio.run(build_graph(
        _router_llm(calculation_required=True, calculation_type="income_tax",
                    cited_source_numbers=[]),
        tax_calculation_planner=plan,  # type: ignore[arg-type]
        tax_calculator=lambda _type, **_kwargs: {
            "calculation_type": "income_tax", "calculated_income_tax_krw": "NaN",
        },
    ).ainvoke({"query": "2025년 과세표준 5천만원 산출세액?"}))

    assert result["answer_status"] == "error"
    assert "NaN" not in result["answer"]


def test_direct_income_tax_skips_retrieval_and_calls_calculator_once() -> None:
    search = SequentialTaxSearch([[_tax_document("tax-1", "사용되면 안 됨")]])
    calls = {"intent": 0, "planner": 0, "calculator": 0}

    async def intent(_state: object) -> TaxIntentDecision:
        calls["intent"] += 1
        return TaxIntentDecision(
            calculation_required=True,
            calculation_type="income_tax",
            reason="산출세액 계산 요청",
        )

    async def plan(_state: object) -> TaxCalculationInputPlan:
        calls["planner"] += 1
        return _input_plan(
            calculation_inputs={"tax_base_krw": "5천만원", "tax_year": 2025},
            reason="질문에 명시됨",
        )

    def calculator(calculation_type: str, **kwargs: object) -> dict[str, object]:
        calls["calculator"] += 1
        assert calculation_type == "income_tax"
        assert kwargs == {"tax_base_krw": "50000000", "tax_year": 2025}
        return serving_calculate_tax(calculation_type, **kwargs)  # type: ignore[arg-type]

    result = asyncio.run(
        build_graph(
            _router_llm(cited_source_numbers=[]),
            tax_search=search,  # type: ignore[arg-type]
            tax_intent_classifier=intent,  # type: ignore[arg-type]
            tax_calculation_planner=plan,  # type: ignore[arg-type]
            tax_calculator=calculator,
        ).ainvoke({"query": "2025년 과세표준 5천만원 산출세액 얼마야?"})
    )

    assert calls == {"intent": 1, "planner": 1, "calculator": 1}
    assert search.call_count == 0
    assert result["answer_status"] == "success"
    assert result["calculation_inputs"]["tax_base_krw"] == "50000000"
    assert result["calculation_result"]["calculated_income_tax_krw"] == "6240000.00"


def test_direct_withholding_calls_formula_calculator_without_table_data() -> None:
    calculator_calls = 0

    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan(
            calculation_inputs={
                "monthly_salary_krw": 3_200_000,
                "family_count": 1,
            },
            reason="질문에 명시됨",
        )

    def calculator(calculation_type: str, **kwargs: object) -> dict[str, object]:
        nonlocal calculator_calls
        calculator_calls += 1
        assert calculation_type == "withholding_tax"
        assert kwargs == {
            "monthly_salary_krw": "3200000",
            "family_count": 1,
            "child_count": 0,
        }
        return {
            "calculation_type": calculation_type,
            "withholding_income_tax_krw": "50000.00",
        }

    result = asyncio.run(
        build_graph(
            _router_llm(
                calculation_required=True,
                calculation_type="withholding_tax",
                cited_source_numbers=[],
            ),
            tax_calculation_planner=plan,  # type: ignore[arg-type]
            tax_calculator=calculator,
        ).ainvoke({"query": "월급 320만원, 가족 1명 원천징수세액은?"})
    )

    assert calculator_calls == 1
    assert result["answer_status"] == "success"


def test_withholding_without_external_table_runs_formula_calculator() -> None:
    calculator_calls = 0

    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan(
            calculation_inputs={
                "monthly_salary_krw": 3_200_000,
                "family_count": 1,
            },
            reason="질문에 명시됨",
        )

    def calculator(calculation_type: str, **kwargs: object) -> dict[str, object]:
        nonlocal calculator_calls
        calculator_calls += 1
        return serving_calculate_tax(calculation_type, **kwargs)  # type: ignore[arg-type]

    result = asyncio.run(
        build_graph(
            _router_llm(
                calculation_required=True,
                calculation_type="withholding_tax",
                cited_source_numbers=[],
            ),
            tax_calculation_planner=plan,  # type: ignore[arg-type]
            tax_calculator=calculator,
        ).ainvoke({"query": "월급 320만원, 가족 1명 원천징수세액은?"})
    )

    assert calculator_calls == 1
    assert result["termination_reason"] == "calculation_complete"
    assert result["missing_calculation_inputs"] == []
    assert result["answer_status"] == "success"
    assert result["calculation_result"]["withholding_income_tax_krw"] == "91460.00"


def test_startup_calculation_requires_rag_and_resolved_legal_inputs() -> None:
    search = SequentialTaxSearch(
        [[_tax_document("tax-1", "청년창업 비수도권 감면 요건")]]
    )
    calculator_calls = 0

    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan(
            calculation_inputs={
                "eligible_tax_krw": 3_000_000,
                "startup_year": 2026,
                "age": 29,
                "business_location": "대전",
                "industry": "음식점업",
                "first_startup": True,
            },
            reason="사용자가 제공한 현실 정보",
        )

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(
            sufficient=True,
            calculation_required=True,
            resolved_calculation_inputs={
                "category": "youth_or_livelihood",
                "region": "outside_capital_region",
            },
            cited_source_numbers=[1],
        )

    def calculator(calculation_type: str, **kwargs: object) -> dict[str, object]:
        nonlocal calculator_calls
        calculator_calls += 1
        assert calculation_type == "startup_tax_reduction"
        assert kwargs["category"] == "youth_or_livelihood"
        assert kwargs["region"] == "outside_capital_region"
        assert "business_location" not in kwargs
        return {
            "calculation_type": calculation_type,
            "reduction_amount_krw": "3000000.00",
        }

    result = asyncio.run(
        build_graph(
            _router_llm(
                calculation_required=True,
                calculation_type="startup_tax_reduction",
            ),
            tax_search=search,  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            tax_calculation_planner=plan,  # type: ignore[arg-type]
            tax_calculator=calculator,
        ).ainvoke({"query": "29세 대전 음식점 첫 창업, 세금 300만원 감면액은?"})
    )

    assert search.call_count == 5
    assert calculator_calls == 1
    assert result["answer_status"] == "success"


def test_startup_calculation_prefills_profile_and_asks_only_unresolved_eligibility() -> None:
    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan({"eligible_tax_krw": 3_000_000, "age": 31})

    result = asyncio.run(build_graph(
        _router_llm(calculation_required=True, calculation_type="startup_tax_reduction"),
        tax_calculation_planner=plan,  # type: ignore[arg-type]
    ).ainvoke({
        "query": "청년창업 감면액 계산해줘",
        "category": "tax",
        "user_context": {
            "user_id": 1, "age": 29, "region": "대전",
            "business": {"industry": "음식점업", "business_type": None,
                         "founded_at": "2026-03-01"},
        },
    }))

    assert result["calculation_inputs"]["age"] == 31  # explicit input wins
    assert result["calculation_inputs"]["startup_year"] == 2026
    assert result["calculation_inputs"]["business_location"] == "대전"
    assert result["calculation_inputs"]["industry"] == "음식점업"
    assert "first_startup" not in result["calculation_inputs"]
    assert result["missing_user_context"] == ["최초 창업 여부와 과거 사업 이력"]
    assert result["answer_status"] == "need_more_info"
    assert "프로필 지역 대전" in result["answer"]
    assert "프로필의 창업연도 2026" in result["answer"]
    assert "최초 창업 여부" in result["answer"]


def test_startup_calculation_missing_inputs_stay_internal_and_request_two() -> None:
    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan({})

    result = asyncio.run(build_graph(
        _router_llm(calculation_required=True, calculation_type="startup_tax_reduction"),
        tax_calculation_planner=plan,  # type: ignore[arg-type]
    ).ainvoke({"query": "창업 감면액 계산해줘", "category": "tax"}))

    assert len(result["missing_calculation_inputs"]) == 6
    assert result["missing_user_context"] == [
        "감면 적용 전 세액", "최초 창업 여부와 과거 사업 이력",
    ]
    assert result["answer_status"] == "need_more_info"
    assert "창업연도" not in result["answer"]


def test_startup_unresolved_internal_parameter_blocks_calculator() -> None:
    calculator_calls = 0

    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan(
            calculation_inputs={
                "eligible_tax_krw": 3_000_000,
                "startup_year": 2026,
                "age": 29,
                "business_location": "대전",
                "industry": "음식점업",
                "first_startup": True,
            },
            reason="사용자 현실 정보가 명시됨",
        )

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(sufficient=True, calculation_required=True)

    def calculator(_calculation_type: str, **_kwargs: object) -> dict[str, object]:
        nonlocal calculator_calls
        calculator_calls += 1
        return {}

    result = asyncio.run(
        build_graph(
            _router_llm(
                calculation_required=True,
                calculation_type="startup_tax_reduction",
            ),
            tax_search=SequentialTaxSearch(
                [[_tax_document("tax-1", "창업 감면 법령 일부")]]
            ),  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            tax_calculation_planner=plan,  # type: ignore[arg-type]
            tax_calculator=calculator,
        ).ainvoke({"query": "2026년 창업, 세금 300만원 감면액은?"})
    )

    assert calculator_calls == 0
    assert result["termination_reason"] == "calculation_parameter_unresolved"
    assert result["answer_status"] == "insufficient_evidence"


def test_legal_calculation_max_hops_never_calls_calculator() -> None:
    calculator_calls = 0

    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan(
            calculation_inputs={
                "eligible_tax_krw": 3_000_000,
                "startup_year": 2026,
                "age": 29,
                "business_location": "대전",
                "industry": "음식점업",
                "first_startup": True,
            },
            reason="사용자 현실 정보가 명시됨",
        )

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(
            sufficient=False,
            missing_information=["적용 업종 근거"],
            calculation_required=True,
        )

    def calculator(_calculation_type: str, **_kwargs: object) -> dict[str, object]:
        nonlocal calculator_calls
        calculator_calls += 1
        return {}

    result = asyncio.run(
        build_graph(
            _router_llm(
                calculation_required=True,
                calculation_type="startup_tax_reduction",
            ),
            tax_search=SequentialTaxSearch(
                [[_tax_document("tax-1", "불충분한 창업 감면 근거")]]
            ),  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            tax_calculation_planner=plan,  # type: ignore[arg-type]
            tax_calculator=calculator,
            settings=Settings(_env_file=None, tax_max_hops=1),
        ).ainvoke({"query": "2026년 청년창업 세금 300만원 감면액은?"})
    )

    assert calculator_calls == 0
    assert result["termination_reason"] == "max_hops"
    assert result["answer_status"] == "insufficient_evidence"


def test_unsupported_income_tax_year_does_not_fallback_or_call_calculator() -> None:
    calculator_calls = 0

    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan(
            calculation_inputs={"tax_base_krw": 50_000_000, "tax_year": 2026},
            reason="질문에 명시됨",
        )

    def calculator(_calculation_type: str, **_kwargs: object) -> dict[str, object]:
        nonlocal calculator_calls
        calculator_calls += 1
        return {}

    result = asyncio.run(
        build_graph(
            _router_llm(
                calculation_required=True,
                calculation_type="income_tax",
            ),
            tax_calculation_planner=plan,  # type: ignore[arg-type]
            tax_calculator=calculator,
        ).ainvoke({"query": "2026년 과세표준 5천만원 산출세액은?"})
    )

    assert calculator_calls == 0
    assert result["termination_reason"] == "unsupported_tax_year"
    assert result["answer_status"] == "integration_unavailable"


def test_evidence_based_decimal_calculation_reaches_unified_answer() -> None:
    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(
            sufficient=True,
            calculation_required=True,
            resolved_calculation_inputs={"rate_percent": "75"},
            cited_source_numbers=[1],
        )

    async def plan(_state: object) -> TaxCalculationInputPlan:
        return _input_plan(
            calculation_inputs={"base_amount": "1000000"},
            reason="명시된 기준 금액",
        )

    result = asyncio.run(
        build_graph(
            _router_llm(
                calculation_required=True,
                calculation_type="reduction_amount",
            ),
            tax_search=SequentialTaxSearch(
                [[_tax_document("tax-1", "산출세액의 100분의 75 감면")]]
            ),  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            tax_calculation_planner=plan,  # type: ignore[arg-type]
        ).ainvoke({"query": "예상 세금은 얼마야?"})
    )

    assert result["calculation_result"] == {
        "calculation_type": "reduction_amount",
        "base_amount": "1000000",
        "rate_percent": "75",
        "reduction_amount": "750000",
        "formula": "base_amount × rate_percent ÷ 100",
        "cited_source_numbers": [1],
    }
    assert result["termination_reason"] == "calculation_complete"
    assert result["answer_status"] == "success"
    assert result["normalized_ratios"][0]["percent"] == 75
    assert result["normalized_ratios"][0]["decimal"] == 0.75
    assert result["reranked_docs"][0]["content"] == "산출세액의 100분의 75 감면"


def test_tax_cohere_failure_falls_back_to_rrf() -> None:
    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(sufficient=True)

    def failing_rerank(
        _query: str,
        _documents: list[VectorSearchResult],
        _top_n: int,
    ) -> list[VectorSearchResult]:
        from src.rag.reranker import CohereRerankError

        raise CohereRerankError("temporary error")

    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=SequentialTaxSearch(
                [[_tax_document("tax-1", "충분한 세법 근거")]]
            ),  # type: ignore[arg-type]
            rerank=failing_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
        ).ainvoke({"query": "세액감면이 뭐야?"})
    )

    assert result["reranked_docs"][0]["chunk_id"] == "tax-1"
    assert result["answer_status"] == "success"


def test_tax_no_result_reaches_unified_answer() -> None:
    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=SequentialTaxSearch([[]]),  # type: ignore[arg-type]
            rerank=_identity_rerank,
        ).ainvoke({"query": "찾을 수 없는 세법 질문"})
    )

    assert result["reranked_docs"] == []
    assert result["evidence_sufficient"] is False
    assert result["answer_status"] == "no_result"


def test_next_query_failure_goes_to_answer_without_calculation() -> None:
    calculation_calls = 0

    async def evaluate(_state: object) -> TaxEvidenceDecision:
        return _decision(sufficient=False, missing_information=["추가 법령"])

    async def failing_next_query(_state: object) -> TaxNextQuery:
        raise RuntimeError("generation failed")

    async def calculation_plan(_state: object) -> TaxCalculationPlan:
        nonlocal calculation_calls
        calculation_calls += 1
        raise AssertionError("calculation must not run")

    result = asyncio.run(
        build_graph(
            _router_llm(),
            tax_search=SequentialTaxSearch(
                [[_tax_document("tax-1", "추가 근거가 필요하다")]]
            ),  # type: ignore[arg-type]
            rerank=_identity_rerank,
            tax_evidence_evaluator=evaluate,  # type: ignore[arg-type]
            tax_next_query_generator=failing_next_query,  # type: ignore[arg-type]
            tax_calculation_planner=calculation_plan,  # type: ignore[arg-type]
        ).ainvoke({"query": "세액감면 조건 알려줘"})
    )

    assert calculation_calls == 0
    assert result["termination_reason"] == "next_query_error"
    assert result["answer_status"] == "error"


def test_tax_decisions_use_structured_output() -> None:
    model = FakeStructuredChatModel(
        {
            TaxEvidenceDecision: {
                "sufficient": False,
                "missing_information": ["업종 요건"],
                "missing_user_context": [],
                "calculation_required": False,
                "resolved_category": None,
                "resolved_region": None,
                "resolved_rate_percent": None,
                "cited_source_numbers": [],
                "reason": "추가 법령 필요",
            },
            TaxNextQuery: {
                "query": "조세특례제한법 음식점업 요건",
                "target_law": "조세특례제한법",
                "target_article": None,
                "reason": "업종 요건 검색",
            },
        }
    )
    documents = [_tax_document("tax-1", "감면 대상 업종 확인 필요")]

    evidence = asyncio.run(
        evaluate_tax_evidence(
            model,  # type: ignore[arg-type]
            query="음식점 창업 감면 대상이야?",
            documents=documents,
            user_context=None,
            general_explanation=True,
        )
    )
    assert "일반 법적 기준 설명: True" in model.last_prompt_text
    assert "사용자 정보 부족을 혼동하지 마세요" in model.last_prompt_text
    assert "sufficient=false여도 질문과 직접 관련된" in model.last_prompt_text
    next_query = asyncio.run(
        generate_tax_next_query(
            model,  # type: ignore[arg-type]
            query="음식점 창업 감면 대상이야?",
            documents=documents,
            missing_information=evidence.missing_information,
            user_context=None,
            search_history=["음식점 창업 감면 대상이야?"],
        )
    )

    assert evidence.missing_information == ["업종 요건"]
    assert next_query.query == "조세특례제한법 음식점업 요건"


def test_tax_evidence_evaluation_uses_short_relevant_excerpts() -> None:
    documents = [
        _tax_document(
            "tax-1",
            ("질문과 무관한 신고 서식 설명입니다. " * 30)
            + "청년창업중소기업은 법에서 정한 요건을 충족하면 세액감면을 적용합니다. "
            + "다만 제외 업종에 해당하는 경우에는 적용하지 않습니다.",
        ),
        _tax_document(
            "tax-2",
            "감면 기간은 해당 조항에서 정한 기간까지 적용합니다. "
            + ("다른 행정 절차 설명입니다. " * 30),
        ),
    ]

    full = _format_evidence(documents)
    excerpt = _format_evidence_for_evaluation(
        "청년창업 세액감면 대상인지 알려주세요", documents
    )

    assert len(excerpt) < len(full)
    assert "청년창업중소기업" in excerpt
    assert "다만 제외 업종" in excerpt
    assert "감면 기간" in excerpt
    assert "[1] 조세특례제한법" in excerpt
    assert "[2] 조세특례제한법" in excerpt
    assert "chunk_id=tax-1" in excerpt
    assert "chunk_id=tax-2" in excerpt


def test_calculate_tax_plan_supports_half_percent_from_evidence() -> None:
    documents = [_tax_document("tax-1", "가산 비율은 1000분의 5(0.5%)이다.")]
    plan = TaxCalculationPlan(
        calculation_type="percentage_of_amount",
        base_amount="200000",
        rate_percent="0.5",
        cited_source_numbers=[1],
        reason="법령 비율 적용",
    )

    result = calculate_tax_plan(plan, documents=documents)

    assert result["calculated_amount"] == "1000"
    assert result["rate_percent"] == "0.5"


def test_calculate_tax_plan_rejects_rate_not_found_in_cited_source() -> None:
    documents = [_tax_document("tax-1", "법령상 비율은 100분의 15(15%)이다.")]
    plan = TaxCalculationPlan(
        calculation_type="reduction_amount",
        base_amount="100000",
        rate_percent="75",
        cited_source_numbers=[1],
        reason="잘못된 비율",
    )

    with pytest.raises(TaxCalculationError, match="not present"):
        calculate_tax_plan(plan, documents=documents)


def test_calculate_tax_plan_rejects_invented_source_number() -> None:
    plan = TaxCalculationPlan(
        calculation_type="reduction_amount",
        base_amount="100000",
        rate_percent="15",
        cited_source_numbers=[2],
        reason="잘못된 출처",
    )

    with pytest.raises(TaxCalculationError, match="source number"):
        calculate_tax_plan(
            plan,
            documents=[_tax_document("tax-1", "100분의 15(15%)")],
        )


def test_tax_calculation_plan_uses_structured_output() -> None:
    model = FakeStructuredChatModel(
        {
            TaxCalculationPlan: {
                "calculation_type": "amount_after_reduction",
                "base_amount": "1000000",
                "rate_percent": "75",
                "missing_inputs": [],
                "cited_source_numbers": [1],
                "reason": "법령 감면율",
            }
        }
    )

    plan = asyncio.run(
        generate_tax_calculation_plan(
            model,  # type: ignore[arg-type]
            query="산출세액 100만원의 감면 후 금액",
            documents=[_tax_document("tax-1", "100분의 75 감면")],
            user_context=None,
        )
    )

    assert plan.base_amount == "1000000"
    assert plan.rate_percent == "75"
    assert "100분의 75(75%)" in model.last_prompt_text


def test_tax_intent_and_input_planner_use_separate_structured_outputs() -> None:
    model = FakeStructuredChatModel(
        {
            TaxIntentDecision: {
                "calculation_required": True,
                "calculation_type": "income_tax",
                "reason": "산출세액 계산 요청",
            },
            TaxCalculationInputPlan: _input_plan_payload(
                {
                    "tax_base_krw": 50_000_000,
                    "tax_year": 2025,
                },
                reason="질문에 명시됨",
            ),
        }
    )

    intent = asyncio.run(
        classify_tax_intent(
            model,  # type: ignore[arg-type]
            query="2025년 과세표준 5천만원 산출세액은?",
            user_context=None,
        )
    )
    plan = asyncio.run(
        generate_tax_calculation_inputs(
            model,  # type: ignore[arg-type]
            query="2025년 과세표준 5천만원 산출세액은?",
            calculation_type=intent.calculation_type,  # type: ignore[arg-type]
            user_context=None,
        )
    )

    assert intent.calculation_type == "income_tax"
    assert plan.provided_inputs()["tax_base_krw"] == "50000000"
    assert "계산 종류: income_tax" in model.last_prompt_text


def test_tax_intent_corrects_salary_income_tax_to_withholding() -> None:
    model = FakeStructuredChatModel(
        {
            TaxIntentDecision: {
                "calculation_required": True,
                "calculation_type": "income_tax",
                "reason": "소득세 계산 요청",
            }
        }
    )

    intent = asyncio.run(
        classify_tax_intent(
            model,  # type: ignore[arg-type]
            query="2025년 내 월급 세전 280만원인데 소득세 얼마나 내야돼?",
            user_context=None,
        )
    )

    assert intent.calculation_type == "withholding_tax"


@pytest.mark.parametrize(
    "schema_model",
    [TaxIntentDecision, TaxCalculationInputPlan, TaxEvidenceDecision],
)
def test_openai_structured_models_require_every_explicit_property(
    schema_model: type[object],
) -> None:
    schema = schema_model.model_json_schema()  # type: ignore[attr-defined]

    assert set(schema["required"]) == set(schema["properties"])
    assert "calculation_inputs" not in schema["properties"]
    assert "resolved_calculation_inputs" not in schema["properties"]
