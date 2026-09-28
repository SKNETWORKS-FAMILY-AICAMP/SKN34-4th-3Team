from src.evaluation.nori_cross_fields_sweep import (
    evaluate_minimum_should_match,
    render_markdown_report,
    validate_percentages,
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


def test_sweep_reuses_dense_and_passes_cross_fields_options(monkeypatch) -> None:
    import src.evaluation.nori_cross_fields_sweep as module

    dense_calls: list[dict[str, object]] = []
    elastic_calls: list[dict[str, object]] = []

    class _FakeDenseSearch:
        def __init__(self, **_: object) -> None:
            pass

        def search(self, *_: object, **kwargs: object) -> list[dict[str, object]]:
            dense_calls.append(kwargs)
            return [_result(1), _result(2)]

    class _FakeElasticsearchBM25:
        def __init__(self, _: object) -> None:
            pass

        def ready(self) -> bool:
            return True

        def search(self, *_: object, **kwargs: object) -> list[dict[str, object]]:
            elastic_calls.append(kwargs)
            return [_result(1), _result(3)]

    monkeypatch.setattr(module, "get_embedding_model", lambda: object())
    monkeypatch.setattr(module, "PostgresVectorSearch", _FakeDenseSearch)
    monkeypatch.setattr(module, "ElasticsearchBM25Search", _FakeElasticsearchBM25)

    class _Settings:
        hybrid_rrf_k = 60
        elasticsearch_index_alias = "rag-documents"

    report = evaluate_minimum_should_match(
        [
            {
                "case_id": "policy-1",
                "question": "청년 창업 지원",
                "relevant_policy_ids": [1],
            }
        ],
        settings=_Settings(),  # type: ignore[arg-type]
        percentages=[10, 30, 50],
        top_k=1,
        candidate_k=2,
    )

    assert len(dense_calls) == 1
    assert [call["minimum_should_match"] for call in elastic_calls] == [
        "10%",
        "30%",
        "50%",
    ]
    assert all(call["multi_match_type"] == "cross_fields" for call in elastic_calls)
    assert report["bm25"]["10"]["hit_at_k"] == 1.0
    assert report["hybrid"]["50"]["candidate_hit_at_k"] == 1.0


def test_markdown_contains_only_aggregate_metric_tables() -> None:
    metrics = {
        "precision_at_k": 0.2,
        "recall_at_k": 1.0,
        "mrr": 0.5,
        "map_at_k": 0.5,
        "hit_at_k": 1.0,
        "average_latency_ms": 12.5,
        "candidate_recall_at_k": 1.0,
        "candidate_hit_at_k": 1.0,
    }

    markdown = render_markdown_report(
        {"bm25": {"30": metrics}, "hybrid": {"30": metrics}},
        top_k=5,
        candidate_k=20,
    )

    assert "| 30% | 0.2000 | 1.0000 |" in markdown
    assert "Recall@20" in markdown
    assert "question" not in markdown
    assert "case_id" not in markdown
    assert "해석" not in markdown


def test_percentage_validation_sorts_deduplicates_and_rejects_out_of_range() -> None:
    assert validate_percentages([50, 10, 30, 10]) == (10, 30, 50)

    try:
        validate_percentages([5, 30])
    except ValueError as error:
        assert "between 10 and 50" in str(error)
    else:
        raise AssertionError("out-of-range percentage must fail")
