from pathlib import Path

import pytest

from src.data.contracts import DocumentCatalogEntry
from src.features.document_processing import (
    PdfDocumentNotFoundError,
    PdfTextNotFoundError,
    load_pdf_pages,
)


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
