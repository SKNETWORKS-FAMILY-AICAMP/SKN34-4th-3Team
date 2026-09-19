from typing import Any

from elasticsearch import Elasticsearch

from src.core.config import Settings
from src.data.contracts import VectorSearchResult


class ElasticsearchBM25Search:
    """Nori가 적용된 Elasticsearch 인덱스를 검색하는 BM25 검색기."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: Elasticsearch | None = None,
    ) -> None:
        """Elasticsearch 연결과 검색 alias를 준비한다.

        Args:
            settings: Elasticsearch URL, alias와 timeout 설정.
            client: 테스트 또는 기존 연결 재사용을 위한 선택적 client.
        """
        self._settings = settings
        self._client = client or Elasticsearch(
            settings.elasticsearch_url,
            request_timeout=settings.elasticsearch_request_timeout,
        )
        self._index = settings.elasticsearch_index_alias

    def ready(self) -> bool:
        """검색 alias가 존재하고 한 건 이상의 문서를 포함하는지 확인한다."""
        return bool(
            self._client.indices.exists_alias(name=self._index)
            and self._client.count(index=self._index)["count"] > 0
        )

    def search(
        self,
        query: str,
        *,
        policy_id: int | None = None,
        source_types: tuple[str, ...] | None = None,
        require_policy_id: bool = False,
        top_k: int = 5,
    ) -> list[VectorSearchResult]:
        """Nori 분석 필드에 multi-match BM25 검색을 수행한다.

        Args:
            query: 검색할 사용자 질문.
            policy_id: 특정 정책으로 제한할 선택적 ID.
            source_types: 허용할 원천 문서 유형.
            require_policy_id: True이면 정책과 연결된 문서만 검색.
            top_k: 반환할 최대 문서 수.

        Returns:
            기존 검색 평가 코드와 호환되는 점수·metadata 목록.
        """
        if not query.strip():
            raise ValueError("query must not be blank")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        filters: list[dict[str, Any]] = []
        if policy_id is not None:
            filters.append({"term": {"policy_id": policy_id}})
        if source_types is not None:
            filters.append({"terms": {"source_type": list(source_types)}})
        if require_policy_id:
            filters.append({"exists": {"field": "policy_id"}})

        response = self._client.search(
            index=self._index,
            size=top_k,
            query={
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["title^2", "content"],
                                "type": "best_fields",
                            }
                        }
                    ],
                    "filter": filters,
                }
            },
        )
        return [_hit_to_result(hit) for hit in response["hits"]["hits"]]


def _hit_to_result(hit: dict[str, Any]) -> VectorSearchResult:
    """Elasticsearch hit을 공통 VectorSearchResult 계약으로 변환한다."""
    source = hit["_source"]
    source_type = str(source["source_type"])
    source_id = int(source["source_id"])
    document_id = str(source.get("document_id") or hit["_id"])
    return {
        "chunk_id": document_id,
        "policy_id": (
            int(source["policy_id"]) if source.get("policy_id") is not None else None
        ),
        "title": str(source["title"]),
        "source": str(source["source"]),
        "page": 1,
        "content": str(source["content"]),
        "source_type": source_type,
        "source_id": source_id,
        "score": float(hit["_score"] or 0.0),
    }
