from src.core.config import Settings
from src.data.contracts import RagSourceDocument
from src.features.indexing import prepare_database_chunks


def test_database_documents_are_chunked_with_source_metadata() -> None:
    source_documents: list[RagSourceDocument] = [
        {
            "source_type": "announcement",
            "source_id": 7,
            "policy_id": 101,
            "title": "청년 창업 공고",
            "source": "https://example.com/policy/101",
            "content": "지원 대상과 지원 내용을 확인합니다. " * 10,
        }
    ]
    settings = Settings(
        _env_file=None,
        chunk_size=80,
        chunk_overlap=10,
    )

    chunks = prepare_database_chunks(source_documents, settings=settings)

    assert len(chunks) > 1
    assert chunks[0]["chunk_id"] == "announcement-7-chunk-1"
    assert chunks[0]["policy_id"] == 101
    assert chunks[0]["source_type"] == "announcement"
    assert chunks[0]["source_id"] == 7
    assert all(len(chunk["content"]) <= 80 for chunk in chunks)
