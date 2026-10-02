import asyncio
import pytest

from evaluation.run_policy_pre_answer import run_before_answer
from src.core.config import Settings
from src.rag import graph as graph_module
from src.vectorstores.nori_hybrid import NoriHybridSearch
from tests.test_graph import _router_llm
from tests.test_nori_hybrid_live import Backend, doc


def test_pre_answer_evaluation_keeps_router_and_rerank_but_skips_generation(monkeypatch):
    rerank_calls = []

    def rerank(query, documents, top_n):
        rerank_calls.append((query, top_n))
        return documents[:top_n]

    async def forbidden_generation(*args, **kwargs):
        raise AssertionError("Final generation must be skipped")

    monkeypatch.setattr(graph_module, "generate_unified_answer", forbidden_generation)
    search = NoriHybridSearch(dense_search=Backend([doc(7, policy_id=7)]),
                              bm25_search=Backend([doc(7, policy_id=7)]))
    graph = graph_module.build_graph(_router_llm("policy"), policy_search=search,
        rerank=rerank, settings=Settings(_env_file=None, cohere_rerank_candidate_k=20, langsmith_tracing=False))
    state, timings = asyncio.run(run_before_answer(graph, {"query": "청년 창업 지원사업 알려줘", "top_k": 5}))

    assert state["route"] == "policy"
    assert {"router", "policy_node"}.issubset(timings)
    assert "answer" not in timings
    assert not state.get("answer")
    assert [d["policy_id"] for d in state["reranked_docs"]] == [7]
    assert rerank_calls == [("청년 창업 지원사업 알려줘", 20)]


def test_policy_graph_groups_query_variants_by_backend():
    shared = doc(8, policy_id=8)
    dense_only = doc(7, policy_id=7)

    class DenseBackend(Backend):
        def search(self, query, **options):
            self.calls.append(options)
            return [shared, dense_only] if "사용자 조건:" in query else [dense_only, shared]

    dense = DenseBackend([])
    lexical = Backend([shared])
    search = NoriHybridSearch(dense_search=dense, bm25_search=lexical)
    graph = graph_module.build_graph(_router_llm("policy", personalized=True), policy_search=search,
        rerank=lambda query, documents, top_n: documents[:top_n],
        settings=Settings(_env_file=None, cohere_rerank_candidate_k=20, langsmith_tracing=False))
    state, _ = asyncio.run(run_before_answer(graph, {
        "query": "서울 창업 공간", "top_k": 5, "user_context": {
            "user_id": 1, "age": 25, "region": "서울",
            "business": {"industry": "IT", "business_type": "개인사업자", "founded_at": "2025-01-01"},
        },
    }))
    assert len(dense.calls) == len(lexical.calls) == 2
    scores = {d["policy_id"]: d["score"] for d in state["retrieved_docs"]}
    assert scores[8] == pytest.approx(1.0)
    assert scores[7] == pytest.approx(0.5)
    assert len(state["policy_search_queries"]) == 2
    assert not state.get("answer")
