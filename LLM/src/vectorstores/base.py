from typing import Protocol

from src.data.contracts import RagChunk, VectorSearchResult


class VectorSearch(Protocol):
    """In-memory 테스트 저장소와 향후 pgvector가 공유할 최소 검색 계약."""

    def add_chunks(self, chunks: list[RagChunk]) -> list[str]:
        """RAG Chunk를 임베딩·저장하고 저장된 Chunk ID를 반환한다."""
        ...

    def search(
        self,
        query: str,
        *,
        policy_id: int | None = None,
        source_types: tuple[str, ...] | None = None,
        require_policy_id: bool = False,
        top_k: int = 5,
    ) -> list[VectorSearchResult]:
        """질문과 유사한 Chunk를 정책 필터와 순위 제한에 따라 반환한다.

        Args:
            query: 유사도 검색에 사용할 사용자 Query.
            policy_id: 검색 범위를 제한할 정책 ID. None이면 전체 정책을 검색한다.
            source_types: 후보를 뽑기 전에 적용할 원천 문서 유형.
            require_policy_id: True이면 정책 ID가 연결된 Chunk만 검색한다.
            top_k: 관련성 순서대로 반환할 최대 Chunk 개수.

        Returns:
            Chunk 본문, 출처 metadata와 유사도 점수를 담은 검색 결과 목록.
        """
        ...

    def get_chunks(self) -> list[RagChunk]:
        """현재 검색기에 적재된 모든 Chunk의 복사본을 반환한다."""
        ...
