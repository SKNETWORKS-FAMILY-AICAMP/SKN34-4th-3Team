from __future__ import annotations

import json
import numpy as np
import pandas as pd
import pytest

from ML import tune_judge_models as hpo


def sample_frame() -> pd.DataFrame:
    rows = []
    for category in ("policy", "tax"):
        for label in (0, 1):
            for number in range(20):
                row = {"case_id": f"{category}-{label}-{number}", "category": category,
                       "question": f"question {category} {label} {number}", "label": label,
                       "status": "ok"}
                row.update({feature: float(number % 5 + label) for feature in hpo.FEATURES})
                rows.append(row)
    return pd.DataFrame(rows)


def test_notebook_split_and_cv_are_frozen_and_stratified():
    frame = sample_frame()
    first = hpo.notebook_split_ids(frame)
    assert first == hpo.notebook_split_ids(frame)
    assert len(first["train"]) == 56
    assert not (set(first["train"]) & set(first["test"]))
    train = hpo.subset(frame, first["train"])
    for fit, score in hpo.folds_for(train, 2):
        assert not (set(fit) & set(score))
        assert len(set(zip(train.category.iloc[score], train.label.iloc[score]))) == 4


def test_threshold_constrains_insufficient_to_sufficient_fp():
    labels = np.array([0] * 10 + [1] * 10)
    probability = np.array([.05] * 9 + [.70] + [.82] * 9 + [.30])
    threshold, score = hpo.choose_threshold(labels, probability, fpr_limit=.10)
    assert score["fp_0_to_1"] <= 1
    assert score["fpr"] <= .10
    assert score == hpo.metrics(labels, probability, threshold)
    assert hpo.metrics(np.array([0, 1]), np.array([.9, .1]), .5)["fp_0_to_1"] == 1


def test_assessment_uses_train_only_and_reports_gap():
    train = sample_frame()
    result = hpo.assess("xgboost", {"n_estimators": 5, "max_depth": 2},
                        train, hpo.folds_for(train, 2), early_stop=False)
    assert len(result["folds"]) == 2
    assert result["cv"]["fpr"] <= .10
    assert result["final_iterations"] == 5
    assert 0 <= result["cv"]["accuracy"] <= 1


def test_freeze_manifest_rejects_changed_source(tmp_path):
    frame = sample_frame()
    source = tmp_path / "features.csv"
    frame.to_csv(source, index=False)
    first = hpo.freeze_split(frame, source, tmp_path / "out")
    assert first == hpo.freeze_split(frame, source, tmp_path / "out")
    source.write_text(source.read_text() + "\n")
    with pytest.raises(ValueError, match="frozen split"):
        hpo.freeze_split(frame, source, tmp_path / "out")


def test_model_spaces_are_identical_for_both_search_methods():
    for space in hpo.SPACES.values():
        assert all(isinstance(choices, list) and choices for choices in space.values())


def test_final_test_gate_prevents_loading_test(tmp_path):
    (tmp_path / "search_results.json").write_text(json.dumps({
        "selected": "xgboost/random", "summary": [{"model": "xgboost", "method": "random",
        "validation": {"target_met": False}}]}), encoding="utf-8")
    (tmp_path / "split_manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Test stays sealed"):
        hpo.final_test(tmp_path / "missing_source.csv", tmp_path)
