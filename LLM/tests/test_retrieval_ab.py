import json
import sys

from src.evaluation.retrieval_ab import (
    _parse_args,
    evaluate_retrievers,
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

    def __init__(self) -> None:
        self.search_kwargs: dict[str, object] = {}

    def count(self, *, index: str) -> dict[str, int]:
        return {"count": 1}

    def search(self, **kwargs: object) -> dict[str, object]:
        self.search_kwargs = kwargs
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

    client = _FakeElasticsearch()
    search = ElasticsearchBM25Search(
        Settings(_env_file=None), client=client  # type: ignore[arg-type]
    )

    assert search.ready() is True
    results = search.search(
        "청년 창업", require_policy_id=True, unique_policy_ids=True
    )

    assert results[0]["chunk_id"] == "policy-7"
    assert results[0]["policy_id"] == 7
    assert results[0]["score"] == 4.2
    assert client.search_kwargs["collapse"] == {"field": "policy_id"}
    query = client.search_kwargs["query"]  # type: ignore[assignment]
    multi_match = query["bool"]["must"][0]["multi_match"]  # type: ignore[index]
    assert multi_match["type"] == "cross_fields"
    assert multi_match["minimum_should_match"] == "25%"


def test_elasticsearch_bm25_applies_cross_fields_and_minimum_should_match() -> None:
    from src.core.config import Settings

    client = _FakeElasticsearch()
    search = ElasticsearchBM25Search(
        Settings(_env_file=None), client=client  # type: ignore[arg-type]
    )

    search.search(
        "청년 창업",
        require_policy_id=True,
        unique_policy_ids=True,
        multi_match_type="cross_fields",
        minimum_should_match="30%",
    )

    query = client.search_kwargs["query"]  # type: ignore[assignment]
    multi_match = query["bool"]["must"][0]["multi_match"]  # type: ignore[index]
    assert multi_match["type"] == "cross_fields"
    assert multi_match["minimum_should_match"] == "30%"


def test_cli_is_retrieval_only(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["retrieval-ab", "--output", str(tmp_path / "result.json")],
    )

    args = _parse_args()

    assert args.cases is None
    assert args.no_rerank is False


def test_holdout250_policy_subset_contains_only_63_policy_cases() -> None:
    cases = load_holdout250_policy_cases()

    assert len(cases) == 63
    assert all(case["relevant_policy_ids"] for case in cases)
    assert all(case["case_id"].startswith("holdout-policy-") for case in cases)


def test_markdown_report_contains_summary_without_case_rankings() -> None:
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
        "rerank_call_count": 0,
        "memory_bm25": metrics,
        "elasticsearch_bm25": {**metrics, "recall_at_k": 0.5},
        "memory_hybrid": metrics,
        "elasticsearch_hybrid": {**metrics, "mrr": 1.0},
        "memory_hybrid_candidate": {"recall_at_k": 0.8, "hit_at_k": 0.9},
        "elasticsearch_hybrid_candidate": {
            "recall_at_k": 0.9,
            "hit_at_k": 1.0,
        },
        "hit_comparison": {
            "memory_only": 0,
            "nori_only": 0,
            "both_hit": 1,
            "both_miss": 0,
        },
        "cases": [],
    }

    markdown = render_markdown_report(report)

    assert "# Nori POS Analyzer 검색 A/B 평가 보고서" in markdown
    assert "평가셋: test-policy-suite" in markdown
    assert "| MRR | 0.5000 | 1.0000 | +0.5000 |" in markdown
    assert "| Recall@20 | 0.8000 | 0.9000 | +0.1000 |" in markdown
    assert "문항별 Hybrid 결과" not in markdown
    assert "Cohere 호출: 0회" in markdown
    assert "사용자 사전: 미사용" in markdown


def test_evaluate_retrievers_reports_bm25_and_hybrid_without_rerank(monkeypatch) -> None:
    import src.evaluation.retrieval_ab as module

    class _FakeDenseSearch:
        def __init__(self, **_: object) -> None:
            pass

        def get_chunks(self) -> list[dict[str, object]]:
            return [_result("dense-1", 1)]

        def search(self, *_: object, **__: object) -> list[dict[str, object]]:
            return [_result("dense-1", 1)]

    class _FakeMemoryBM25:
        def __init__(self, _: object) -> None:
            pass

        def search(self, *_: object, **__: object) -> list[dict[str, object]]:
            return [_result("memory-1", 1)]

    class _FakeElasticsearchBM25:
        def __init__(self, _: object) -> None:
            pass

        def ready(self) -> bool:
            return True

        def search(self, *_: object, **__: object) -> list[dict[str, object]]:
            return [_result("elastic-1", 1)]

    monkeypatch.setattr(module, "get_embedding_model", lambda: object())
    monkeypatch.setattr(module, "PostgresVectorSearch", _FakeDenseSearch)
    monkeypatch.setattr(module, "BM25Search", _FakeMemoryBM25)
    monkeypatch.setattr(module, "ElasticsearchBM25Search", _FakeElasticsearchBM25)

    class _Settings:
        hybrid_rrf_k = 60
        elasticsearch_index_alias = "rag-documents"

    report = evaluate_retrievers(
        [
            {
                "case_id": "policy-1",
                "question": "청년 창업 지원",
                "relevant_policy_ids": [1],
            }
        ],
        settings=_Settings(),  # type: ignore[arg-type]
        top_k=1,
        candidate_k=1,
    )

    assert report["rerank_call_count"] == 0
    assert report["memory_bm25"]["hit_at_k"] == 1.0
    assert report["elasticsearch_bm25"]["hit_at_k"] == 1.0
    assert report["memory_hybrid"]["hit_at_k"] == 1.0
    assert report["elasticsearch_hybrid"]["hit_at_k"] == 1.0
    assert report["memory_hybrid_candidate"]["recall_at_k"] == 1.0
    assert report["elasticsearch_hybrid_candidate"]["hit_at_k"] == 1.0
