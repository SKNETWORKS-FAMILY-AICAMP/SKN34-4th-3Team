import pytest

from src.evaluation.nori_candidate_pool_ab import (
    _find_exact_saturation,
    evaluate_candidate_pools,
    render_markdown_report,
)


def _result(policy_id: int) -> dict[str, object]:
    return {
        "chunk_id": f"policy-{policy_id}",
        "policy_id": policy_id,
        "title": f"정책 {policy_id}",
        "source": f"db://policies/{policy_id}",
        "page": 1,
        "content": "검색 본문",
        "source_type": "policy",
        "source_id": policy_id,
        "score": 1.0,
    }


def test_candidate_pool_evaluation_changes_only_unique_pool_size(monkeypatch) -> None:
    import src.evaluation.nori_candidate_pool_ab as module

    class _FakeEmbedding:
        calls = 0

        def embed_query(self, _: str) -> list[float]:
            self.calls += 1
            return [0.1]

        def embed_documents(self, _: list[str]) -> list[list[float]]:
            raise AssertionError("document embedding must not run")

    embedding = _FakeEmbedding()
    search_calls: list[tuple[str, int, bool]] = []

    class _FakeDense:
        def __init__(self, *, embedding: object, settings: object) -> None:
            del settings
            self.embedding = embedding

        def search(self, query: str, **kwargs: object) -> list[dict[str, object]]:
            self.embedding.embed_query(query)  # type: ignore[attr-defined]
            pool_k = int(kwargs["top_k"])
            search_calls.append(("dense", pool_k, bool(kwargs["unique_policy_ids"])))
            return [_result(value) for value in range(1, pool_k + 1)]

    class _FakeNori:
        def __init__(self, _: object) -> None:
            pass

        def ready(self) -> bool:
            return True

        def search(self, _: str, **kwargs: object) -> list[dict[str, object]]:
            pool_k = int(kwargs["top_k"])
            search_calls.append(("nori", pool_k, bool(kwargs["unique_policy_ids"])))
            return [_result(value) for value in range(1, pool_k + 1)]

    monkeypatch.setattr(module, "get_embedding_model", lambda: embedding)
    monkeypatch.setattr(module, "PostgresVectorSearch", _FakeDense)
    monkeypatch.setattr(module, "ElasticsearchBM25Search", _FakeNori)

    class _Settings:
        hybrid_rrf_k = 60
        elasticsearch_index_alias = "rag-documents"

    report = evaluate_candidate_pools(
        [{"case_id": "p1", "question": "질문", "relevant_policy_ids": [1]}],
        settings=_Settings(),  # type: ignore[arg-type]
        retrieval_pool_sizes=[20, 30],
        rerank_candidate_k=20,
        top_k=5,
    )

    assert embedding.calls == 1
    assert search_calls == [
        ("dense", 20, True),
        ("nori", 20, True),
        ("dense", 30, True),
        ("nori", 30, True),
    ]
    assert report["cohere_call_count"] == 0
    assert report["rerank_used"] is False
    assert "cases" not in report


def test_candidate_pool_rejects_non_unique_results(monkeypatch) -> None:
    import src.evaluation.nori_candidate_pool_ab as module

    class _Embedding:
        def embed_query(self, _: str) -> list[float]:
            return [0.1]

    class _DuplicateSearch:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def ready(self) -> bool:
            return True

        def search(self, *_: object, **__: object) -> list[dict[str, object]]:
            return [_result(1)] * 20

    monkeypatch.setattr(module, "get_embedding_model", _Embedding)
    monkeypatch.setattr(module, "PostgresVectorSearch", _DuplicateSearch)
    monkeypatch.setattr(module, "ElasticsearchBM25Search", _DuplicateSearch)

    class _Settings:
        hybrid_rrf_k = 60
        elasticsearch_index_alias = "rag-documents"

    with pytest.raises(RuntimeError, match="unique policies"):
        evaluate_candidate_pools(
            [{"case_id": "p1", "question": "질문", "relevant_policy_ids": [1]}],
            settings=_Settings(),  # type: ignore[arg-type]
            retrieval_pool_sizes=[20],
        )


def test_report_contains_metrics_deltas_and_saturation_only() -> None:
    results = [
        {
            "retrieval_pool_k": pool_k,
            "recall_at_20": recall,
            "hit_at_20": recall,
            "recall_at_5": 0.5,
            "hit_at_5": 0.6,
            "mrr": 0.4,
            "map_at_5": 0.3,
            "average_retrieval_latency_ms": float(pool_k),
        }
        for pool_k, recall in ((20, 0.7), (30, 0.8), (40, 0.8), (50, 0.8))
    ]
    report = {
        "results": results,
        "deltas_from_previous_pool": [
            {
                "from_pool_k": 20,
                "to_pool_k": 30,
                "recall_at_20_delta": 0.1,
                "hit_at_20_delta": 0.1,
                "recall_at_5_delta": 0.0,
                "mrr_delta": 0.0,
                "map_at_5_delta": 0.0,
                "average_retrieval_latency_ms_delta": 10.0,
            }
        ],
        "exact_saturation_pool_k": 30,
        "recommended_pool_k_for_cohere_validation": 30,
    }

    markdown = render_markdown_report(report)

    assert "| 20 | 0.7000 |" in markdown
    assert "| 20→30 | +0.1000 |" in markdown
    assert "포화 시작점: Pool K=30" in markdown
    assert "문항별" not in markdown


def test_exact_saturation_requires_both_primary_metrics_to_stop_improving() -> None:
    results = [
        {"retrieval_pool_k": 20, "recall_at_20": 0.7, "hit_at_20": 0.8},
        {"retrieval_pool_k": 30, "recall_at_20": 0.8, "hit_at_20": 0.9},
        {"retrieval_pool_k": 40, "recall_at_20": 0.8, "hit_at_20": 0.9},
        {"retrieval_pool_k": 50, "recall_at_20": 0.8, "hit_at_20": 0.9},
    ]

    assert _find_exact_saturation(results) == 30
