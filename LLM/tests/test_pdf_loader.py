from pathlib import Path

import pytest

from src.data.contracts import DocumentCatalogEntry
from src.data.document_catalog import SOURCE_PDF_DIR, get_document_catalog
from src.features.document_processing import (
    PdfDocumentNotFoundError,
    PdfTextNotFoundError,
    load_pdf_pages,
)


def test_catalog_discovers_all_pdfs_in_rag_data() -> None:
    catalog = get_document_catalog()

    assert SOURCE_PDF_DIR.name == "RAG_data"
    assert len(catalog) == len(list(SOURCE_PDF_DIR.glob("*.pdf"))) == 20
    assert catalog[0] == {
        "policy_id": 103,
        "title": "청년 직무경험 지원사업 공고",
        "file_name": "01_청년_직무경험_지원사업_공고.pdf",
    }
    assert catalog[-1] == {
        "policy_id": 120,
        "title": "청년 전월세보증금 이자지원",
        "file_name": "20_청년_전월세보증금_이자지원_실제공고문형.pdf",
    }


def test_catalog_pdf_is_loaded_read_only_with_page_metadata() -> None:
    entry = get_document_catalog()[0]
    pdf_path = SOURCE_PDF_DIR / entry["file_name"]
    before = pdf_path.read_bytes()

    pages = load_pdf_pages(entry)

    assert pages
    assert pages[0].page_content.strip()
    assert pages[0].metadata == {
        "policy_id": entry["policy_id"],
        "title": entry["title"],
        "source": entry["file_name"],
        "page": 1,
    }
    assert pdf_path.read_bytes() == before


def test_missing_pdf_raises_clear_error(tmp_path: Path) -> None:
    entry: DocumentCatalogEntry = {
        "policy_id": 999,
        "title": "없는 테스트 문서",
        "file_name": "missing.pdf",
    }

    with pytest.raises(PdfDocumentNotFoundError, match="PDF not found"):
        load_pdf_pages(entry, source_dir=tmp_path)


def test_pdf_without_extractable_text_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class EmptyPage:
        @staticmethod
        def extract_text() -> None:
            return None

    class EmptyReader:
        def __init__(self, _stream: object) -> None:
            self.pages = [EmptyPage()]

    entry: DocumentCatalogEntry = {
        "policy_id": 999,
        "title": "빈 테스트 문서",
        "file_name": "empty.pdf",
    }
    (tmp_path / entry["file_name"]).touch()
    monkeypatch.setattr("src.features.document_processing.PdfReader", EmptyReader)

    with pytest.raises(PdfTextNotFoundError, match="No extractable text"):
        load_pdf_pages(entry, source_dir=tmp_path)


def test_empty_page_is_skipped_without_changing_following_page_number(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakePage:
        def __init__(self, content: str | None) -> None:
            self.content = content

        def extract_text(self) -> str | None:
            return self.content

    class MixedReader:
        def __init__(self, _stream: object) -> None:
            self.pages = [FakePage(None), FakePage("두 번째 페이지 본문")]

    entry: DocumentCatalogEntry = {
        "policy_id": 999,
        "title": "혼합 테스트 문서",
        "file_name": "mixed.pdf",
    }
    (tmp_path / entry["file_name"]).touch()
    monkeypatch.setattr("src.features.document_processing.PdfReader", MixedReader)

    pages = load_pdf_pages(entry, source_dir=tmp_path)

    assert len(pages) == 1
    assert pages[0].metadata["page"] == 2
