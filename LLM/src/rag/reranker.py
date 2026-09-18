"""RRF 후보를 공통 검색 schema를 유지한 채 Cohere로 재정렬한다."""

import cohere
from functools import lru_cache

from src.core.config import Settings
from src.data.contracts import VectorSearchResult


class CohereRerankError(RuntimeError):
    """Cohere 설정 또는 API 응답 때문에 재정렬할 수 없을 때 발생한다."""


@lru_cache(maxsize=4)
def _cohere_client(api_key: str) -> cohere.ClientV2:
    return cohere.ClientV2(api_key=api_key)


def rerank_documents(
    query: str,
    documents: list[VectorSearchResult],
    *,
    top_n: int,
    settings: Settings,
) -> list[VectorSearchResult]:
    """Cohere relevance score 순서로 RRF 후보를 재정렬한다.

    Args:
        query: 사용자 질문 또는 개인화 검색 Query.
        documents: Dense + BM25 + RRF가 반환한 후보 문서.
        top_n: 최종 반환할 최대 문서 수.
        settings: Cohere 인증정보와 모델 설정.

    Returns:
        원본 metadata와 Cohere score를 보존한 공통 검색 결과.

    Raises:
        CohereRerankError: 설정이 없거나 Cohere 요청·응답이 유효하지 않을 때.
    """
    if not documents:
        return []
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    if not settings.cohere_configured or settings.cohere_api_key is None:
        raise CohereRerankError(
            "Cohere rerank is not configured. Set COHERE_API_KEY."
        )

    try:
        response = _cohere_client(settings.cohere_api_key.get_secret_value()).rerank(
            model=settings.cohere_rerank_model,
            query=query,
            documents=[document["content"] for document in documents],
            top_n=min(top_n, len(documents)),
        )
        reranked_documents = [
            {
                **documents[result.index],
                "score": float(result.relevance_score),
            }
            for result in response.results
            if 0 <= result.index < len(documents)
        ]
    except Exception as exc:
        raise CohereRerankError("Cohere rerank request failed") from exc

    if not reranked_documents:
        raise CohereRerankError("Cohere rerank returned no valid results")
    return reranked_documents
