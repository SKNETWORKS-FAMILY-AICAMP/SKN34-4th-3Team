from __future__ import annotations

import asyncio

from elasticsearch import ConnectionError as ElasticsearchConnectionError

from src.core.config import Settings
from src.rag.graph import build_graph
from src.serving import rag_routes
from src.vectorstores.hybrid import BM25Search, HybridSearch
from src.vectorstores.nori_hybrid import NoriHybridSearch, merge_unique_sources, source_level_rrf
from src.vectorstores.postgres import PostgresVectorSearch
from tests.test_graph import _router_llm


def doc(source_id: int, *, policy_id: int | None = None, chunk: int = 0) -> dict:
    return {
        "chunk_id": f"{source_id}-{chunk}", "policy_id": policy_id,
        "source_type": "tax_document" if policy_id is None else "policy",
        "source_id": source_id, "title": f"title {source_id}", "source": "test",
        "page": 1, "content": "content", "score": 0.9,
    }


class Backend:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents
        self.calls: list[dict] = []

    def search(self, _query: str, **options: object) -> list[dict]:
        self.calls.append(options)
        return self.documents[: int(options["top_k"])]


def test_policy_nori_uses_unique_top40_before_top20_rrf() -> None:
    dense = Backend([doc(i, policy_id=i) for i in range(1, 41)])
    lexical = Backend([doc(i, policy_id=i, chunk=1) for i in range(21, 61)])
    search = NoriHybridSearch(dense_search=dense, bm25_search=lexical)
    dense_docs, bm25_docs, fused = search.search_stages(
        "question", source_types=("policy", "announcement"), require_policy_id=True,
    )
    assert len(dense_docs) == len(bm25_docs) == 40
    assert len(fused) == len({row["policy_id"] for row in fused}) == 20
    assert dense.calls[0]["top_k"] == lexical.calls[0]["top_k"] == 40
    assert dense.calls[0]["unique_policy_ids"] is True
    assert lexical.calls[0]["unique_policy_ids"] is True


def test_tax_nori_uses_source_identity_and_rejects_chunk_duplicates() -> None:
    dense = Backend([doc(i) for i in range(40)])
    lexical = Backend([doc(i, chunk=1) for i in range(20, 60)])
    search = NoriHybridSearch(dense_search=dense, bm25_search=lexical)
    _, _, fused = search.search_stages("question", source_types=("tax_document",))
    assert len(fused) == 20
    assert len({(item["source_type"], item["source_id"]) for item in fused}) == 20
    assert dense.calls[0]["unique_source_ids"] is True
    assert lexical.calls[0]["unique_source_ids"] is True
    assert len(merge_unique_sources([doc(1)], [doc(1, chunk=2), doc(2)], unit="tax")) == 2
    assert len(source_level_rrf([[doc(1), doc(1, chunk=2)], [doc(2)]],
                                unit="tax", rrf_k=60, top_k=20)) == 2


def test_elasticsearch_failure_keeps_dense_evidence_for_policy_and_tax(caplog) -> None:
    class FailingBackend:
        def search(self, _query: str, **_options: object) -> list[dict]:
            raise ElasticsearchConnectionError("Elasticsearch unavailable")

    policy = NoriHybridSearch(
        dense_search=Backend([doc(1, policy_id=1)]), bm25_search=FailingBackend(),
    )
    tax = NoriHybridSearch(
        dense_search=Backend([doc(2)]), bm25_search=FailingBackend(),
    )

    assert policy.search_stages("question", require_policy_id=True)[2][0]["policy_id"] == 1
    assert tax.search_stages("question", source_types=("tax_document",))[2][0]["source_id"] == 2
    assert "Elasticsearch BM25 search failed" in caplog.text


def test_out_of_sync_elasticsearch_is_skipped() -> None:
    dense = Backend([doc(1, policy_id=1)])
    lexical = Backend([doc(2, policy_id=2)])
    search = NoriHybridSearch(
        dense_search=dense, bm25_search=lexical, bm25_enabled=lambda: False,
    )

    _, bm25, fused = search.search_stages("question", require_policy_id=True)

    assert bm25 == []
    assert [row["policy_id"] for row in fused] == [1]
    assert lexical.calls == []


def test_ready_uses_runtime_index_for_basic_bm25() -> None:
    runtime = rag_routes.RagRuntime()
    settings = Settings(_env_file=None, vector_store_backend="postgres", retrieval_mode="hybrid")
    assert asyncio.run(rag_routes.ready(runtime, settings)).index_ready is False
    runtime.set_index(Backend([]), document_count=1, chunk_count=1, index_source="cache")
    assert asyncio.run(rag_routes.ready(runtime, settings)).index_ready is True


def test_tax_exact_legal_lookup_remains_available() -> None:
    called = []
    expected = [doc(7)]
    def exact(law_name: str, article: str, *, top_k: int) -> list[dict]:
        called.append((law_name, article, top_k))
        return expected
    search = NoriHybridSearch(dense_search=Backend([]), bm25_search=Backend([]),
                              exact_legal_search=exact)
    assert search.search_legal_reference("some law", "6", top_k=3) == expected
    assert called == [("some law", "6", 3)]


