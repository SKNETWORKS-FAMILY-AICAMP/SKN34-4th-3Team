from langchain_core.embeddings import DeterministicFakeEmbedding

from src.core.config import Settings
from src.data import get_document_catalog
import pytest

from src.features import (
    build_document_vector_index,
    build_vector_index,
    prepare_document_chunks,
)


def test_all_catalog_documents_are_chunked_with_their_policy_metadata() -> None:
    settings = Settings(
        _env_file=None,
        chunk_size=500,
        chunk_overlap=50,
    )

    chunks = prepare_document_chunks(settings=settings)

    catalog = get_document_catalog()
    assert chunks
    assert {chunk["policy_id"] for chunk in chunks} == {
        entry["policy_id"] for entry in catalog
    }
    assert all(chunk["source"].endswith(".pdf") for chunk in chunks)
    assert all(chunk["page"] >= 1 for chunk in chunks)


def test_real_pdf_chunks_can_be_searched_without_openai_api() -> None:
    settings = Settings(
        _env_file=None,
        chunk_size=500,
        chunk_overlap=50,
    )

    index = build_document_vector_index(
        DeterministicFakeEmbedding(size=32),
        settings=settings,
    )
    results = index.search("지원 대상", policy_id=101, top_k=3)

    assert results
    assert len(results) <= 3
    assert all(result["policy_id"] == 101 for result in results)
    assert all(result["source"].endswith(".pdf") for result in results)
    assert all(result["content"] for result in results)
    assert all(isinstance(result["score"], float) for result in results)


def test_empty_chunk_collection_is_rejected_before_embedding() -> None:
    with pytest.raises(ValueError, match="At least one RAG chunk"):
        build_vector_index([], embedding=DeterministicFakeEmbedding(size=16))
