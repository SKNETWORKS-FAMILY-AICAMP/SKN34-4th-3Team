import pytest

from src.core.config import Settings
from src.data.contracts import TaxDocumentRow
from src.data.postgres_repository import (
    build_tax_document_content,
    clean_tax_document,
    prepare_tax_documents,
)
from src.data.tax_normalization import (
    extract_legal_ratios,
    normalize_legal_percentage,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("10분의 1", "10분의 1(10%)"),
        ("100분의 15", "100분의 15(15%)"),
        ("100분의 75", "100분의 75(75%)"),
        ("100분의 100", "100분의 100(100%)"),
        ("1000분의 5", "1000분의 5(0.5%)"),
    ],
)
def test_normalize_legal_percentage(source: str, expected: str) -> None:
    assert normalize_legal_percentage(source) == expected


def test_legal_percentage_normalization_is_idempotent() -> None:
    normalized = normalize_legal_percentage("100분의 15(15%)")

    assert normalized == "100분의 15(15%)"
    assert normalize_legal_percentage(normalized) == normalized


def test_legal_percentage_normalizes_multiple_values_and_keeps_zero_denominator() -> None:
    source = "감면율은 10분의 1, 추가율은 1000분의 5, 예외는 0분의 1이다."

    assert normalize_legal_percentage(source) == (
        "감면율은 10분의 1(10%), 추가율은 1000분의 5(0.5%), "
        "예외는 0분의 1이다."
    )


@pytest.mark.parametrize("source", [None, "", "제6조에 따른 일반 문장"])
def test_legal_percentage_preserves_non_fraction_text(source: str | None) -> None:
    assert normalize_legal_percentage(source) == source


def test_extract_legal_ratio_returns_percent_decimal_and_context() -> None:
    ratios = extract_legal_ratios("산출세액의 100분의 75를 감면한다.")

    assert ratios == [
        {
            "raw": "100분의 75",
            "numerator": 75,
            "denominator": 100,
            "percent": 75,
            "decimal": 0.75,
            "context": "산출세액의 100분의 75를 감면한다.",
        }
    ]


def test_extract_legal_ratios_finds_every_ratio_without_changing_text() -> None:
    source = "감면은 10분의 1, 가산은 1000분의 5를 적용한다."

    ratios = extract_legal_ratios(source)

    assert [(ratio["percent"], ratio["decimal"]) for ratio in ratios] == [
        (10, 0.1),
        (0.5, 0.005),
    ]
    assert source == "감면은 10분의 1, 가산은 1000분의 5를 적용한다."


def test_clean_tax_document_uses_shared_text_cleaning() -> None:
    cleaned = clean_tax_document(
        {
            "id": 3,
            "title": "  소득세법&nbsp;제1조  ",
            "law_name": "소득세법\u200b",
            "content": "<p>납세 의무</p>\r\n  내용",
            "source": " https://example.com/law ",
        }
    )

    assert cleaned == {
        "tax_document_id": 3,
        "title": "소득세법 제1조",
        "law_name": "소득세법",
        "content": "납세 의무 내용",
        "source": "https://example.com/law",
    }
    assert build_tax_document_content(cleaned) == (
        "문서명: 소득세법 제1조\n법령명: 소득세법\n내용: 납세 의무 내용"
    )


def test_clean_tax_document_keeps_original_legal_fraction() -> None:
    cleaned = clean_tax_document(
        {
            "id": 8,
            "title": "감면 규정",
            "law_name": "조세특례제한법",
            "content": "산출세액의 100분의 75를 감면한다.",
            "source": "https://example.com/100분의15",
        }
    )

    assert cleaned["content"] == "산출세액의 100분의 75를 감면한다."
    assert cleaned["source"] == "https://example.com/100분의15"


def test_prepare_tax_documents_omits_empty_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: list[TaxDocumentRow] = [
        {
            "id": 4,
            "title": None,
            "law_name": "부가가치세법",
            "content": "  과세 대상  ",
            "source": None,
        }
    ]
    monkeypatch.setattr(
        "src.data.postgres_repository.load_tax_documents", lambda _settings: rows
    )

    assert prepare_tax_documents(Settings(_env_file=None)) == [
        {
            "tax_document_id": 4,
            "content": "법령명: 부가가치세법\n내용: 과세 대상",
            "metadata": {"law_name": "부가가치세법"},
        }
    ]
