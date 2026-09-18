from src.data import get_rag_chunks
from src.rag.context_builder import (
    build_prompt_context,
    select_chunks_by_source_numbers,
)


def search_result(chunk_index: int, score: float = 0.9) -> dict:
    """Mock Chunk에 검색 점수를 추가한다."""
    retrieved_chunk = get_rag_chunks()[chunk_index].copy()
    retrieved_chunk["score"] = score
    return retrieved_chunk


def test_context_removes_duplicates_and_limits_chunks_per_policy() -> None:
    policy_101_first = search_result(0)
    policy_101_second = search_result(1)
    policy_102_first = search_result(2)

    prompt_context = build_prompt_context(
        [policy_101_first, policy_101_first, policy_101_second, policy_102_first],
        max_context_characters=10000,
        max_chunks_per_policy=1,
    )

    assert [
        chunk["chunk_id"] for chunk in prompt_context.selected_chunks
    ] == [policy_101_first["chunk_id"], policy_102_first["chunk_id"]]
    assert prompt_context.excluded_chunk_count == 2


def test_context_keeps_first_complete_chunk_when_limit_is_too_small() -> None:
    first_chunk = search_result(0)
    second_chunk = search_result(2)

    prompt_context = build_prompt_context(
        [first_chunk, second_chunk],
        max_context_characters=1,
        max_chunks_per_policy=2,
    )

    assert prompt_context.selected_chunks == (first_chunk,)
    assert first_chunk["content"] in prompt_context.context_text
    assert second_chunk["content"] not in prompt_context.context_text


def test_context_uses_document_boundaries_and_stable_source_numbers() -> None:
    prompt_context = build_prompt_context(
        [search_result(0), search_result(2)],
        max_context_characters=10000,
        max_chunks_per_policy=2,
    )

    assert prompt_context.context_text.startswith("<retrieved_documents>")
    assert prompt_context.context_text.endswith("</retrieved_documents>")
    assert '<document source_number="1">' in prompt_context.context_text
    assert "정책 ID: 101" in prompt_context.context_text
    assert "[출처 2]" in prompt_context.context_text
    assert select_chunks_by_source_numbers(prompt_context, (2, 1)) == (
        prompt_context.selected_chunks[1],
        prompt_context.selected_chunks[0],
    )
