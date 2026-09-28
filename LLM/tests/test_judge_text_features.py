from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from ML.augment_judge_text_features import augment_files, augment_rows
from ML.judge_text_features import TEXT_FEATURE_COLUMNS, extract_text_features


def test_title_only_tax_evidence_is_not_a_substantive_body():
    result = extract_text_features(
        "증자의 조세감면 조건은?",
        [{"title": "조세특례제한법 증자의 조세감면",
          "content": "문서명: 조세특례제한법 증자의 조세감면\n법령명: 조세특례제한법"}],
    )
    assert set(result) == set(TEXT_FEATURE_COLUMNS)
    assert result["text_top1_body_chars"] == 0
    assert result["text_top5_body_present_count"] == 0
    assert result["text_top5_title_coverage_max"] > 0
    assert result["text_top5_body_coverage_max"] == 0


def test_inline_policy_fields_region_and_top5_text_overlap():
    result = extract_text_features(
        "서울 사업자 시제품 제작 지원",
        [
            {"title": "[부산] 시제품 지원", "content": "정책명: A 지역: 부산 분야: 창업 지원내용: 시제품 제작 지원"},
            {"title": "[서울] 시제품 제작 지원", "content": "정책명: B 지역: 서울 분야: 창업 지원대상: 서울 사업자 지원내용: 시제품 제작비 지원"},
        ],
    )
    assert result["text_top5_body_present_count"] == 2
    assert result["text_top5_region_match_count"] == 1
    assert result["text_top5_region_conflict_count"] == 1
    assert result["text_top5_body_coverage_max"] > result["text_top5_body_coverage_mean"]
    assert result["text_top1_body_chars"] > 0


def test_tax_list_reference_and_empty_results():
    evidence = [{"title": "주택 면세", "content": "문서명: 주택 면세\n법령명: 세법\n내용: 면세 범위는 다음 각 호에 따른다."}]
    result = extract_text_features("주택 면세 범위", evidence)
    assert result["text_top5_list_reference_count"] == 1
    empty = extract_text_features("질문", [])
    assert all(value == 0 for value in empty.values())
    with pytest.raises(ValueError, match="at most five"):
        extract_text_features("질문", evidence * 6)


def test_augmentation_ignores_gold_and_checks_case_alignment():
    features = [{"case_id": "a", "category": "tax", "question": "기한 조건",
                 "dense_top1": "0.4", "label": "0", "status": "ok"}]
    audit = [{"case_id": "a", "question": "기한 조건", "label": "0", "status": "ok",
              "evidence_titles": json.dumps(["기한 연장"]),
              "evidence_texts": json.dumps(["문서명: 기한 연장\n내용: 기한 연장 조건"]),
              "eval_gold_answer": "secret answer", "eval_gold_source_id": "123",
              "user_id": "42"}]
    first = augment_rows(features, audit)[0]
    audit[0]["eval_gold_answer"] = "different secret"
    audit[0]["eval_gold_source_id"] = "999"
    audit[0]["user_id"] = "17"
    second = augment_rows(features, audit)[0]
    assert first == second
    assert "eval_gold_answer" not in first
    assert first["dense_top1"] == "0.4"
    assert first["label"] == "0"
    audit[0]["question"] = "different question"
    with pytest.raises(ValueError, match="question mismatch"):
        augment_rows(features, audit)


def test_augmentation_writes_separate_file_and_refuses_overwrite(tmp_path: Path):
    features_path = tmp_path / "features.csv"
    audit_path = tmp_path / "audit.csv"
    output_path = tmp_path / "enriched.csv"
    with features_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "category", "question", "dense_top1", "label", "status"])
        writer.writeheader()
        writer.writerow({"case_id": "a", "category": "policy", "question": "서울 지원", "dense_top1": "0.9", "label": "1", "status": "ok"})
    with audit_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "question", "label", "status", "evidence_titles", "evidence_texts", "eval_gold_answer"])
        writer.writeheader()
        writer.writerow({"case_id": "a", "question": "서울 지원", "label": "1", "status": "ok",
                         "evidence_titles": json.dumps(["[서울] 지원"]),
                         "evidence_texts": json.dumps(["지원내용: 서울 지원"]),
                         "eval_gold_answer": "must not leak"})
    original_features = features_path.read_bytes()
    manifest = augment_files(features_path, audit_path, output_path)
    assert manifest["row_count"] == 1
    assert features_path.read_bytes() == original_features
    with output_path.open("r", encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["text_top5_body_present_count"] == "1"
    assert "eval_gold_answer" not in row
    with pytest.raises(FileExistsError):
        augment_files(features_path, audit_path, output_path)
