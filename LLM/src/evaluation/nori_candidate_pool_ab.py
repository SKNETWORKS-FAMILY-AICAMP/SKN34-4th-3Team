from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from src.core.config import Settings, get_settings
from src.evaluation.metrics import retrieval_metrics
from src.evaluation.retrieval_ab import (
    RetrievalCase,
    _policy_ids,
    load_holdout250_policy_cases,
    load_retrieval_cases,
    policy_level_rrf,
)
from src.models import get_embedding_model
from src.vectorstores.elasticsearch import ElasticsearchBM25Search
from src.vectorstores.postgres import PostgresVectorSearch


DEFAULT_POOL_SIZES = (20, 30, 40, 50)
DEFAULT_RERANK_CANDIDATE_K = 20
DEFAULT_TOP_K = 5
DEFAULT_OUTPUT = Path("evaluation/results/nori_candidate_pool_ab.json")


class CachedQueryEmbeddings:
    """Reuse one query embedding across candidate-pool conditions."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self._query_cache: dict[str, list[float]] = {}

    def embed_query(self, text: str) -> list[float]:
        if text not in self._query_cache:
            self._query_cache[text] = self._delegate.embed_query(text)
        return self._query_cache[text]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._delegate.embed_documents(texts)


def evaluate_candidate_pools(
    cases: list[RetrievalCase],
    *,
    settings: Settings,
    retrieval_pool_sizes: tuple[int, ...] | list[int] = DEFAULT_POOL_SIZES,
    rerank_candidate_k: int = DEFAULT_RERANK_CANDIDATE_K,
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, Any]:
    """Measure only the effect of pre-RRF Dense/Nori candidate pool size."""
    pool_sizes = _validate_pool_sizes(
        retrieval_pool_sizes,
        rerank_candidate_k=rerank_candidate_k,
        top_k=top_k,
    )
    if not cases:
        raise ValueError("cases must not be empty")

    cached_embedding = CachedQueryEmbeddings(get_embedding_model())
    dense_search = PostgresVectorSearch(
        embedding=cached_embedding,  # type: ignore[arg-type]
        settings=settings,
    )
    nori_search = ElasticsearchBM25Search(settings)
    if not nori_search.ready():
        raise RuntimeError(
            f"Elasticsearch alias is not ready: {settings.elasticsearch_index_alias}"
        )

    samples: dict[int, list[dict[str, float]]] = {
        pool_k: [] for pool_k in pool_sizes
    }
    for position, case in enumerate(cases, start=1):
        question = case["question"]
        relevant = set(case["relevant_policy_ids"])

        embedding_started = perf_counter()
        cached_embedding.embed_query(question)
        embedding_ms = (perf_counter() - embedding_started) * 1000

        for pool_k in pool_sizes:
            dense_started = perf_counter()
            dense_results = dense_search.search(
                question,
                source_types=("policy", "announcement"),
                require_policy_id=True,
                unique_policy_ids=True,
                top_k=pool_k,
            )
            dense_ms = (perf_counter() - dense_started) * 1000

            nori_started = perf_counter()
            nori_results = nori_search.search(
                question,
                source_types=("policy", "announcement"),
                require_policy_id=True,
                unique_policy_ids=True,
                top_k=pool_k,
            )
            nori_ms = (perf_counter() - nori_started) * 1000
            _require_unique_pool(case["case_id"], "dense", dense_results, pool_k)
            _require_unique_pool(case["case_id"], "nori", nori_results, pool_k)

            fusion_started = perf_counter()
            fused = policy_level_rrf(
                dense_results,
                nori_results,
                rrf_k=settings.hybrid_rrf_k,
                top_k=rerank_candidate_k,
            )
            fusion_ms = (perf_counter() - fusion_started) * 1000
            ranking = _policy_ids(fused, rerank_candidate_k)
            if len(ranking) != rerank_candidate_k:
                raise RuntimeError(
                    f"{case['case_id']} RRF produced {len(ranking)} unique policies; "
                    f"expected {rerank_candidate_k}"
                )
            samples[pool_k].append(
                _case_metrics(
                    ranking,
                    relevant,
                    top_k=top_k,
                    candidate_k=rerank_candidate_k,
                    latency_ms=embedding_ms + dense_ms + nori_ms + fusion_ms,
                )
            )
        print(f"evaluated={position}/{len(cases)}", flush=True)

    results = [
        {
            "retrieval_pool_k": pool_k,
            **_aggregate(samples[pool_k]),
        }
        for pool_k in pool_sizes
    ]
    deltas = _calculate_deltas(results)
    saturation_pool_k = _find_exact_saturation(results)
    recommended_pool_k = saturation_pool_k or pool_sizes[-1]
    return {
        "suite": "holdout250-policy63-development-subset",
        "case_count": len(cases),
        "retrieval_pool_sizes": list(pool_sizes),
        "rerank_candidate_k": rerank_candidate_k,
        "top_k": top_k,
        "analyzer_version": "nori-v3-xsv-xsa",
        "multi_match_type": "cross_fields",
        "minimum_should_match": "25%",
        "rerank_used": False,
        "cohere_call_count": 0,
        "results": results,
        "deltas_from_previous_pool": deltas,
        "exact_saturation_pool_k": saturation_pool_k,
        "recommended_pool_k_for_cohere_validation": recommended_pool_k,
    }


def _validate_pool_sizes(
    pool_sizes: tuple[int, ...] | list[int],
    *,
    rerank_candidate_k: int,
    top_k: int,
) -> tuple[int, ...]:
    normalized = tuple(sorted(set(pool_sizes)))
    if not normalized:
        raise ValueError("retrieval_pool_sizes must not be empty")
    if top_k < 1 or rerank_candidate_k < top_k:
        raise ValueError("rerank_candidate_k must be greater than or equal to top_k")
    if any(pool_k < rerank_candidate_k for pool_k in normalized):
        raise ValueError(
            "every retrieval_pool_k must be greater than or equal to "
            "rerank_candidate_k"
        )
    return normalized


def _require_unique_pool(
    case_id: str,
    branch: str,
    results: list[dict[str, Any]],
    expected_count: int,
) -> None:
    actual_count = len(_policy_ids(results, expected_count))
    if actual_count != expected_count:
        raise RuntimeError(
            f"{case_id} {branch} produced {actual_count} unique policies; "
            f"expected {expected_count}"
        )


def _case_metrics(
    ranking: list[int],
    relevant: set[int],
    *,
    top_k: int,
    candidate_k: int,
    latency_ms: float,
) -> dict[str, float]:
    top_metrics = retrieval_metrics(ranking[:top_k], relevant, top_k)
    candidate_hits = set(ranking[:candidate_k]) & relevant
    return {
        "recall_at_20": len(candidate_hits) / len(relevant) if relevant else 0.0,
        "hit_at_20": float(bool(candidate_hits)),
        "recall_at_5": top_metrics.recall_at_k,
        "hit_at_5": float(bool(set(ranking[:top_k]) & relevant)),
        "mrr": top_metrics.reciprocal_rank,
        "map_at_5": top_metrics.average_precision,
        "average_retrieval_latency_ms": latency_ms,
    }


def _aggregate(samples: list[dict[str, float]]) -> dict[str, float]:
    return {
        key: mean(sample[key] for sample in samples)
        for key in (
            "recall_at_20",
            "hit_at_20",
            "recall_at_5",
            "hit_at_5",
            "mrr",
            "map_at_5",
            "average_retrieval_latency_ms",
        )
    }


def _calculate_deltas(results: list[dict[str, Any]]) -> list[dict[str, float | int]]:
    deltas: list[dict[str, float | int]] = []
    for previous, current in zip(results, results[1:], strict=False):
        deltas.append(
            {
                "from_pool_k": int(previous["retrieval_pool_k"]),
                "to_pool_k": int(current["retrieval_pool_k"]),
                **{
                    f"{key}_delta": float(current[key]) - float(previous[key])
                    for key in (
                        "recall_at_20",
                        "hit_at_20",
                        "recall_at_5",
                        "mrr",
                        "map_at_5",
                        "average_retrieval_latency_ms",
                    )
                },
            }
        )
    return deltas


def _find_exact_saturation(results: list[dict[str, Any]]) -> int | None:
    """Return the earliest pool after which Recall@20 and Hit@20 never improve."""
    for index, result in enumerate(results[:-1]):
        recall = float(result["recall_at_20"])
        hit = float(result["hit_at_20"])
        later = results[index + 1 :]
        if all(
            float(item["recall_at_20"]) == recall
            and float(item["hit_at_20"]) == hit
            for item in later
        ):
            return int(result["retrieval_pool_k"])
    return None


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Nori Hybrid Candidate Pool A/B",
        "",
        "| Pool K | Recall@20 | Hit@20 | Recall@5 | Hit@5 | MRR | MAP@5 | Latency (ms) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in report["results"]:
        lines.append(
            f"| {result['retrieval_pool_k']} | {result['recall_at_20']:.4f} | "
            f"{result['hit_at_20']:.4f} | {result['recall_at_5']:.4f} | "
            f"{result['hit_at_5']:.4f} | {result['mrr']:.4f} | "
            f"{result['map_at_5']:.4f} | "
            f"{result['average_retrieval_latency_ms']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## 이전 Pool 대비 변화",
            "",
            "| 구간 | ΔRecall@20 | ΔHit@20 | ΔRecall@5 | ΔMRR | ΔMAP@5 | ΔLatency (ms) |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for delta in report["deltas_from_previous_pool"]:
        lines.append(
            f"| {delta['from_pool_k']}→{delta['to_pool_k']} | "
            f"{delta['recall_at_20_delta']:+.4f} | "
            f"{delta['hit_at_20_delta']:+.4f} | "
            f"{delta['recall_at_5_delta']:+.4f} | {delta['mrr_delta']:+.4f} | "
            f"{delta['map_at_5_delta']:+.4f} | "
            f"{delta['average_retrieval_latency_ms_delta']:+.2f} |"
        )

    saturation = report["exact_saturation_pool_k"]
    lines.extend(
        [
            "",
            "## 판단",
            "",
            (
                f"- Recall@20과 Hit@20의 포화 시작점: Pool K={saturation}"
                if saturation is not None
                else "- Recall@20과 Hit@20의 정확한 포화 지점은 관측되지 않음"
            ),
            (
                "- Cohere 최종 검증 후보: Pool K="
                f"{report['recommended_pool_k_for_cohere_validation']}"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Nori Hybrid retrieval pool sizes without Cohere."
    )
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--retrieval-pool-sizes",
        type=int,
        nargs="+",
        default=list(DEFAULT_POOL_SIZES),
    )
    parser.add_argument(
        "--rerank-candidate-k", type=int, default=DEFAULT_RERANK_CANDIDATE_K
    )
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    cases = (
        load_holdout250_policy_cases()
        if args.cases is None
        else load_retrieval_cases(args.cases)
    )
    report = evaluate_candidate_pools(
        cases,
        settings=settings,
        retrieval_pool_sizes=args.retrieval_pool_sizes,
        rerank_candidate_k=args.rerank_candidate_k,
        top_k=args.top_k,
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