def test_live_runtime_wires_postgres_dense_to_source_basic_bm25(monkeypatch) -> None:
    postgres = object.__new__(PostgresVectorSearch)
    legacy = HybridSearch(dense_search=postgres, chunks=[], dense_candidate_k=20,
                          bm25_candidate_k=20, rrf_k=60)
    runtime = rag_routes.RagRuntime(embedding_factory=lambda: object(),
                                     llm_factory=lambda: object())
    runtime.set_index(legacy, document_count=1, chunk_count=1, index_source="cache")
    documents = [
        {"document_id": "policy-1", "policy_id": 1, "source_type": "policy",
         "source_id": 1, "title": "지원", "source": "test", "content": "청년 지원"},
        {"document_id": "tax-2", "policy_id": None, "source_type": "tax_document",
         "source_id": 2, "title": "세금", "source": "test", "content": "세금 공제"},
    ]
    monkeypatch.setattr(rag_routes, "load_elasticsearch_source_documents", lambda _settings: documents)
    monkeypatch.setattr(postgres, "search", Backend([]).search)
    settings = Settings(_env_file=None, tax_cache_enabled=False)
    assert asyncio.run(rag_routes.ready(runtime, settings)).index_ready is False
    wired = runtime.require_hybrid_index(settings)
    assert asyncio.run(rag_routes.ready(runtime, settings)).index_ready is True
    assert isinstance(wired, NoriHybridSearch)
    assert wired.dense_search is postgres
    assert isinstance(wired.bm25_search, BM25Search)
    assert len(wired.bm25_search.get_chunks()) == 2
    assert wired.retrieval_pool_k == 40
    assert wired.rerank_candidate_k == 20
    assert wired.search("청년 지원", require_policy_id=True)[0]["policy_id"] == 1
    assert wired.search("세금 공제", source_types=("tax_document",))[0]["source_id"] == 2


def test_live_graph_hands_20_unique_policies_to_reranker() -> None:
    dense = Backend([doc(i, policy_id=i) for i in range(1, 41)])
    lexical = Backend([doc(i, policy_id=i, chunk=1) for i in range(21, 61)])
    search = NoriHybridSearch(dense_search=dense, bm25_search=lexical)
    seen = []
    def rerank(_query, documents, _top_n):
        seen.append(documents)
        return documents[:5]
    result = asyncio.run(build_graph(
        _router_llm("policy"), policy_search=search, rerank=rerank,
        settings=Settings(_env_file=None, default_top_k=5, cohere_rerank_candidate_k=20),
    ).ainvoke({"query": "청년 창업 지원 정책 알려줘"}))
    assert seen
    assert len(seen[0]) == len({item["policy_id"] for item in seen[0]}) == 20
    assert result["retrieved_docs"] == seen[0]


def test_live_graph_keeps_dense_policy_when_elasticsearch_fails() -> None:
    class FailingBackend:
        def search(self, _query: str, **_options: object) -> list[dict]:
            raise ElasticsearchConnectionError("Elasticsearch unavailable")

    search = NoriHybridSearch(
        dense_search=Backend([doc(1, policy_id=1)]), bm25_search=FailingBackend(),
    )
    result = asyncio.run(build_graph(
        _router_llm("policy"), policy_search=search,
        rerank=lambda _query, documents, _top_n: documents,
        settings=Settings(_env_file=None, default_top_k=5, cohere_rerank_candidate_k=20),
    ).ainvoke({"query": "청년 창업 지원 정책 알려줘"}))

    assert [item["policy_id"] for item in result["retrieved_docs"]] == [1]
    assert result.get("termination_reason") != "retrieval_error"


def test_nori_config_rejects_pool_smaller_than_rerank_budget() -> None:
    import pytest
    with pytest.raises(ValueError, match="NORI_RETRIEVAL_POOL_K"):
        Settings(_env_file=None, nori_retrieval_pool_k=19,
                 cohere_rerank_candidate_k=20)


def test_tax_query_variants_share_rerank_budget_and_preserve_exact_evidence():
    from src.rag.tax import build_tax_initial_search_queries
    from tests.test_tax_graph import _router_llm as tax_llm, _decision

    question = "청년창업 세액감면 조세특례제한법 제6조"
    queries = build_tax_initial_search_queries(question, normalize=False)
    assert len(queries) == 5

    class Dense(Backend):
        def search(self, query, **options):
            offset = queries.index(query) * 20
            return [doc(offset + i) for i in range(1, 21)]

    class Lexical(Backend):
        def search(self, query, **options):
            return [doc(81)] if query == queries[-1] else []

    async def evaluate(_state):
        return _decision(sufficient=True, cited_source_numbers=[1])

    candidates = []
    def rerank(_query, documents, top_n):
        candidates.extend(documents)
        return documents[:top_n]

    search = NoriHybridSearch(
        dense_search=Dense([]), bm25_search=Lexical([]),
        exact_legal_search=lambda *_args, **_kwargs: [doc(900), doc(901)],
    )
    graph = build_graph(
        tax_llm(), tax_search=search, rerank=rerank, tax_evidence_evaluator=evaluate,
        settings=Settings(_env_file=None, tax_cache_enabled=False),
    )
    result = asyncio.run(graph.ainvoke({"query": question, "category": "tax"}))

    assert result["answer_status"] == "success"
    assert len(candidates) == 20
    assert candidates[0]["source_id"] == 81
    assert len({row["source_id"] for row in candidates}) == 20

    candidates.clear()
    question = "조세특례제한법 제6조"
    queries = build_tax_initial_search_queries(question, normalize=False)
    result = asyncio.run(graph.ainvoke({"query": question, "category": "tax"}))
    assert result["answer_status"] == "success"
    assert len(candidates) == 20
    assert [row["source_id"] for row in candidates[:2]] == [900, 901]
