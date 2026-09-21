from __future__ import annotations

import asyncio

from src.core.config import Settings
from src.rag.graph import build_graph
from src.serving import rag_routes
from src.vectorstores.hybrid import HybridSearch
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


def test_live_runtime_wires_postgres_dense_to_nori(monkeypatch) -> None:
    postgres = object.__new__(PostgresVectorSearch)
    legacy = HybridSearch(dense_search=postgres, chunks=[], dense_candidate_k=20,
                          bm25_candidate_k=20, rrf_k=60)
    runtime = rag_routes.RagRuntime(embedding_factory=lambda: object(),
                                     llm_factory=lambda: object())
    runtime.set_index(legacy, document_count=1, chunk_count=1, index_source="cache")
    lexical = Backend([])
    monkeypatch.setattr(rag_routes, "ElasticsearchBM25Search", lambda _settings: lexical)
    settings = Settings(_env_file=None, tax_cache_enabled=False)
    wired = runtime.require_hybrid_index(settings)
    assert isinstance(wired, NoriHybridSearch)
    assert wired.dense_search is postgres
    assert wired.bm25_search is lexical
    assert wired.retrieval_pool_k == 40
    assert wired.rerank_candidate_k == 20


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


def test_nori_config_rejects_pool_smaller_than_rerank_budget() -> None:
    import pytest
    with pytest.raises(ValueError, match="NORI_RETRIEVAL_POOL_K"):
        Settings(_env_file=None, nori_retrieval_pool_k=19,
                 cohere_rerank_candidate_k=20)
