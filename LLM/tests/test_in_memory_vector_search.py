import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from src.data import get_rag_chunks
from src.features import build_mock_vector_index
from src.vectorstores import InMemoryVectorSearch


def test_index_embeds_and_returns_the_identical_chunk_first() -> None:
    chunks = get_rag_chunks()
    index = build_mock_vector_index(DeterministicFakeEmbedding(size=32))

    results = index.search(chunks[0]["content"], top_k=2)

    assert results[0]["chunk_id"] == chunks[0]["chunk_id"]
    assert results[0]["score"] == pytest.approx(1.0)
    assert results[0]["score"] >= results[1]["score"]


def test_search_filters_chunks_by_policy_id() -> None:
    index = build_mock_vector_index(DeterministicFakeEmbedding(size=32))

    results = index.search("지원 대상과 신청 조건", policy_id=101, top_k=5)

    assert len(results) == 2
    assert all(result["policy_id"] == 101 for result in results)


def test_search_returns_empty_list_for_unknown_policy() -> None:
    index = build_mock_vector_index(DeterministicFakeEmbedding(size=32))

    assert index.search("지원 조건", policy_id=999) == []


def test_source_type_filter_selects_tax_before_dense_top_k() -> None:
    policy = {
        "chunk_id": "policy-1", "policy_id": 1, "title": "정책",
        "source": "db://policy/1", "page": 1, "content": "같은 질문",
        "source_type": "policy", "source_id": 1,
    }
    tax = {
        **policy, "chunk_id": "tax-1", "policy_id": None, "title": "세법",
        "source": "db://tax_document/1", "source_type": "tax_document",
    }
    index = InMemoryVectorSearch(DeterministicFakeEmbedding(size=16))
    index.add_chunks([policy, tax])

    result = index.search("같은 질문", source_types=("tax_document",), top_k=1)

    assert [doc["chunk_id"] for doc in result] == ["tax-1"]
    assert result[0]["policy_id"] is None
    assert result[0]["source_type"] == "tax_document"


def test_policy_id_requirement_excludes_unlinked_announcement() -> None:
    unlinked = {
        "chunk_id": "announcement-1", "policy_id": None, "title": "공고",
        "source": "db://announcement/1", "page": 1, "content": "창업 공고",
        "source_type": "announcement", "source_id": 1,
    }
    linked = {**unlinked, "chunk_id": "announcement-2", "policy_id": 2, "source_id": 2}
    index = InMemoryVectorSearch(DeterministicFakeEmbedding(size=16))
    index.add_chunks([unlinked, linked])

    result = index.search(
        "창업 공고", source_types=("policy", "announcement"),
        require_policy_id=True, top_k=2,
    )

    assert [doc["chunk_id"] for doc in result] == ["announcement-2"]


def test_add_chunks_does_not_mutate_mock_data() -> None:
    chunks = get_rag_chunks(policy_id=101)
    original_chunks = get_rag_chunks(policy_id=101)
    index = InMemoryVectorSearch(DeterministicFakeEmbedding(size=16))

    ids = index.add_chunks(chunks)

    assert ids == [chunk["chunk_id"] for chunk in original_chunks]
    assert chunks == original_chunks


def test_get_chunks_returns_copy_with_original_metadata() -> None:
    original_chunks = get_rag_chunks()
    index = build_mock_vector_index(DeterministicFakeEmbedding(size=16))

    stored_chunks = index.get_chunks()
    stored_chunks[0]["content"] = "변경된 테스트 본문"

    assert index.get_chunks() == original_chunks


@pytest.mark.parametrize("query", ["", "   "])
def test_blank_query_is_rejected(query: str) -> None:
    index = build_mock_vector_index(DeterministicFakeEmbedding(size=16))

    with pytest.raises(ValueError, match="query must not be blank"):
        index.search(query)


def test_invalid_top_k_is_rejected() -> None:
    index = build_mock_vector_index(DeterministicFakeEmbedding(size=16))

    with pytest.raises(ValueError, match="top_k must be at least 1"):
        index.search("지원 조건", top_k=0)
