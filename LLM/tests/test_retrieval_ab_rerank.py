import sys

import pytest

from src.evaluation.retrieval_ab_rerank import (
    RequestIntervalLimiter,
    _parse_args,
    evaluate_with_rerank,
    render_markdown_report,
)


def _result(policy_id: int) -> dict[str, object]:
    return {
        "chunk_id": f"policy-{policy_id}",
        "policy_id": policy_id,
        "title": f"정책 {policy_id}",
        "source": f"db://policies/{policy_id}",
        "page": 1,
        "content": f"정책 {policy_id} 검색 본문",
        "source_type": "policy",
        "source_id": policy_id,
        "score": 1.0,
    }


def test_request_interval_limiter_keeps_calls_below_10_per_minute() -> None:
    current = [10.0]
    sleeps: list[float] = []

    def clock() -> float:
        return current[0]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        current[0] += seconds

    limiter = RequestIntervalLimiter(6.1, clock=clock, sleeper=sleeper)

    assert limiter.wait() == 0.0
    current[0] += 1.1
    assert limiter.wait() == pytest.approx(5.0)
    assert sleeps == [pytest.approx(5.0)]


def test_cli_defaults_to_pool_40_and_rerank_candidates_20(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["retrieval-ab-rerank"])

    args = _parse_args()

    assert args.retrieval_pool_k == 40
    assert args.rerank_candidate_k == 20
    assert args.top_k == 5
    assert args.rerank_min_interval_seconds == 6.1


def test_evaluation_reranks_both_unique_policy_branches(monkeypatch) -> None:
    import src.evaluation.retrieval_ab_rerank as module

    search_calls: list[dict[str, object]] = []
    rerank_calls: list[list[int]] = []

    class _FakeSearch:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def get_chunks(self) -> list[dict[str, object]]:
            return [_result(1), _result(2)]

        def ready(self) -> bool:
            return True

        def search(self, *_: object, **kwargs: object) -> list[dict[str, object]]:
            search_calls.append(kwargs)
            return [
                _result(policy_id)
                for policy_id in range(1, int(kwargs["top_k"]) + 1)
            ]

    def fake_rerank(
        _query: str,
        documents: list[dict[str, object]],
        *,
        top_n: int,
        settings: object,
    ) -> list[dict[str, object]]:
        del settings
        rerank_calls.append([int(document["policy_id"]) for document in documents])
        return list(reversed(documents))[:top_n]

    monkeypatch.setattr(module, "get_embedding_model", lambda: object())
    monkeypatch.setattr(module, "PostgresVectorSearch", _FakeSearch)
    monkeypatch.setattr(module, "BM25Search", _FakeSearch)
    monkeypatch.setattr(module, "ElasticsearchBM25Search", _FakeSearch)
    monkeypatch.setattr(module, "rerank_documents", fake_rerank)

    class _NoWaitLimiter:
        def __init__(self, minimum_interval_seconds: float) -> None:
            assert minimum_interval_seconds == 6.1

        def wait(self) -> float:
            return 0.0

    monkeypatch.setattr(module, "RequestIntervalLimiter", _NoWaitLimiter)

    class _Settings:
        cohere_configured = True
        cohere_rerank_model = "rerank-test"
        hybrid_rrf_k = 60
        elasticsearch_index_alias = "rag-documents"

    report = evaluate_with_rerank(
        [
            {
                "case_id": "policy-1",
                "question": "청년 창업 지원",
                "relevant_policy_ids": [1],
            }
        ],
        settings=_Settings(),  # type: ignore[arg-type]
        top_k=1,
        retrieval_pool_k=3,
        rerank_candidate_k=2,
        rerank_min_interval_seconds=6.1,
    )

    assert report["rerank_call_count"] == 2
    assert report["retrieval_pool_k"] == 3
    assert report["rerank_candidate_k"] == 2
    assert len(rerank_calls) == 2
    assert all(call["top_k"] == 3 for call in search_calls)
    assert all(call["unique_policy_ids"] is True for call in search_calls)
    assert all(len(call) == 2 for call in rerank_calls)
    assert "cases" not in report

    markdown = render_markdown_report(report)
    assert "# Nori XSV/XSA + MSM 25% 비교" in markdown
    assert "Cohere 호출" not in markdown
    assert "지연시간" not in markdown
    assert "문항별" not in markdown
    assert "Recall@2" in markdown
