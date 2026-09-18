import pytest
from langchain_core.documents import Document

from src.features.document_processing import split_pdf_pages


def make_page(content: str = "첫 번째 문장입니다. 두 번째 문장입니다.") -> Document:
    return Document(
        page_content=content,
        metadata={
            "policy_id": 101,
            "title": "테스트 정책",
            "source": "test.pdf",
            "page": 2,
        },
    )


def test_chunks_preserve_metadata_and_have_deterministic_ids() -> None:
    pages = [make_page("가" * 70)]

    first = split_pdf_pages(pages, chunk_size=30, chunk_overlap=5)
    second = split_pdf_pages(pages, chunk_size=30, chunk_overlap=5)

    assert first == second
    assert len(first) > 1
    assert first[0]["chunk_id"] == "policy-101-page-2-chunk-1"
    assert first[0]["policy_id"] == 101
    assert first[0]["title"] == "테스트 정책"
    assert first[0]["source"] == "test.pdf"
    assert first[0]["page"] == 2
    assert all(chunk["content"] for chunk in first)
    assert all(len(chunk["content"]) <= 30 for chunk in first)


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap", "message"),
    [
        (0, 0, "chunk_size must be at least 1"),
        (10, -1, "chunk_overlap must not be negative"),
        (10, 10, "chunk_overlap must be smaller than chunk_size"),
    ],
)
def test_invalid_chunk_settings_are_rejected(
    chunk_size: int,
    chunk_overlap: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        split_pdf_pages(
            [make_page()],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )


def test_missing_page_metadata_is_rejected() -> None:
    with pytest.raises(ValueError, match="Missing page metadata"):
        split_pdf_pages(
            [Document(page_content="본문", metadata={})],
            chunk_size=100,
            chunk_overlap=10,
        )
