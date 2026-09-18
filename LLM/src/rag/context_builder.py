from dataclasses import dataclass

from langsmith import traceable

from src.data.contracts import VectorSearchResult


@dataclass(frozen=True, slots=True)
class PromptContext:
    """Prompt에 실제 포함할 Chunk와 직렬화된 문맥 정보."""

    selected_chunks: tuple[VectorSearchResult, ...]
    context_text: str
    excluded_chunk_count: int


@traceable(name="build_prompt_context", run_type="chain")
def build_prompt_context(
    retrieved_chunks: list[VectorSearchResult],
    *,
    max_context_characters: int,
    max_chunks_per_policy: int,
) -> PromptContext:
    """중복·정책별 개수·전체 길이를 제한한 Prompt 문맥을 생성한다.

    Args:
        retrieved_chunks: Retriever가 관련성 순서로 반환한 Chunk 목록.
        max_context_characters: Prompt 문서 영역에 허용할 최대 문자 수.
        max_chunks_per_policy: 정책 하나에서 포함할 최대 Chunk 개수.

    Returns:
        선택된 Chunk, 문서 경계가 적용된 문자열과 제외된 Chunk 개수.

    Raises:
        ValueError: Context 또는 정책별 Chunk 제한이 1보다 작을 때.

    Notes:
        첫 번째 Chunk가 제한보다 길면 내용을 자르지 않고 완전한 Chunk 하나를
        유지한다. API 출처는 `selected_chunks`만 사용해야 한다.
    """
    if max_context_characters < 1:
        raise ValueError("max_context_characters must be at least 1")
    if max_chunks_per_policy < 1:
        raise ValueError("max_chunks_per_policy must be at least 1")

    unique_chunks = _deduplicate_chunks(retrieved_chunks)
    selected_chunks: list[VectorSearchResult] = []
    source_sections: list[str] = []
    policy_chunk_counts: dict[int, int] = {}

    for retrieved_chunk in unique_chunks:
        policy_id = retrieved_chunk["policy_id"]
        if policy_chunk_counts.get(policy_id, 0) >= max_chunks_per_policy:
            continue

        source_number = len(selected_chunks) + 1
        source_section = _format_source_section(retrieved_chunk, source_number)
        candidate_sections = [*source_sections, source_section]
        candidate_context = _wrap_document_context(candidate_sections)
        if selected_chunks and len(candidate_context) > max_context_characters:
            continue

        selected_chunks.append(retrieved_chunk)
        source_sections.append(source_section)
        policy_chunk_counts[policy_id] = policy_chunk_counts.get(policy_id, 0) + 1

    return PromptContext(
        selected_chunks=tuple(selected_chunks),
        context_text=_wrap_document_context(source_sections),
        excluded_chunk_count=len(retrieved_chunks) - len(selected_chunks),
    )


def select_chunks_by_source_numbers(
    prompt_context: PromptContext,
    source_numbers: tuple[int, ...],
) -> tuple[VectorSearchResult, ...]:
    """검증된 출처 번호에 해당하는 Prompt Chunk를 순서대로 반환한다.

    Args:
        prompt_context: 번호가 부여된 실제 Prompt 검색 문맥.
        source_numbers: 1부터 시작하는 검증된 출처 번호.

    Returns:
        출처 번호 순서에 대응하는 검색 Chunk tuple.
    """
    return tuple(
        prompt_context.selected_chunks[source_number - 1]
        for source_number in source_numbers
    )


def _deduplicate_chunks(
    retrieved_chunks: list[VectorSearchResult],
) -> list[VectorSearchResult]:
    """최초 검색 순서를 유지하면서 중복 chunk_id를 제거한다."""
    unique_chunks: list[VectorSearchResult] = []
    seen_chunk_ids: set[str] = set()
    for retrieved_chunk in retrieved_chunks:
        chunk_id = retrieved_chunk["chunk_id"]
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        unique_chunks.append(retrieved_chunk)
    return unique_chunks


def _format_source_section(
    retrieved_chunk: VectorSearchResult,
    source_number: int,
) -> str:
    """Chunk 하나를 번호가 지정된 XML 문서 영역으로 변환한다."""
    return "\n".join(
        [
            f'<document source_number="{source_number}">',
            f"[출처 {source_number}]",
            f"정책 ID: {retrieved_chunk['policy_id']}",
            f"문서명: {retrieved_chunk['title']}",
            f"파일: {retrieved_chunk['source']}",
            f"페이지: {retrieved_chunk['page']}",
            f"내용: {retrieved_chunk['content']}",
            "</document>",
        ]
    )


def _wrap_document_context(source_sections: list[str]) -> str:
    """출처별 문서 문자열을 명확한 검색 문서 경계로 감싼다."""
    joined_sections = "\n\n".join(source_sections)
    return f"<retrieved_documents>\n{joined_sections}\n</retrieved_documents>"
