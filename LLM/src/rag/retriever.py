from langsmith import traceable

from src.data.contracts import VectorSearchResult
from src.rag.guardrails import keep_grounded_results
from src.vectorstores.base import VectorSearch


@traceable(name="retrieve_documents", run_type="retriever")
def retrieve_relevant_chunks(
    vector_search: VectorSearch,
    question: str,
    *,
    policy_id: int | None,
    top_k: int,
    min_score: float,
) -> list[VectorSearchResult]:
    """질문과 관련된 Chunk를 검색하고 근거 기준을 통과한 결과를 반환한다.

    Args:
        vector_search: In-memory 또는 향후 pgvector 검색 구현체.
        question: Vector Search에 전달할 사용자 질문 또는 개인화 Query.
        policy_id: 특정 정책으로 검색을 제한할 ID. None이면 전체 정책 검색.
        top_k: 관련성 순서대로 요청할 최대 Chunk 개수.
        min_score: 답변 근거로 유지할 최소 유사도 점수.

    Returns:
        정책 필터와 최소 유사도 점수를 통과한 검색 결과 목록.
    """
    retrieved_chunks = vector_search.search(
        question,
        policy_id=policy_id,
        top_k=top_k,
    )
    return keep_grounded_results(
        retrieved_chunks,
        policy_id=policy_id,
        min_score=min_score,
    )
