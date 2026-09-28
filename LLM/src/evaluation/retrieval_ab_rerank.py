from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from time import perf_counter, sleep
from typing import Any, Callable

from src.core.config import Settings, get_settings
from src.evaluation.metrics import retrieval_metrics
from src.evaluation.retrieval_ab import (
    RetrievalCase,
    load_holdout250_policy_cases,
    load_retrieval_cases,
    policy_level_rrf,
)
from src.models import get_embedding_model
from src.rag.reranker import CohereRerankError, rerank_documents
from src.vectorstores.elasticsearch import ElasticsearchBM25Search
from src.vectorstores.hybrid import BM25Search
from src.vectorstores.postgres import PostgresVectorSearch


DEFAULT_OUTPUT = Path(
    "evaluation/results/nori_v3_pool40_with_rerank.json"
)
DEFAULT_RETRIEVAL_POOL_K = 40
DEFAULT_RERANK_CANDIDATE_K = 20
DEFAULT_RERANK_MIN_INTERVAL_SECONDS = 6.1
MIN_RERANK_INTERVAL_SECONDS = 6.0


class RequestIntervalLimiter:
    """Cohere 요청 시작 사이에 지정한 최소 간격을 보장한다."""

    def __init__(
        self,
        minimum_interval_seconds: float,
        *,
        clock: Callable[[], float] = perf_counter,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds must not be negative")
        self._minimum_interval_seconds = minimum_interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_started: float | None = None

    def wait(self) -> float:
        now = self._clock()
        wait_seconds = 0.0
        if self._last_request_started is not None:
            elapsed = now - self._last_request_started
            wait_seconds = max(0.0, self._minimum_interval_seconds - elapsed)
            if wait_seconds:
                self._sleeper(wait_seconds)
        self._last_request_started = self._clock()
        return wait_seconds


def evaluate_with_rerank(
    cases: list[RetrievalCase],
    *,
    settings: Settings,
    top_k: int = 5,
    retrieval_pool_k: int = DEFAULT_RETRIEVAL_POOL_K,
    rerank_candidate_k: int = DEFAULT_RERANK_CANDIDATE_K,
    rerank_min_interval_seconds: float = DEFAULT_RERANK_MIN_INTERVAL_SECONDS,
    suite_name: str = "custom",
) -> dict[str, Any]:
    """두 Hybrid 검색의 고유 정책 후보를 Cohere로 재정렬해 비교한다."""
    if top_k < 1 or rerank_candidate_k < top_k:
        raise ValueError(
            "rerank_candidate_k must be greater than or equal to top_k"
        )
    if retrieval_pool_k < rerank_candidate_k:
        raise ValueError(
            "retrieval_pool_k must be greater than or equal to "
            "rerank_candidate_k"
        )
    if rerank_min_interval_seconds < MIN_RERANK_INTERVAL_SECONDS:
        raise ValueError(
            "rerank_min_interval_seconds must be at least 6.0 seconds"
        )
    if not settings.cohere_configured:
        raise ValueError("COHERE_API_KEY and COHERE_RERANK_MODEL are required")

    dense_search = PostgresVectorSearch(
        embedding=get_embedding_model(),
        settings=settings,
    )
    memory_bm25 = BM25Search(dense_search.get_chunks())
    elasticsearch_bm25 = ElasticsearchBM25Search(settings)
    if not elasticsearch_bm25.ready():
        raise RuntimeError(
            f"Elasticsearch alias is not ready: {settings.elasticsearch_index_alias}"
        )

    limiter = RequestIntervalLimiter(rerank_min_interval_seconds)
    rows: list[dict[str, Any]] = []
    rerank_call_count = 0
    throttle_wait_seconds = 0.0

    for position, case in enumerate(cases, start=1):
        question = case["question"]
        relevant = set(case["relevant_policy_ids"])

        dense_started = perf_counter()
        dense_results = dense_search.search(
            question,
            source_types=("policy", "announcement"),
            require_policy_id=True,
            unique_policy_ids=True,
            top_k=retrieval_pool_k,
        )
        dense_ms = (perf_counter() - dense_started) * 1000
        _require_unique_pool(
            case["case_id"], "dense", dense_results, retrieval_pool_k
        )

        fused_by_branch: dict[str, tuple[list[dict[str, Any]], float]] = {}
        for branch, lexical_search in (
            ("memory", memory_bm25),
            ("nori", elasticsearch_bm25),
        ):
            lexical_started = perf_counter()
            lexical_results = lexical_search.search(
                question,
                source_types=("policy", "announcement"),
                require_policy_id=True,
                unique_policy_ids=True,
                top_k=retrieval_pool_k,
            )
            lexical_ms = (perf_counter() - lexical_started) * 1000
            _require_unique_pool(
                case["case_id"], branch, lexical_results, retrieval_pool_k
            )
            fusion_started = perf_counter()
            fused = policy_level_rrf(
                dense_results,
                lexical_results,
                rrf_k=settings.hybrid_rrf_k,
                top_k=rerank_candidate_k,
            )
            fusion_ms = (perf_counter() - fusion_started) * 1000
            fused_by_branch[branch] = (
                fused,
                dense_ms + lexical_ms + fusion_ms,
            )

        row: dict[str, Any] = {
            "case_id": case["case_id"],
            "relevant_policy_ids": sorted(relevant),
        }
        for branch in ("memory", "nori"):
            fused, retrieval_ms = fused_by_branch[branch]
            candidate_ranking = _policy_ids(fused, rerank_candidate_k)
            if len(candidate_ranking) != rerank_candidate_k:
                raise RuntimeError(
                    f"{case['case_id']} {branch} produced "
                    f"{len(candidate_ranking)} unique policies, "
                    f"expected {rerank_candidate_k}"
                )
            throttle_wait_seconds += limiter.wait()
            rerank_call_count += 1
            rerank_started = perf_counter()
            try:
                reranked = rerank_documents(
                    question,
                    fused,
                    top_n=top_k,
                    settings=settings,
                )
            except CohereRerankError as exc:
                raise RuntimeError(
                    f"Rerank failed for {case['case_id']} ({branch})"
                ) from exc
            rerank_api_ms = (perf_counter() - rerank_started) * 1000
            row[branch] = {
                "hybrid": _ranking_result(
                    candidate_ranking[:top_k], relevant, top_k, retrieval_ms
                ),
                "candidate": _candidate_result(
                    candidate_ranking, relevant, rerank_candidate_k
                ),
                "rerank": _ranking_result(
                    _policy_ids(reranked, top_k),
                    relevant,
                    top_k,
                    rerank_api_ms,
                ),
            }
        rows.append(row)
        print(
            f"evaluated={position}/{len(cases)} "
            f"cohere_calls={rerank_call_count}",
            flush=True,
        )

    return {
        "suite": suite_name,
        "case_count": len(rows),
        "top_k": top_k,
        "retrieval_pool_k": retrieval_pool_k,
        "rerank_candidate_k": rerank_candidate_k,
        "candidate_unit": "unique_policy_id",
        "analyzer_version": "nori-v3-xsv-xsa",
        "multi_match_type": "cross_fields",
        "minimum_should_match": "25%",
        "rerank_used": True,
        "rerank_model": settings.cohere_rerank_model,
        "rerank_call_count": rerank_call_count,
        "rerank_min_interval_seconds": rerank_min_interval_seconds,
        "rerank_throttle_wait_seconds": throttle_wait_seconds,
        "memory_hybrid": _aggregate(rows, "memory", "hybrid"),
        "nori_hybrid": _aggregate(rows, "nori", "hybrid"),
        "memory_hybrid_candidate": _aggregate_candidate(rows, "memory"),
        "nori_hybrid_candidate": _aggregate_candidate(rows, "nori"),
        "memory_hybrid_rerank": _aggregate(rows, "memory", "rerank"),
        "nori_hybrid_rerank": _aggregate(rows, "nori", "rerank"),
        "rerank_hit_comparison": _hit_comparison(rows),
    }


def _require_unique_pool(
    case_id: str,
    branch: str,
    results: list[dict[str, Any]],
    expected_count: int,
) -> None:
    actual_count = len(_policy_ids(results, expected_count))
    if actual_count != expected_count:
        raise RuntimeError(
            f"{case_id} {branch} produced {actual_count} unique policies, "
            f"expected {expected_count}"
        )


def _policy_ids(results: list[dict[str, Any]], limit: int) -> list[int]:
    ranking: list[int] = []
    seen: set[int] = set()
    for result in results:
        value = result.get("policy_id")
        if value is None:
            continue
        policy_id = int(value)
        if policy_id in seen:
            continue
        seen.add(policy_id)
        ranking.append(policy_id)
        if len(ranking) >= limit:
            break
    return ranking


def _ranking_result(
    ranking: list[int], relevant: set[int], top_k: int, latency_ms: float
) -> dict[str, Any]:
    metrics = retrieval_metrics(ranking, relevant, top_k)
    return {
        "ranking": ranking,
        "precision_at_k": metrics.precision_at_k,
        "recall_at_k": metrics.recall_at_k,
        "mrr": metrics.reciprocal_rank,
        "map_at_k": metrics.average_precision,
        "hit_at_k": float(bool(set(ranking[:top_k]) & relevant)),
        "latency_ms": latency_ms,
    }


def _candidate_result(
    ranking: list[int], relevant: set[int], candidate_k: int
) -> dict[str, float]:
    hits = set(ranking[:candidate_k]) & relevant
    return {
        "recall_at_k": len(hits) / len(relevant) if relevant else 0.0,
        "hit_at_k": float(bool(hits)),
    }


def _aggregate(
    rows: list[dict[str, Any]], branch: str, stage: str
) -> dict[str, float]:
    values = [row[branch][stage] for row in rows]
    return {
        "precision_at_k": mean(value["precision_at_k"] for value in values),
        "recall_at_k": mean(value["recall_at_k"] for value in values),
        "mrr": mean(value["mrr"] for value in values),
        "map_at_k": mean(value["map_at_k"] for value in values),
        "hit_at_k": mean(value["hit_at_k"] for value in values),
        "average_latency_ms": mean(value["latency_ms"] for value in values),
    }


def _aggregate_candidate(
    rows: list[dict[str, Any]], branch: str
) -> dict[str, float]:
    values = [row[branch]["candidate"] for row in rows]
    return {
        "recall_at_k": mean(value["recall_at_k"] for value in values),
        "hit_at_k": mean(value["hit_at_k"] for value in values),
    }


def _hit_comparison(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"memory_only": 0, "nori_only": 0, "both_hit": 0, "both_miss": 0}
    for row in rows:
        memory_hit = bool(row["memory"]["rerank"]["hit_at_k"])
        nori_hit = bool(row["nori"]["rerank"]["hit_at_k"])
        if memory_hit and nori_hit:
            counts["both_hit"] += 1
        elif memory_hit:
            counts["memory_only"] += 1
        elif nori_hit:
            counts["nori_only"] += 1
        else:
            counts["both_miss"] += 1
    return counts


def render_markdown_report(report: dict[str, Any]) -> str:
    """문항별 결과와 실행 설명을 제외하고 비교 지표만 출력한다."""
    top_k = report["top_k"]
    candidate_k = report["rerank_candidate_k"]
    lines = [
        "# Nori XSV/XSA + MSM 25% 비교",
        "",
        "## Rerank 전 Hybrid",
        "",
        *_metric_table(
            report["memory_hybrid"],
            report["nori_hybrid"],
            top_k,
        ),
        "",
        f"## Hybrid 후보 Top-{candidate_k}",
        "",
        *_candidate_table(report, candidate_k),
        "",
        "## Cohere Rerank 후",
        "",
        *_metric_table(
            report["memory_hybrid_rerank"],
            report["nori_hybrid_rerank"],
            top_k,
        ),
        "",
    ]
    return "\n".join(lines)


def _metric_table(
    memory: dict[str, float],
    nori: dict[str, float],
    top_k: int,
) -> list[str]:
    rows = [
        "| 지표 | 기존 Hybrid | Nori Hybrid | 차이(Nori-기존) |",
        "|---|---:|---:|---:|",
    ]
    for label, key in (
        (f"Precision@{top_k}", "precision_at_k"),
        (f"Recall@{top_k}", "recall_at_k"),
        ("MRR", "mrr"),
        (f"MAP@{top_k}", "map_at_k"),
        (f"Hit@{top_k}", "hit_at_k"),
    ):
        difference = float(nori[key]) - float(memory[key])
        rows.append(
            f"| {label} | {float(memory[key]):.4f} | "
            f"{float(nori[key]):.4f} | {difference:+.4f} |"
        )
    return rows


def _candidate_table(report: dict[str, Any], candidate_k: int) -> list[str]:
    memory = report["memory_hybrid_candidate"]
    nori = report["nori_hybrid_candidate"]
    rows = [
        "| 지표 | 기존 Hybrid | Nori Hybrid | 차이(Nori-기존) |",
        "|---|---:|---:|---:|",
    ]
    for label, key in (
        (f"Recall@{candidate_k}", "recall_at_k"),
        (f"Hit@{candidate_k}", "hit_at_k"),
    ):
        difference = float(nori[key]) - float(memory[key])
        rows.append(
            f"| {label} | {float(memory[key]):.4f} | "
            f"{float(nori[key]):.4f} | {difference:+.4f} |"
        )
    return rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two unique-policy Hybrid retrievers with Cohere rerank."
    )
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--retrieval-pool-k", type=int, default=DEFAULT_RETRIEVAL_POOL_K
    )
    parser.add_argument(
        "--rerank-candidate-k",
        "--candidate-k",
        dest="rerank_candidate_k",
        type=int,
        default=DEFAULT_RERANK_CANDIDATE_K,
    )
    parser.add_argument(
        "--rerank-min-interval-seconds",
        type=float,
        default=DEFAULT_RERANK_MIN_INTERVAL_SECONDS,
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    if args.cases is None:
        cases = load_holdout250_policy_cases()
        suite_name = "holdout250-policy63-development-subset"
    else:
        cases = load_retrieval_cases(args.cases)
        suite_name = str(args.cases)

    report = evaluate_with_rerank(
        cases,
        settings=settings,
        top_k=args.top_k,
        retrieval_pool_k=args.retrieval_pool_k,
        rerank_candidate_k=args.rerank_candidate_k,
        rerank_min_interval_seconds=args.rerank_min_interval_seconds,
        suite_name=suite_name,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown_output = args.output.with_suffix(".md")
    markdown_output.write_text(render_markdown_report(report), encoding="utf-8")
    print(f"json_report={args.output}")
    print(f"markdown_report={markdown_output}")


if __name__ == "__main__":
    main()
