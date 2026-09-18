from datetime import datetime, timezone
import json

from src.core.config import Settings
from src.rag.tax_cache import (
    TaxRagCache,
    _decision_conditions,
    _decision_scope,
    _normalized_question,
    _user_conditions,
)
from src.serving.rag_routes import RagRuntime
from src.vectorstores.hybrid import HybridSearch
from src.vectorstores.postgres import PostgresVectorSearch


class FakeEmbedding:
    def __init__(self) -> None:
        self.calls = 0

    def embed_query(self, _text: str) -> list[float]:
        self.calls += 1
        return [0.1] * 1536


class FakeVectorSearch:
    def __init__(self) -> None:
        self.ids: list[int] = []

    def get_tax_evidence_by_ids(
        self, ids: list[int], _created_at: datetime
    ) -> list[dict[str, object]]:
        self.ids = ids
        return [
            {"id": value, "chunk_id": f"tax-{value}", "policy_id": None,
             "title": "조세특례제한법", "source": "db://tax/1", "page": 1,
             "content": "제6조 요건", "score": 1.0, "source_type": "tax_document",
             "source_id": 1}
            for value in ids
        ]


class FakeCursor:
    def __init__(self, exact: object, candidates: list[dict[str, object]]) -> None:
        self.exact = exact
        self.candidates = candidates
        self.sql: list[str] = []
        self.params: list[tuple[object, ...]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.sql.append(sql)
        self.params.append(params)

    def fetchone(self):
        return self.exact

    def fetchall(self):
        return self.candidates


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def cursor(self, **_kwargs):
        return self._cursor


def _cache(monkeypatch, *, exact=None, candidates=None):
    from src.rag import tax_cache as module

    cursor = FakeCursor(exact, candidates or [])
    monkeypatch.setattr(module, "connect_database", lambda _settings: FakeConnection(cursor))
    monkeypatch.setattr(module, "register_vector", lambda _connection: None)
    embedding = FakeEmbedding()
    vector = FakeVectorSearch()
    cache = TaxRagCache(
        Settings(_env_file=None, tax_cache_similarity_threshold=0.95),
        embedding, vector,  # type: ignore[arg-type]
    )
    return cache, embedding, vector, cursor


def _signed_payload(
    question: str,
    profile,
    result: dict[str, object],
    prior_ids: list[int] | None = None,
) -> dict[str, object]:
    prior_ids = prior_ids or []
    decision_conditions = _decision_conditions(question, profile)
    ids = result["embedding_ids"]
    assert isinstance(ids, list)
    return {
        **result,
        "decision_scope": _decision_scope(question),
        "decision_conditions": decision_conditions,
        "decision_lookup_key": TaxRagCache._decision_lookup_key(
            question, decision_conditions, prior_ids
        ),
        "decision_signature": TaxRagCache._decision_signature(
            question, decision_conditions, prior_ids, ids
        ),
    }


def test_exact_key_normalizes_whitespace_and_ignores_user_id(monkeypatch) -> None:
    profile = {"user_id": 1, "age": 27, "region": "서울", "business": {
        "industry": "제조업", "business_type": None, "founded_at": "2025-01-01"
    }}
    conditions = _user_conditions("청년 창업 감면", profile)  # type: ignore[arg-type]
    assert TaxRagCache._key(_normalized_question(" 청년  창업 감면 "), conditions) == (
        TaxRagCache._key(_normalized_question("청년 창업 감면"), conditions)
    )
    assert "user_id" not in conditions
    changed = {**profile, "user_id": 2}
    assert _user_conditions("청년 창업 감면", changed) == conditions  # type: ignore[arg-type]


def test_exact_hit_restores_ids_without_embedding(monkeypatch) -> None:
    question = "청년 창업 감면"
    conditions = _user_conditions(question, None)
    result = _signed_payload(question, None, {
        "user_conditions": conditions, "embedding_ids": [323, 418],
        "retrieval_ids": [323, 418], "embedding_version": "topic-v3",
        "decision_question": question, "hop_queries": ["제6조", "시행령"],
    })
    cache, embedding, vector, cursor = _cache(
        monkeypatch, exact={"cached_result": result, "created_at": datetime.now(timezone.utc)}
    )
    documents, queries, query_embedding, decision, mode = cache.lookup(question, None)
    assert [document["id"] for document in documents] == [323, 418]
    assert queries == ["제6조", "시행령"]
    assert vector.ids == [323, 418]
    assert query_embedding is None and decision is None and mode == "full"
    assert embedding.calls == 0
    assert len(cursor.sql) == 1


def test_semantic_hit_reuses_retrieval_across_user_conditions(monkeypatch) -> None:
    question = "청년 창업 감면"
    conditions = _user_conditions(question, None)
    result = {"user_conditions": conditions, "embedding_ids": [323],
              "retrieval_ids": [323], "embedding_version": "topic-v3",
              "decision_question": question,
              "hop_queries": ["제6조"]}
    cache, embedding, vector, cursor = _cache(
        monkeypatch, candidates=[{"cached_result": result, "created_at": datetime.now(timezone.utc), "similarity": 0.94}]
    )
    assert cache.lookup(question, None)[0] == []
    assert embedding.calls == 1
    assert "<=>" in cursor.sql[-1] and "1 -" in cursor.sql[-1]

    cursor.candidates = [{"cached_result": result, "created_at": datetime.now(timezone.utc), "similarity": 0.96}]
    hit = cache.lookup(question, None)
    assert hit[0][0]["id"] == 323 and hit[4] == "retrieval"
    assert vector.ids == [323]

    other = {**conditions, "age": 50}
    cursor.candidates = [{"cached_result": {**result, "user_conditions": other},
                          "created_at": datetime.now(timezone.utc),
                          "similarity": 0.99}]
    hit = cache.lookup(question, {"age": 51})  # type: ignore[arg-type]
    assert hit[0][0]["id"] == 323
    assert hit[3] is None and hit[4] == "retrieval"


def test_stale_exact_evidence_is_a_miss(monkeypatch) -> None:
    question = "청년 창업 감면"
    result = {"user_conditions": _user_conditions(question, None),
              "embedding_ids": [323], "hop_queries": ["제6조"]}
    cache, _, vector, _ = _cache(
        monkeypatch, exact={"cached_result": result, "created_at": datetime.now(timezone.utc)}
    )
    vector.get_tax_evidence_by_ids = lambda *_args: []  # type: ignore[method-assign]
    assert cache.lookup(question, None)[0] == []


def test_save_uses_pk_and_conflict_upsert(monkeypatch) -> None:
    cache, embedding, _, cursor = _cache(monkeypatch)
    cache.save("청년 창업 감면", None, [{"id": 323}], ["제6조"], [0.1] * 1536)  # type: ignore[list-item]
    assert embedding.calls == 0
    assert "ON CONFLICT (cache_key) DO UPDATE" in cursor.sql[-1]
    assert "cached_result" in cursor.sql[-1]
    stored = json.loads(cursor.params[-1][3])
    assert set(stored) == {
        "hop_queries", "embedding_ids", "retrieval_ids", "embedding_version",
        "decision_question", "decision_scope", "decision_conditions",
        "decision_lookup_key", "decision_signature", "user_conditions",
    }
    assert stored["embedding_ids"] == [323]
    assert stored["retrieval_ids"] == [323]
    assert stored["embedding_version"] == "topic-v3"


def test_negative_evidence_decision_is_restored_for_same_hop(monkeypatch) -> None:
    question = "조세특례제한법 청년 요건"
    conditions = _user_conditions(question, None)
    decision = {
        "sufficient": False,
        "missing_information": ["시행령 연령 요건"],
        "missing_user_context": [],
        "calculation_required": False,
        "resolved_category": None,
        "resolved_region": None,
        "resolved_rate_percent": None,
        "cited_source_numbers": [1],
        "reason": "추가 근거 필요",
        "hop_count": 2,
        "termination_reason": None,
    }
    result = _signed_payload(question, None, {
        "user_conditions": conditions,
        "embedding_ids": [323],
        "retrieval_ids": [323],
        "embedding_version": "topic-v3",
        "decision_question": question,
        "hop_queries": [question],
        "evidence_cache_version": "tax-evidence-v1",
        "llm_model": "test-model",
        "prior_evidence_ids": [111],
        "evidence_decision": decision,
    }, [111])
    cache, embedding, _, _ = _cache(
        monkeypatch,
        exact={"cached_result": result, "created_at": datetime.now(timezone.utc)},
    )
    cache._settings = Settings(_env_file=None, llm_model="test-model")

    documents, queries, query_embedding, restored, mode = cache.lookup(
        question, None, [111]
    )

    assert documents[0]["id"] == 323
    assert queries == [question]
    assert query_embedding is None and embedding.calls == 0
    assert restored == decision
    assert mode == "decision"
    assert cache.lookup(question, None, [222])[0] == []


def test_legacy_exact_hit_is_reused_as_retrieval_and_upgraded(monkeypatch) -> None:
    question = "청년 창업 감면"
    result = {
        "user_conditions": _user_conditions(question, None),
        "embedding_ids": [111, 323],
        "prior_evidence_ids": [111],
        "hop_queries": [question],
        "evidence_cache_version": "tax-evidence-v1",
        "llm_model": "test-model",
        "evidence_decision": {"sufficient": False},
    }
    cache, embedding, _, _ = _cache(
        monkeypatch,
        exact={"cached_result": result, "created_at": datetime.now(timezone.utc)},
    )
    cache._settings = Settings(_env_file=None, llm_model="test-model")

    documents, _, query_embedding, decision, mode = cache.lookup(
        question, None, [111]
    )

    assert [document["id"] for document in documents] == [323]
    assert query_embedding is not None and embedding.calls == 1
    assert decision is None and mode == "retrieval"


def test_semantic_decision_requires_strict_similarity_and_conditions(monkeypatch) -> None:
    question = "청년 창업 감면 대상"
    conditions = _user_conditions(question, None)
    decision = {"sufficient": True}
    result = _signed_payload(question, None, {
        "user_conditions": conditions,
        "embedding_ids": [323],
        "retrieval_ids": [323],
        "embedding_version": "topic-v3",
        "decision_question": question,
        "hop_queries": [question],
        "evidence_cache_version": "tax-evidence-v1",
        "llm_model": "test-model",
        "prior_evidence_ids": [],
        "evidence_decision": decision,
    })
    cache, _, _, cursor = _cache(
        monkeypatch,
        candidates=[{
            "cached_result": result,
            "created_at": datetime.now(timezone.utc),
            "similarity": 0.97,
        }],
    )
    cache._settings = Settings(
        _env_file=None,
        llm_model="test-model",
        tax_cache_similarity_threshold=0.92,
        tax_cache_decision_similarity_threshold=0.98,
    )

    below = cache.lookup(question, None)
    assert below[3] is None and below[4] == "retrieval"

    cursor.candidates = [{
        "cached_result": result,
        "created_at": datetime.now(timezone.utc),
        "similarity": 0.99,
    }]
    strict = cache.lookup(question, None)
    assert strict[3] == decision and strict[4] == "decision"

    different_profile = cache.lookup(question, {"age": 50})  # type: ignore[arg-type]
    assert different_profile[3] is None
    assert different_profile[4] == "retrieval"


def test_startup_cache_embedding_ignores_conversation_conditions() -> None:
    standalone = "청년 창업 세액감면 대상인지"
    contextualized = (
        "경기도에서 처음 사업을 시작하고 서울에서 사업장을 옮기는 경우 "
        "제 조건이 청년 창업 세액감면 대상인지"
    )

    assert TaxRagCache._embedding_text(standalone) == (
        TaxRagCache._embedding_text(contextualized)
    )


def test_decision_cache_reuses_equivalent_phrasing_with_same_facts(monkeypatch) -> None:
    first = "서울 청년 창업 세액감면 대상인지 알려주세요"
    second = "제 조건이면 청년창업 세액감면에 해당하나요"
    profile = {
        "user_id": 1,
        "age": 29,
        "region": "서울",
        "business": {
            "industry": "소프트웨어",
            "business_type": "개인사업자",
            "founded_at": "2024-03-01",
        },
    }
    decision = {"sufficient": True}
    result = _signed_payload(first, profile, {
        "user_conditions": _user_conditions(first, profile),
        "embedding_ids": [323],
        "retrieval_ids": [323],
        "embedding_version": "topic-v3",
        "decision_question": first,
        "hop_queries": [first],
        "evidence_cache_version": "tax-evidence-v1",
        "llm_model": "test-model",
        "prior_evidence_ids": [],
        "evidence_decision": decision,
    })
    cache, embedding, _, _ = _cache(
        monkeypatch,
        exact={
            "cached_result": result,
            "created_at": datetime.now(timezone.utc),
        },
    )
    cache._settings = Settings(_env_file=None, llm_model="test-model")

    assert _decision_scope(first) == _decision_scope(second)
    assert _decision_conditions(first, profile) == _decision_conditions(
        second, profile
    )
    documents, _, query_embedding, restored, mode = cache.lookup(
        second, profile
    )

    assert documents[0]["id"] == 323
    assert query_embedding is None and embedding.calls == 0
    assert restored == decision and mode == "decision"


def test_decision_cache_does_not_cross_high_impact_profile_facts(monkeypatch) -> None:
    question = "청년 창업 세액감면 대상인지"
    first_profile = {
        "user_id": 1, "age": 29, "region": "서울",
        "business": {"industry": "소프트웨어", "business_type": None,
                     "founded_at": "2024-03-01"},
    }
    result = _signed_payload(question, first_profile, {
        "user_conditions": _user_conditions(question, first_profile),
        "embedding_ids": [323], "retrieval_ids": [323],
        "embedding_version": "topic-v3", "decision_question": question,
        "hop_queries": [question], "evidence_cache_version": "tax-evidence-v1",
        "llm_model": "test-model", "prior_evidence_ids": [],
        "evidence_decision": {"sufficient": True},
    })
    cache, embedding, _, _ = _cache(
        monkeypatch,
        exact={
            "cached_result": result,
            "created_at": datetime.now(timezone.utc),
        },
    )
    cache._settings = Settings(_env_file=None, llm_model="test-model")
    changed_profile = {**first_profile, "age": 30}

    hit = cache.lookup(question, changed_profile)  # type: ignore[arg-type]

    assert hit[0] == [] and hit[3] is None and hit[4] is None
    assert embedding.calls == 1


def test_hybrid_runtime_passes_postgres_index_to_tax_cache(monkeypatch) -> None:
    from src.serving import rag_routes

    postgres = object.__new__(PostgresVectorSearch)
    hybrid = HybridSearch(
        dense_search=postgres, chunks=[], dense_candidate_k=20,
        bm25_candidate_k=20, rrf_k=60,
    )
    runtime = RagRuntime(embedding_factory=lambda: object(), llm_factory=lambda: object())
    runtime.set_index(hybrid, document_count=1, chunk_count=1, index_source="cache")
    captured = {}

    def fake_build_graph(_llm, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(rag_routes, "build_graph", fake_build_graph)
    runtime.require_graph(Settings(_env_file=None, tax_cache_enabled=True), None)
    assert isinstance(captured["tax_cache"], TaxRagCache)
    assert captured["tax_cache"]._vector_search is postgres
