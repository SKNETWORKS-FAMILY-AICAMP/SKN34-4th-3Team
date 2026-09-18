import pytest

from src.core.config import Settings
from src.data.contracts import PolicyRow
from src.data.postgres_repository import (
    build_policy_content,
    clean_policy,
    clean_text,
    prepare_policies,
)


@pytest.mark.parametrize("value", [None, "", "   \r\n\t  ", "\u200b"])
def test_clean_text_returns_none_for_empty_values(value: object | None) -> None:
    assert clean_text(value) is None


def test_clean_text_removes_html_entities_and_control_characters() -> None:
    raw_text = "<p>청년&nbsp;지원</p>\u200b\x00\r\n  사업"

    assert clean_text(raw_text) == "청년 지원 사업"


def test_clean_text_normalizes_list_markers() -> None:
    raw_text = (
        "① 지원대상  ② 지원내용\n"
        "○ 신청방법 ● 제출서류 ■ 유의사항 ㅇ 지원기준 ☞ 신청안내"
    )

    assert clean_text(raw_text) == (
        "1. 지원대상 2. 지원내용 - 신청방법 - 제출서류 - 유의사항 "
        "- 지원기준 - 신청안내"
    )


def test_clean_text_normalizes_inline_arrow_and_spaced_label() -> None:
    raw_text = "지 원 대 상 : 청년 (홈페이지▶자격정보▶검색)"

    assert clean_text(raw_text) == "지원대상 : 청년 (홈페이지 - 자격정보 - 검색)"


def test_clean_text_preserves_meaningful_korean_symbols() -> None:
    raw_text = (
        "만 19세~39세 / 금리 2.0% - 최대 1억원, "
        "중소기업·소상공인 (₩ 지원)"
    )

    assert clean_text(raw_text) == raw_text


def test_clean_text_preserves_footnote_markers_and_negative_sign() -> None:
    raw_text = "* 청년: 19세~39세 ** 중·장년: 40세~65세 -1억원"

    assert clean_text(raw_text) == raw_text


def test_clean_policy_preserves_id_and_omits_missing_content_fields() -> None:
    cleaned_policy = clean_policy(
        {
            "id": 7,
            "title": "  청년전용창업자금  ",
            "region": None,
            "industry": "고용·창업",
            "target": "○ 만 39세 이하",
            "benefit": None,
        }
    )

    assert cleaned_policy["policy_id"] == 7
    assert cleaned_policy["region"] is None
    assert cleaned_policy["target"] == "만 39세 이하"
    assert build_policy_content(cleaned_policy) == (
        "정책명: 청년전용창업자금\n"
        "분야: 고용·창업\n"
        "지원대상: 만 39세 이하"
    )


def test_prepare_policies_builds_content_and_minimum_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_rows: list[PolicyRow] = [
        {
            "id": 7,
            "title": "청년전용창업자금",
            "region": None,
            "industry": "고용·창업",
            "target": "대표자가 만 39세 이하인 자",
            "benefit": "시설자금 및 사업화 자금 지원",
        }
    ]
    monkeypatch.setattr(
        "src.data.postgres_repository.load_policies",
        lambda _settings: policy_rows,
    )

    prepared_policies = prepare_policies(Settings(_env_file=None))

    assert prepared_policies == [
        {
            "policy_id": 7,
            "content": (
                "정책명: 청년전용창업자금\n"
                "분야: 고용·창업\n"
                "지원대상: 대표자가 만 39세 이하인 자\n"
                "지원내용: 시설자금 및 사업화 자금 지원"
            ),
            "metadata": {
                "title": "청년전용창업자금",
                "industry": "고용·창업",
            },
        }
    ]
