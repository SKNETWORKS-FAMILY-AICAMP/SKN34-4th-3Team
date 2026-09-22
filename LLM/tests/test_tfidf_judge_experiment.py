from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from ML import tfidf_judge_experiment as experiment


def sample_rows() -> pd.DataFrame:
    rows = []
    for category in ("policy", "tax"):
        for label in (0, 1):
            for number in range(12):
                row = {"case_id": f"{category}-{label}-{number}", "category": category,
                       "question": f"{category} 신청 조건 {number} 문의", "label": label}
                row.update({name: float(number + label) for name in experiment.NUMERIC_FEATURES})
                for rank in range(1, 6):
                    row[f"evidence_{rank}"] = f"{category} 신청 조건 근거 {rank} 내용 반복"
                row["evidence_joined"] = "\n".join(row[f"evidence_{rank}"] for rank in range(1, 6))
                rows.append(row)
    return pd.DataFrame(rows)


def test_join_rejects_mismatch_and_excludes_gold(monkeypatch, tmp_path):
    frame = sample_rows().iloc[:8].copy()
    frame["status"] = "ok"
    monkeypatch.setattr(experiment, "load_source", lambda path: frame)
    audit = frame[["case_id", "category", "question", "label", "status"]].copy()
    audit["evidence_texts"] = [json.dumps([f"근거 {rank}" for rank in range(5)])] * len(audit)
    audit["eval_gold_answer"] = "never model input"
    path = tmp_path / "audit.csv"
    audit.to_csv(path, index=False)
    joined = experiment.load_joined(tmp_path / "source.csv", path)
    assert "eval_gold_answer" not in joined
    assert "label" in joined  # kept only for y/diagnostics, not selected by make_pipeline
    assert joined.evidence_1.iloc[0] == "근거 0"
    audit.loc[0, "label"] = 1 - audit.loc[0, "label"]
    audit.to_csv(path, index=False)
    with pytest.raises(ValueError, match="label mismatch"):
        experiment.load_joined(tmp_path / "source.csv", path)
    audit.loc[0, "label"] = frame.label.iloc[0]
    audit.loc[0, "evidence_texts"] = json.dumps(["only one"])
    audit.to_csv(path, index=False)
    with pytest.raises(ValueError, match="five nonempty"):
        experiment.load_joined(tmp_path / "source.csv", path)


def test_same_candidates_and_oof_threshold_direction():
    assert experiment.sampled_candidates() == experiment.sampled_candidates()
    assert len(experiment.sampled_candidates()) == 12
    y = np.array([0] * 10 + [1] * 10)
    margins = np.array([-2.] * 9 + [1.2] + [2.] * 9 + [-1.])
    threshold, result = experiment.choose_threshold(y, margins)
    assert result == experiment.metrics(y, margins, threshold)
    assert result["fp_0_to_1"] <= 1
    assert result["fpr"] <= 0.10


def test_three_arms_are_fold_fit_and_have_no_gold_columns():
    train = sample_rows()
    folds = experiment.folds_for(train, 2)
    params = {"analyzer": "char", "ngram_range": (2, 4), "min_df": 2,
              "C": 0.1, "class_weight": "balanced"}
    for arm in experiment.ARMS:
        model = experiment.make_pipeline(arm, "linear_svm", params)
        selected = set()
        for _, _, columns in model.named_steps["features"].transformers:
            selected.update([columns] if isinstance(columns, str) else columns)
        assert "label" not in selected
        assert "eval_gold_answer" not in selected
        result = experiment.assess(train, folds, arm, "linear_svm", params)
        assert len(result["folds"]) == 2
        assert result["cv"]["fpr"] <= 0.10
        assert result["score_type"] == "margin"


def test_tfidf_vocabulary_excludes_held_out_text():
    frame = sample_rows()
    held_out = frame.iloc[-1:].copy()
    held_out.loc[held_out.index[0], "question"] = "qzxvlmnpqzxv"
    params = {"analyzer": "char", "ngram_range": (2, 4), "min_df": 2,
              "C": 0.1, "class_weight": None}
    model = experiment.make_pipeline("B_question_evidence", "logistic_regression", params)
    model.fit(frame.iloc[:-1], frame.label.iloc[:-1])
    question_vocab = model.named_steps["features"].named_transformers_["question"].vocabulary_
    similarity_vocab = model.named_steps["features"].named_transformers_["similarity"].vectorizer_.vocabulary_
    assert "qzxv" not in question_vocab
    assert "qzxv" not in similarity_vocab
    assert model.predict(held_out).shape == (1,)


def test_final_test_stays_sealed_after_failed_validation(tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    (output / "search_results.json").write_text(
        json.dumps({"selected": "C_evidence_numeric/linear_svm",
                    "validation_target_met": False}), encoding="utf-8")
    with pytest.raises(ValueError, match="Test stays sealed"):
        experiment.final_test(output=output)
    assert not (output / "test_results.json").exists()


def test_smoke_run_cannot_open_test_even_if_validation_passed(tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    (output / "search_results.json").write_text(
        json.dumps({"selected": "C_evidence_numeric/logistic_regression",
                    "validation_target_met": True, "search_complete": False}), encoding="utf-8")
    with pytest.raises(ValueError, match="Test stays sealed"):
        experiment.final_test(output=output)
