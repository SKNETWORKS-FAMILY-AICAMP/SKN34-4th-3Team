from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ML.build_judge_dataset import add_question_to_existing_audit, collect, selected_cases
from ML.evaluate_judge_model import evaluate
from ML.judge_single_1000_v2_loader import JudgeCase, load_cases
from ML.judge_training_graph import (
    FEATURE_COLUMNS, build_graph, extract_features, source_key, source_level_rrf,
)
from ML.split_judge_dataset import make_split, read_csv
from src.core.config import Settings
from src.vectorstores.elasticsearch import ElasticsearchBM25Search
from src.vectorstores.postgres import PostgresVectorSearch


def doc(number: int, category: str, score: float = 1.0) -> dict:
    return {
        "chunk_id": str(number), "policy_id": number if category == "policy" else None,
        "source_type": "policy" if category == "policy" else "tax_document",
        "source_id": number, "title": f"title {number}", "content": f"evidence {number}",
        "source": "fake", "page": 1, "score": score,
    }


class FakeSearch:
    def __init__(self):
        self.calls = []

    def search(self, question, **options):
        self.calls.append((question, options))
        category = "tax" if options["source_types"] == ("tax_document",) else "policy"
        return [doc(i, category, 1 - i / 100) for i in range(1, 41)]


class FakeLimiter:
    def __init__(self):
        self.calls = 0

    def wait(self):
        self.calls += 1


def test_graph_40_20_5_both_categories_and_no_gold():
    dense, bm25, limiter = FakeSearch(), FakeSearch(), FakeLimiter()
    seen = []

    def rerank(question, docs):
        assert len(docs) == 20
        seen.append(("rerank", question))
        return [{**item, "score": 0.9 - i * 0.1} for i, item in enumerate(docs[:5])]

    def judge(question, evidence):
        assert len(evidence) == 5
        seen.append(("judge", question))
        return 1

    graph = build_graph(settings=SimpleNamespace(hybrid_rrf_k=60), dense_search=dense,
                        bm25_search=bm25, rerank=rerank, judge=judge, limiter=limiter)
    for category in ("policy", "tax"):
        result = graph.invoke({"case_id": category, "category": category,
                               "question": "real question"})
        assert len(result["dense"]) == len(result["bm25"]) == 40
        assert len(result["rrf"]) == 20
        assert len(result["rerank"]) == 5
        assert result["label"] == 1
        assert set(result["features"]) == set(FEATURE_COLUMNS)
        assert result["features"]["rerank_count_ge_0_5"] == 5
    assert limiter.calls == 2
    assert all(call[1]["top_k"] == 40 for call in dense.calls + bm25.calls)
    assert dense.calls[0][1]["unique_policy_ids"] is True
    assert dense.calls[1][1]["unique_source_ids"] is True
    assert seen == [("rerank", "real question"), ("judge", "real question")] * 2


def test_tax_dedup_key_and_feature_missing():
    assert source_key(doc(1, "tax"), "tax") == ("tax_document", 1)
    first = doc(1, "tax")
    duplicate = {**first, "chunk_id": "other"}
    result = source_level_rrf([first, duplicate, doc(2, "tax")], [first],
                              category="tax", rrf_k=60)
    assert [source_key(item, "tax") for item in result] == [
        ("tax_document", 1), ("tax_document", 2)
    ]
    features = extract_features({"dense": [], "bm25": [], "rrf": [], "rerank": []})
    assert features["dense_present"] == 0
    assert features["dense_score_variance"] == 0
    assert features["rerank_count_ge_0_5"] == 0


def test_policy_rrf_uses_policy_id_across_document_types():
    policy = doc(7, "policy")
    announcement = {**policy, "source_type": "announcement", "source_id": 900,
                    "chunk_id": "announcement-900"}
    assert source_key(policy, "policy") == source_key(announcement, "policy")
    ranked = source_level_rrf([policy], [announcement], category="policy", rrf_k=60)
    assert len(ranked) == 1


def test_tax_nori_collapses_before_limit_without_dsl_change():
    class Client:
        kwargs = None
        def search(self, **kwargs):
            self.kwargs = kwargs
            return {"hits": {"hits": []}}
    client = Client()
    search = ElasticsearchBM25Search(Settings(_env_file=None), client=client)
    assert search.search("tax question", source_types=("tax_document",),
                         unique_source_ids=True, top_k=40) == []
    assert client.kwargs["size"] == 40
    assert client.kwargs["collapse"] == {"field": "source_id"}
    query = client.kwargs["query"]["bool"]
    assert query["must"][0]["multi_match"]["type"] == "cross_fields"
    assert query["must"][0]["multi_match"]["minimum_should_match"] == "25%"
    assert query["filter"] == [{"terms": {"source_type": ["tax_document"]}}]


def test_tax_dense_deduplicates_in_sql_before_limit(monkeypatch):
    import src.vectorstores.postgres as postgres
    captured = {}
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def execute(self, sql, params): captured.update(sql=sql, params=params)
        def fetchall(self): return []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def cursor(self, **_): return Cursor()
    monkeypatch.setattr(postgres, "connect_database", lambda _: Connection())
    monkeypatch.setattr(postgres, "register_vector", lambda _: None)
    search = object.__new__(PostgresVectorSearch)
    search._settings = object()
    search._embedding = SimpleNamespace(embed_query=lambda _: [0.1, 0.2])
    assert search.search("tax question", source_types=("tax_document",),
                         unique_source_ids=True, top_k=40) == []
    assert "PARTITION BY source_type, source_id" in captured["sql"]
    assert captured["sql"].index("source_rank = 1") < captured["sql"].index("LIMIT %s")
    assert captured["params"][-1] == 40


