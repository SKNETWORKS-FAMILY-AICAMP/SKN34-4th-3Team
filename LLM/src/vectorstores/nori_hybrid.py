"""PostgreSQL Dense + Elasticsearch Nori retrieval for the live graph."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Literal

from elasticsearch import ApiError, TransportError

from src.data.contracts import VectorSearchResult
from src.vectorstores.elasticsearch import ElasticsearchBM25Search
from src.vectorstores.postgres import PostgresVectorSearch

SourceUnit = Literal["policy", "tax"]
logger = logging.getLogger(__name__)


def source_key(document: VectorSearchResult, unit: SourceUnit) -> tuple[str, int]:
    if unit == "policy":
        value = document.get("policy_id")
        if value is None:
            raise ValueError("policy retrieval result has no policy_id")
        return "policy", int(value)
    source_type, source_id = document.get("source_type"), document.get("source_id")
    if source_type is None or source_id is None:
        raise ValueError("tax retrieval result has no source type or ID")
    return str(source_type), int(source_id)


def source_level_rrf(
    rankings: list[list[VectorSearchResult]], *, unit: SourceUnit, rrf_k: int, top_k: int,
) -> list[VectorSearchResult]:
    """RRF once per source in each ranking, never once per chunk."""
    if rrf_k < 1 or top_k < 1:
        raise ValueError("rrf_k and top_k must be positive")
    scores: dict[tuple[str, int], float] = {}
    representative: dict[tuple[str, int], VectorSearchResult] = {}
    for ranking in rankings:
        seen: set[tuple[str, int]] = set()
        for document in ranking:
            key = source_key(document, unit)
            if key in seen:
                continue
            seen.add(key)
            representative.setdefault(key, document)
            scores[key] = scores.get(key, 0.0) + 1 / (rrf_k + len(seen))
    if not rankings:
        return []
    maximum = len(rankings) / (rrf_k + 1)
    keys = sorted(scores, key=lambda key: -scores[key])[:top_k]
    return [{**representative[key], "score": scores[key] / maximum} for key in keys]


def merge_unique_sources(
    existing: list[VectorSearchResult], new: list[VectorSearchResult], *, unit: SourceUnit,
) -> list[VectorSearchResult]:
    merged = list(existing)
    seen = {source_key(document, unit) for document in existing}
    for document in new:
        key = source_key(document, unit)
        if key not in seen:
            seen.add(key)
            merged.append(document)
    return merged


class NoriHybridSearch:
    """Search unique sources with each backend before source-level RRF."""

    def __init__(
        self,
        *,
        dense_search: PostgresVectorSearch,
        bm25_search: ElasticsearchBM25Search,
        retrieval_pool_k: int = 40,
        rerank_candidate_k: int = 20,
        rrf_k: int = 60,
        exact_legal_search: Callable[..., list[VectorSearchResult]] | None = None,
        bm25_enabled: Callable[[], bool] | None = None,
    ) -> None:
        if rerank_candidate_k < 1 or retrieval_pool_k < rerank_candidate_k or rrf_k < 1:
            raise ValueError("require retrieval_pool_k >= rerank_candidate_k >= 1 and rrf_k >= 1")
        self.dense_search = dense_search
        self.bm25_search = bm25_search
        self.retrieval_pool_k = retrieval_pool_k
        self.rerank_candidate_k = rerank_candidate_k
        self.rrf_k = rrf_k
        self._exact_legal_search = exact_legal_search
        self._bm25_enabled = bm25_enabled or (lambda: True)

    def search_stages(
        self,
        query: str,
        *,
        policy_id: int | None = None,
        source_types: tuple[str, ...] | None = None,
        require_policy_id: bool = False,
        top_k: int = 20,
    ) -> tuple[list[VectorSearchResult], list[VectorSearchResult], list[VectorSearchResult]]:
        if top_k < 1 or top_k > self.rerank_candidate_k:
            raise ValueError("top_k exceeds the fixed rerank candidate budget")
        unit: SourceUnit = "tax" if source_types == ("tax_document",) else "policy"
        if unit == "tax" and policy_id is not None:
            raise ValueError("tax retrieval cannot filter by policy_id")
        if unit == "policy" and not require_policy_id:
            raise ValueError("policy retrieval requires a policy_id-bearing result")
        options = {
            "policy_id": policy_id,
            "source_types": source_types,
            "require_policy_id": require_policy_id,
            "top_k": self.retrieval_pool_k,
            "unique_policy_ids": unit == "policy",
            "unique_source_ids": unit == "tax",
        }
        dense = self.dense_search.search(query, **options)
        if not self._bm25_enabled():
            logger.warning("Elasticsearch index is out of sync; using PostgreSQL dense results")
            bm25 = []
        else:
            try:
                bm25 = self.bm25_search.search(query, **options)
            except (ApiError, TransportError):
                logger.exception("Elasticsearch BM25 search failed; using PostgreSQL dense results")
                bm25 = []
        if len(dense) > self.retrieval_pool_k or len(bm25) > self.retrieval_pool_k:
            raise ValueError("backend exceeded retrieval pool")
        for ranking in (dense, bm25):
            keys = [source_key(document, unit) for document in ranking]
            if len(keys) != len(set(keys)):
                raise ValueError("backend returned duplicate sources before RRF")
        rankings = [dense, bm25] if bm25 else [dense]
        fused = source_level_rrf(rankings, unit=unit, rrf_k=self.rrf_k, top_k=top_k)
        return dense, bm25, fused

    def search(
        self, query: str, *, policy_id: int | None = None,
        source_types: tuple[str, ...] | None = None, require_policy_id: bool = False,
        top_k: int = 20,
    ) -> list[VectorSearchResult]:
        return self.search_stages(
            query, policy_id=policy_id, source_types=source_types,
            require_policy_id=require_policy_id, top_k=top_k,
        )[2]

    def search_legal_reference(
        self, law_name: str, article: str, *, top_k: int = 5,
    ) -> list[VectorSearchResult]:
        # Preserve the production graph's exact-reference path. This is not a
        # BM25 fallback: normal lexical retrieval always uses Elasticsearch.
        if self._exact_legal_search is not None:
            return self._exact_legal_search(law_name, article, top_k=top_k)
        pattern = re.compile(rf"^{re.escape(law_name)}\s+제\s*{re.escape(article)}조(?!\d)")
        results: list[VectorSearchResult] = []
        seen: set[tuple[str, int]] = set()
        for chunk in self.dense_search.get_chunks():
            if chunk.get("source_type") != "tax_document" or not pattern.match(chunk["title"]):
                continue
            key = ("tax_document", int(chunk["source_id"]))
            if key in seen:
                continue
            seen.add(key)
            results.append({**chunk, "score": 1.0})
            if len(results) >= top_k:
                break
        return results
