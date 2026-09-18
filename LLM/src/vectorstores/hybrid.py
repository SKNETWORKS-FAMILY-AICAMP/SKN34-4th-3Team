from collections import Counter
import logging
import math
import re

from src.data.contracts import RagChunk, VectorSearchResult
from src.vectorstores.base import VectorSearch


_TOKEN_PATTERN = re.compile(r"[0-9a-zA-Z가-힣]+")
logger = logging.getLogger(__name__)


def tokenize_for_bm25(text: str) -> list[str]:
    """한국어 조사와 복합어에 대응하도록 어절과 2-gram을 생성한다.

    Args:
        text: BM25 인덱싱 또는 검색에 사용할 문자열.

    Returns:
        영문 소문자화가 적용된 어절과 문자 2-gram 목록.
    """
    tokens: list[str] = []
    for word in _TOKEN_PATTERN.findall(text.casefold()):
        tokens.append(word)
        if len(word) >= 2:
            tokens.extend(
                f"#2:{word[index:index + 2]}"
                for index in range(len(word) - 1)
            )
    return tokens


class BM25Search:
    """별도 DB 없이 Dense와 동일한 Chunk를 검색하는 BM25 구현체."""

    def __init__(
        self,
        chunks: list[RagChunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """BM25 corpus와 파라미터를 초기화한다.

        Args:
            chunks: Dense 인덱스와 동일한 RAG Chunk 목록.
            k1: 단어 빈도 포화 정도를 조절하는 BM25 파라미터.
            b: 문서 길이 정규화 강도를 조절하는 BM25 파라미터.

        Raises:
            ValueError: k1이 양수가 아니거나 b가 0~1 범위가 아닐 때.
        """
        if k1 <= 0:
            raise ValueError("BM25 k1 must be greater than 0")
        if not 0 <= b <= 1:
            raise ValueError("BM25 b must be between 0 and 1")

        self._k1 = k1
        self._b = b
        self._chunks_by_id: dict[str, RagChunk] = {}
        self._term_frequencies: dict[str, Counter[str]] = {}
        self._document_lengths: dict[str, int] = {}
        self._inverse_document_frequencies: dict[str, float] = {}
        self._average_document_length = 0.0
        self.add_chunks(chunks)

    def add_chunks(self, chunks: list[RagChunk]) -> list[str]:
        """Chunk를 BM25 corpus에 추가하고 통계를 다시 계산한다.

        Args:
            chunks: 본문과 메타데이터가 있는 RAG Chunk 목록.

        Returns:
            추가된 Chunk ID 목록.
        """
        for chunk in chunks:
            self._chunks_by_id[chunk["chunk_id"]] = dict(chunk)
        self._rebuild_statistics()
        return [chunk["chunk_id"] for chunk in chunks]

    def search(
        self,
        query: str,
        *,
        policy_id: int | None = None,
        source_types: tuple[str, ...] | None = None,
        require_policy_id: bool = False,
        top_k: int = 5,
    ) -> list[VectorSearchResult]:
        """Query 단어와 Chunk 단어의 BM25 관련성을 계산한다.

        Args:
            query: 키워드 검색에 사용할 질문 또는 개인화 Query.
            policy_id: 검색 범위를 제한할 정책 ID. None이면 전체 검색.
            source_types: 후보를 뽑기 전에 적용할 원천 문서 유형.
            require_policy_id: True이면 정책 ID가 연결된 Chunk만 검색한다.
            top_k: BM25 점수 순으로 반환할 최대 Chunk 개수.

        Returns:
            기존 메타데이터와 BM25 점수를 담은 검색 결과.

        Raises:
            ValueError: Query가 비었거나 top_k가 1보다 작을 때.
        """
        if not query.strip():
            raise ValueError("query must not be blank")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        query_terms = set(tokenize_for_bm25(query))
        scored_chunks = [
            (self._score(chunk_id, query_terms), chunk)
            for chunk_id, chunk in self._chunks_by_id.items()
            if (policy_id is None or chunk["policy_id"] == policy_id)
            and (source_types is None or _source_type(chunk) in source_types)
            and (not require_policy_id or chunk["policy_id"] is not None)
        ]
        ranked_chunks = sorted(
            (
                (score, chunk)
                for score, chunk in scored_chunks
                if score > 0
            ),
            key=lambda item: item[0],
            reverse=True,
        )[:top_k]
        return [
            _to_search_result(chunk, score)
            for score, chunk in ranked_chunks
        ]

    def get_chunks(self) -> list[RagChunk]:
        """BM25 corpus에 저장된 Chunk 복사본을 반환한다."""
        return [dict(chunk) for chunk in self._chunks_by_id.values()]

    def _rebuild_statistics(self) -> None:
        """현재 corpus의 단어 빈도, 문서 길이와 IDF를 갱신한다."""
        document_frequencies: Counter[str] = Counter()
        self._term_frequencies.clear()
        self._document_lengths.clear()

        for chunk_id, chunk in self._chunks_by_id.items():
            term_frequencies = Counter(tokenize_for_bm25(chunk["content"]))
            self._term_frequencies[chunk_id] = term_frequencies
            self._document_lengths[chunk_id] = sum(term_frequencies.values())
            document_frequencies.update(term_frequencies.keys())

        document_count = len(self._chunks_by_id)
        total_terms = sum(self._document_lengths.values())
        self._average_document_length = (
            total_terms / document_count if document_count else 0.0
        )
        self._inverse_document_frequencies = {
            term: math.log(
                1 + (document_count - frequency + 0.5) / (frequency + 0.5)
            )
            for term, frequency in document_frequencies.items()
        }

    def _score(self, chunk_id: str, query_terms: set[str]) -> float:
        """하나의 Chunk에 대한 BM25 점수를 계산한다."""
        if not self._average_document_length:
            return 0.0

        term_frequencies = self._term_frequencies[chunk_id]
        document_length = self._document_lengths[chunk_id]
        length_normalization = self._k1 * (
            1 - self._b
            + self._b * document_length / self._average_document_length
        )
        return sum(
            self._inverse_document_frequencies.get(term, 0.0)
            * frequency
            * (self._k1 + 1)
            / (frequency + length_normalization)
            for term in query_terms
            if (frequency := term_frequencies.get(term, 0))
        )


def reciprocal_rank_fusion(
    ranked_result_lists: list[list[VectorSearchResult]],
    *,
    rrf_k: int,
    top_k: int,
) -> list[VectorSearchResult]:
    """Dense와 BM25 순위를 Chunk ID 기준 RRF 점수로 결합한다.

    Args:
        ranked_result_lists: 검색 방식별로 순위가 정렬된 결과 목록.
        rrf_k: 상위 순위 간 점수 격차를 완화하는 RRF 상수.
        top_k: 결합 점수 순으로 반환할 최대 Chunk 개수.

    Returns:
        중복 Chunk의 RRF 점수가 누적된 기존 schema 호환 결과.

    Raises:
        ValueError: rrf_k 또는 top_k가 1보다 작을 때.

    Notes:
        최종 점수는 입력 검색기 모두에서 1위인 경우를 1로 정규화한다.
        원본 Dense와 BM25 점수는 결합에 사용하지 않는다.
    """
    if rrf_k < 1:
        raise ValueError("rrf_k must be at least 1")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if not ranked_result_lists:
        return []

    fused_scores: dict[str, float] = {}
    chunks_by_id: dict[str, VectorSearchResult] = {}
    first_seen_order: dict[str, int] = {}

    for ranked_results in ranked_result_lists:
        for rank, result in enumerate(ranked_results, start=1):
            chunk_id = result["chunk_id"]
            if chunk_id not in chunks_by_id:
                chunks_by_id[chunk_id] = dict(result)
                first_seen_order[chunk_id] = len(first_seen_order)
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (
                1 / (rrf_k + rank)
            )

    maximum_score = len(ranked_result_lists) / (rrf_k + 1)
    ranked_chunk_ids = sorted(
        fused_scores,
        key=lambda chunk_id: (
            -fused_scores[chunk_id],
            first_seen_order[chunk_id],
        ),
    )[:top_k]
    return [
        {
            **chunks_by_id[chunk_id],
            "score": fused_scores[chunk_id] / maximum_score,
        }
        for chunk_id in ranked_chunk_ids
    ]


class HybridSearch:
    """Dense와 BM25 후보를 RRF로 결합하는 검색 구현체."""

    def __init__(
        self,
        *,
        dense_search: VectorSearch,
        chunks: list[RagChunk],
        dense_candidate_k: int,
        bm25_candidate_k: int,
        rrf_k: int,
    ) -> None:
        """Hybrid 검색에 필요한 두 검색기와 RRF 설정을 준비한다.

        Args:
            dense_search: 기존 동작을 변경하지 않은 Dense 검색기.
            chunks: Dense에 적재된 것과 동일한 RAG Chunk 목록.
            dense_candidate_k: RRF에 전달할 Dense 최대 후보 수.
            bm25_candidate_k: RRF에 전달할 BM25 최대 후보 수.
            rrf_k: RRF 순위 점수 상수.

        Raises:
            ValueError: 후보 수나 rrf_k가 1보다 작을 때.
        """
        if dense_candidate_k < 1 or bm25_candidate_k < 1:
            raise ValueError("Hybrid candidate counts must be at least 1")
        if rrf_k < 1:
            raise ValueError("rrf_k must be at least 1")

        self._dense_search = dense_search
        self._bm25_search = BM25Search(chunks)
        self._dense_candidate_k = dense_candidate_k
        self._bm25_candidate_k = bm25_candidate_k
        self._rrf_k = rrf_k

    @property
    def dense_search(self) -> VectorSearch:
        """Expose the underlying index for tax-cache evidence restoration."""
        return self._dense_search

    def add_chunks(self, chunks: list[RagChunk]) -> list[str]:
        """Dense와 BM25 양쪽에 동일한 Chunk를 추가한다.

        Args:
            chunks: 양쪽 검색기에 추가할 RAG Chunk 목록.

        Returns:
            Dense 검색기가 반환한 Chunk ID 목록.
        """
        chunk_ids = self._dense_search.add_chunks(chunks)
        self._bm25_search.add_chunks(chunks)
        return chunk_ids

    def search(
        self,
        query: str,
        *,
        policy_id: int | None = None,
        source_types: tuple[str, ...] | None = None,
        require_policy_id: bool = False,
        top_k: int = 5,
    ) -> list[VectorSearchResult]:
        """Dense와 BM25 후보를 검색하고 RRF 상위 Chunk를 반환한다.

        Args:
            query: 두 검색기에 동일하게 전달할 Query.
            policy_id: 검색 범위를 제한할 정책 ID. None이면 전체 검색.
            source_types: Dense와 BM25 후보 검색에 공통 적용할 원천 유형.
            require_policy_id: True이면 정책 ID가 연결된 후보만 검색한다.
            top_k: RRF 결합 후 반환할 최대 Chunk 개수.

        Returns:
            RRF 점수와 기존 Chunk 메타데이터를 담은 결과.
        """
        _, _, fused_results = self.search_stages(
            query,
            policy_id=policy_id,
            source_types=source_types,
            require_policy_id=require_policy_id,
            top_k=top_k,
        )
        return fused_results

    def search_stages(
        self,
        query: str,
        *,
        policy_id: int | None = None,
        source_types: tuple[str, ...] | None = None,
        require_policy_id: bool = False,
        top_k: int = 5,
    ) -> tuple[
        list[VectorSearchResult],
        list[VectorSearchResult],
        list[VectorSearchResult],
    ]:
        """Dense, BM25와 RRF 결과를 단계별로 반환한다."""
        dense_results = self._dense_search.search(
            query,
            policy_id=policy_id,
            source_types=source_types,
            require_policy_id=require_policy_id,
            top_k=max(top_k, self._dense_candidate_k),
        )
        bm25_results = self._bm25_search.search(
            query,
            policy_id=policy_id,
            source_types=source_types,
            require_policy_id=require_policy_id,
            top_k=max(top_k, self._bm25_candidate_k),
        )
        fused_results = reciprocal_rank_fusion(
            [dense_results, bm25_results],
            rrf_k=self._rrf_k,
            top_k=top_k,
        )
        logger.info(
            "Hybrid retrieval counts: dense=%d bm25=%d rrf=%d",
            len(dense_results),
            len(bm25_results),
            len(fused_results),
        )
        return dense_results, bm25_results, fused_results

    def get_chunks(self) -> list[RagChunk]:
        """Dense와 BM25가 공유하는 Chunk 집합의 복사본을 반환한다."""
        return self._bm25_search.get_chunks()

    def search_legal_reference(
        self, law_name: str, article: str, *, top_k: int = 5
    ) -> list[VectorSearchResult]:
        """색인된 세법 Chunk에서 법령명과 조문 번호가 정확히 맞는 제목을 찾는다."""
        title_pattern = re.compile(
            rf"^{re.escape(law_name)}\s+제\s*{re.escape(article)}조(?!\d)"
        )
        matches: list[VectorSearchResult] = []
        for chunk in self._bm25_search.get_chunks():
            if _source_type(chunk) != "tax_document":
                continue
            if title_pattern.match(chunk["title"]):
                matches.append(_to_search_result(chunk, 1.0))
                if len(matches) >= top_k:
                    break
        return matches


def _to_search_result(chunk: RagChunk, score: float) -> VectorSearchResult:
    """RAG Chunk와 검색 점수를 공통 검색 결과로 변환한다."""
    return {
        "chunk_id": chunk["chunk_id"],
        "policy_id": chunk["policy_id"],
        "title": chunk["title"],
        "source": chunk["source"],
        "page": chunk["page"],
        "content": chunk["content"],
        "score": float(score),
        **({"source_type": chunk["source_type"]} if "source_type" in chunk else {}),
        **({"source_id": chunk["source_id"]} if "source_id" in chunk else {}),
        **({"id": chunk["id"]} if "id" in chunk else {}),
    }


def _source_type(chunk: RagChunk) -> str:
    """Legacy chunks without explicit metadata are distinguished by policy ID."""
    return chunk.get("source_type") or (
        "policy" if chunk["policy_id"] is not None else "tax_document"
    )