def _case(case_id: str) -> JudgeCase:
    return JudgeCase(case_id, "policy", 7, "question", 999, "gold title", "gold secret")


def test_journal_resume_retry_and_training_gold_isolation(tmp_path: Path):
    source = tmp_path / "source.csv"
    source.write_text("fixed source", encoding="utf-8")
    class Graph:
        calls = 0
        def invoke(self, payload):
            self.calls += 1
            assert set(payload) == {"case_id", "category", "question"}
            if self.calls == 1:
                raise RuntimeError("search unavailable")
            return {"label": 0, "features": {column: 0 for column in FEATURE_COLUMNS},
                    "rerank": [doc(1, "policy")]}
    graph = Graph()
    output = tmp_path / "run"
    assert collect([_case("a")], graph=graph, output_dir=output, source_path=source) == {"ok": 0, "error": 1}
    assert graph.calls == 1
    error_row = read_csv(output / "teacher_features.csv")[0]
    assert error_row["status"] == "error" and error_row["label"] == ""
    assert collect([_case("a")], graph=graph, output_dir=output,
                   source_path=source, resume=True) == {"ok": 0, "error": 1}
    assert graph.calls == 1
    assert collect([_case("a")], graph=graph, output_dir=output,
                   source_path=source, resume=True, retry_failed=True) == {"ok": 1, "error": 0}
    training = (output / "teacher_features.csv").read_text(encoding="utf-8-sig")
    audit = (output / "teacher_audit.csv").read_text(encoding="utf-8-sig")
    assert "gold secret" not in training and "eval_gold" not in training
    assert "gold secret" in audit and "title 1" in audit
    assert len(read_csv(output / "teacher_features.csv")) == 1
    assert read_csv(output / "teacher_audit.csv")[0]["question"] == "question"
    audit_path = output / "teacher_audit.csv"
    audit_rows = read_csv(audit_path)
    old_fields = [field for field in audit_rows[0] if field != "question"]
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=old_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(audit_rows)
    assert add_question_to_existing_audit(output) == 1
    restored = read_csv(audit_path)[0]
    assert restored["question"] == "question"
    assert restored["eval_gold_answer"] == "gold secret"
    with pytest.raises(FileExistsError):
        collect([_case("a")], graph=graph, output_dir=output, source_path=source)


def test_loader_path_and_balanced_limit():
    cases = load_cases()
    assert len(cases) == 1000
    sample = selected_cases(cases, 60)
    assert sum(case.category == "policy" for case in sample) == 30
    assert sum(case.category == "tax" for case in sample) == 30


def test_split_reproducibility_strata_and_group():
    rows = []
    for category in ("policy", "tax"):
        for label in ("0", "1"):
            for i in range(30):
                rows.append({"case_id": f"{category}-{label}-{i}", "category": category,
                             "label": label, "status": "ok", "question": f"{category}-{label}-{i}"})
    rows[1]["question"] = rows[0]["question"]
    left = make_split(rows, 42)
    right = make_split(rows, 42)
    assert {key: [item["case_id"] for item in value] for key, value in left.items()} == {
        key: [item["case_id"] for item in value] for key, value in right.items()
    }
    assert any({rows[0]["case_id"], rows[1]["case_id"]} <=
               {item["case_id"] for item in values} for values in left.values())
    for values in left.values():
        assert {row["category"] for row in values} == {"policy", "tax"}
        assert {row["label"] for row in values} == {"0", "1"}


def test_prediction_contract_fp_direction_and_auc():
    test = [
        {"case_id": "a", "category": "policy", "label": "0"},
        {"case_id": "b", "category": "policy", "label": "1"},
        {"case_id": "c", "category": "tax", "label": "0"},
        {"case_id": "d", "category": "tax", "label": "1"},
    ]
    prediction = [
        {"case_id": case_id, "predicted_label": predicted,
         "probability_sufficient": probability, "inference_ms": "10"}
        for case_id, predicted, probability in
        (("a", "1", "0.8"), ("b", "1", "0.9"), ("c", "0", "0.1"), ("d", "0", "0.2"))
    ]
    review = [{"case_id": row["case_id"], "teacher_label": row["label"],
               "reviewed_label": ""} for row in test]
    result = evaluate(test, prediction, review)
    assert result["overall"]["confusion_matrix"] == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}
    assert result["overall"]["fpr"] == 0.5
    assert result["overall"]["roc_auc"] == 0.75
    assert result["unreviewed_test_count"] == 4
    review[0]["reviewed_label"] = "1"
    assert evaluate(test, prediction, review)["reviewed_label_overrides"] == 1
    with pytest.raises(ValueError, match="exactly"):
        evaluate(test, prediction[:-1])
    with pytest.raises(ValueError, match="duplicate"):
        evaluate(test, prediction + [prediction[0]])
    prediction[0]["probability_sufficient"] = "1.1"
    with pytest.raises(ValueError, match="out of range"):
        evaluate(test, prediction)


def test_auc_unavailable_for_single_class():
    test = [{"case_id": "only", "category": "tax", "label": "0"}]
    predictions = [{"case_id": "only", "predicted_label": "1",
                    "probability_sufficient": "0.5", "inference_ms": "1"}]
    report = evaluate(test, predictions)
    assert report["overall"]["roc_auc"] is None
    assert report["overall"]["roc_auc_unavailable_reason"] == "single-class reference labels"
    assert report["overall"]["dangerous_fp_insufficient_to_sufficient"] == 1
