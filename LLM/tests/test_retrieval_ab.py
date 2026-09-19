import json
import sys

from src.evaluation.retrieval_ab import (
    _parse_args,
    RequestIntervalLimiter,
    load_holdout250_policy_cases,
    load_retrieval_cases,
    policy_level_rrf,
    render_markdown_report,
)
from src.vectorstores.elasticsearch import ElasticsearchBM25Search


def _result(chunk_id: str, policy_id: int, score: float = 1.0) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "policy_id": policy_id,
        "title": f"정책 {policy_id}",
        "source": f"db://policies/{policy_id}",
        "page": 1,
        "content": "검색 본문",
        "source_type": "policy",
        "source_id": policy_id,
        "score": score,
    }


def test_policy_level_rrf_deduplicates_multiple_chunks_from_same_policy() -> None:
    dense = [_result("p1-c1", 1), _result("p1-c2", 1), _result("p2-c1", 2)]
    lexical = [_result("policy-2", 2), _result("policy-1", 1)]

    fused = policy_level_rrf(dense, lexical, rrf_k=60, top_k=5)

    assert [result["policy_id"] for result in fused] == [1, 2]


def test_load_retrieval_cases_excludes_guardrail_cases(tmp_path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "case_id": "policy-1",
                    "question": "지원 정책",
                    "relevant_policy_ids": [1],
                    "should_block": False,
                },
                {
                    "case_id": "blocked-1",
                    "question": "날씨",
                    "relevant_policy_ids": [],
                    "should_block": True,
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cases = load_retrieval_cases(path)

    assert cases == [
        {
            "case_id": "policy-1",
            "question": "지원 정책",
            "relevant_policy_ids": [1],
        }
    ]


class _FakeIndices:
    def exists_alias(self, *, name: str) -> bool:
        return name == "rag-documents"


class _FakeElasticsearch:
    indices = _FakeIndices()

    def count(self, *, index: str) -> dict[str, int]:
        return {"count": 1}

    def search(self, **_: object) -> dict[str, object]:
        return {
            "hits": {
                "hits": [
                    {
                        "_id": "policy-7",
                        "_score": 4.2,
                        "_source": {
                            "document_id": "policy-7",
                            "source_type": "policy",
                            "source_id": 7,
                            "policy_id": 7,
                            "title": "청년 정책",
                            "source": "db://policies/7",
                            "content": "청년 창업 지원",
                        },
                    }
                ]
            }
        }


def test_elasticsearch_bm25_maps_hit_to_common_search_contract() -> None:
    from src.core.config import Settings

    search = ElasticsearchBM25Search(
        Settings(_env_file=None), client=_FakeElasticsearch()  # type: ignore[arg-type]
    )

    assert search.ready() is True
    results = search.search("청년 창업", require_policy_id=True)

    assert results[0]["chunk_id"] == "policy-7"
    assert results[0]["policy_id"] == 7
    assert results[0]["score"] == 4.2


def test_cli_enables_rerank_by_default(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["retrieval-ab", "--output", str(tmp_path / "result.json")],
    )

    args = _parse_args()

    assert args.with_rerank is True
    assert args.cases is None
    assert args.rerank_min_interval_seconds == 1.6


def test_holdout250_policy_subset_contains_only_63_policy_cases() -> None:
    cases = load_holdout250_policy_cases()

    assert len(cases) == 63
    assert all(case["relevant_policy_ids"] for case in cases)
    assert all(case["case_id"].startswith("holdout-policy-") for case in cases)


def test_markdown_report_contains_final_comparison_and_case_rankings() -> None:
    metrics = {
        "precision_at_k": 0.2,
        "recall_at_k": 1.0,
        "mrr": 0.5,
        "map_at_k": 0.5,
        "hit_at_k": 1.0,
        "average_latency_ms": 12.5,
    }
    report = {
        "suite": "test-policy-suite",
        "case_count": 1,
        "top_k": 5,
        "candidate_k": 20,
        "with_rerank": True,
        "rerank_min_interval_seconds": 1.6,
        "memory_bm25": metrics,
        "elasticsearch_bm25": {**metrics, "recall_at_k": 0.5},
        "memory_bm25_rerank": metrics,
        "elasticsearch_bm25_rerank": {**metrics, "mrr": 1.0},
        "cases": [
            {
                "case_id": "policy|1",
                "relevant_policy_ids": [7],
                "memory_bm25": {
                    "rerank": {
                        "ranking": [8, 7],
                        "metrics": {"hit_at_k": 1.0},
                    }
                },
                "elasticsearch_bm25": {
                    "rerank": {
                        "ranking": [7, 8],
                        "metrics": {"hit_at_k": 1.0},
                    }
                },
            }
        ],
    }

    markdown = render_markdown_report(report)

    assert "# 검색 방식 A/B 평가 보고서" in markdown
    assert "평가셋: test-policy-suite" in markdown
    assert "| MRR | 0.5000 | 1.0000 | +0.5000 |" in markdown
    assert "policy\\|1" in markdown
    assert "8, 7" in markdown


def test_request_interval_limiter_waits_between_consecutive_calls() -> None:
    current_time = [10.0]
    requested_sleeps: list[float] = []

    def clock() -> float:
        return current_time[0]

    def sleeper(seconds: float) -> None:
        requested_sleeps.append(seconds)
        current_time[0] += seconds

    limiter = RequestIntervalLimiter(1.6, clock=clock, sleeper=sleeper)

    assert limiter.wait() == 0.0
    current_time[0] += 0.4
    assert limiter.wait() == 1.2
    assert requested_sleeps == [1.2]
