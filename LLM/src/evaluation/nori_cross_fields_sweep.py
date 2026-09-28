from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from src.core.config import Settings, get_settings
from src.evaluation.retrieval_ab import (
    CandidateMetrics,
    RankingMetrics,
    RetrievalCase,
    _candidate_metrics,
    _case_metrics,
    _policy_ids,
    load_holdout250_policy_cases,
    load_retrieval_cases,
    policy_level_rrf,
)
from src.models import get_embedding_model
from src.vectorstores.elasticsearch import ElasticsearchBM25Search
from src.vectorstores.postgres import PostgresVectorSearch


DEFAULT_PERCENTAGES = tuple(range(10, 51, 5))


def evaluate_minimum_should_match(
    cases: list[RetrievalCase],
    *,
    settings: Settings,
    percentages: list[int] | tuple[int, ...] = DEFAULT_PERCENTAGES,
    top_k: int = 5,
    candidate_k: int = 20,
) -> dict[str, Any]:
    """Evaluate cross_fields Nori BM25 and Hybrid without Cohere reranking."""
    normalized_percentages = validate_percentages(percentages)
    if top_k < 1 or candidate_k < top_k:
        raise ValueError("candidate_k must be greater than or equal to top_k")
    if not cases:
        raise ValueError("cases must not be empty")

    dense_search = PostgresVectorSearch(
        embedding=get_embedding_model(),
        settings=settings,
    )
    elasticsearch_bm25 = ElasticsearchBM25Search(settings)
    if not elasticsearch_bm25.ready():
        raise RuntimeError(
            f"Elasticsearch alias is not ready: {settings.elasticsearch_index_alias}. "
            "Run the indexing command first."
        )

    samples: dict[int, dict[str, list[dict[str, Any]]]] = {
        percentage: {"bm25": [], "hybrid": []}
        for percentage in normalized_percentages
    }
    for case in cases:
        question = case["question"]
        relevant = set(case["relevant_policy_ids"])

        dense_started = perf_counter()
        dense_results = dense_search.search(
            question,
            source_types=("policy", "announcement"),
            require_policy_id=True,
            unique_policy_ids=True,
            top_k=candidate_k,
        )
        dense_ms = (perf_counter() - dense_started) * 1000

        for percentage in normalized_percentages:
            lexical_started = perf_counter()
            lexical_results = elasticsearch_bm25.search(
                question,
                source_types=("policy", "announcement"),
                require_policy_id=True,
                unique_policy_ids=True,
                multi_match_type="cross_fields",
                minimum_should_match=f"{percentage}%",
                top_k=candidate_k,
            )
            lexical_ms = (perf_counter() - lexical_started) * 1000
            lexical_ranking = _policy_ids(lexical_results, candidate_k)
            samples[percentage]["bm25"].append(
                _sample_metrics(
                    lexical_ranking,
                    relevant,
                    top_k=top_k,
                    candidate_k=candidate_k,
                    latency_ms=lexical_ms,
                )
            )

            fusion_started = perf_counter()
            fused = policy_level_rrf(
                dense_results,
                lexical_results,
                rrf_k=settings.hybrid_rrf_k,
                top_k=candidate_k,
            )
            fusion_ms = (perf_counter() - fusion_started) * 1000
            hybrid_ranking = _policy_ids(fused, candidate_k)
            samples[percentage]["hybrid"].append(
                _sample_metrics(
                    hybrid_ranking,
                    relevant,
                    top_k=top_k,
                    candidate_k=candidate_k,
                    latency_ms=dense_ms + lexical_ms + fusion_ms,
                )
            )

    return {
        "bm25": {
            str(percentage): _aggregate(samples[percentage]["bm25"])
            for percentage in normalized_percentages
        },
        "hybrid": {
            str(percentage): _aggregate(samples[percentage]["hybrid"])
            for percentage in normalized_percentages
        },
    }


def validate_percentages(percentages: list[int] | tuple[int, ...]) -> tuple[int, ...]:
    """Normalize unique minimum_should_match percentages in the requested range."""
    normalized = tuple(sorted(set(percentages)))
    if not normalized:
        raise ValueError("percentages must not be empty")
    if any(value < 10 or value > 50 for value in normalized):
        raise ValueError("every percentage must be between 10 and 50")
    return normalized


def _sample_metrics(
    ranking: list[int],
    relevant: set[int],
    *,
    top_k: int,
    candidate_k: int,
    latency_ms: float,
) -> dict[str, Any]:
    return {
        "ranking": _case_metrics(ranking[:top_k], relevant, top_k),
        "candidate": _candidate_metrics(ranking, relevant, candidate_k),
        "latency_ms": latency_ms,
    }


def _aggregate(samples: list[dict[str, Any]]) -> dict[str, float]:
    ranking = RankingMetrics(
        precision_at_k=mean(item["ranking"]["precision_at_k"] for item in samples),
        recall_at_k=mean(item["ranking"]["recall_at_k"] for item in samples),
        mrr=mean(item["ranking"]["reciprocal_rank"] for item in samples),
        map_at_k=mean(item["ranking"]["average_precision"] for item in samples),
        hit_at_k=mean(item["ranking"]["hit_at_k"] for item in samples),
        average_latency_ms=mean(item["latency_ms"] for item in samples),
    )
    candidate = CandidateMetrics(
        recall_at_k=mean(item["candidate"]["recall_at_k"] for item in samples),
        hit_at_k=mean(item["candidate"]["hit_at_k"] for item in samples),
    )
    return {
        **asdict(ranking),
        "candidate_recall_at_k": candidate.recall_at_k,
        "candidate_hit_at_k": candidate.hit_at_k,
    }


def render_markdown_report(
    report: dict[str, Any], *, top_k: int, candidate_k: int
) -> str:
    """Render aggregate metrics only; omit questions and per-case rankings."""
    lines = ["# Nori cross_fields + minimum_should_match sweep", ""]
    for label, key in (("Nori BM25", "bm25"), ("Nori Hybrid", "hybrid")):
        lines.extend(
            [
                f"## {label}",
                "",
                (
                    f"| minimum_should_match | Precision@{top_k} | Recall@{top_k} | "
                    f"MRR | MAP@{top_k} | Hit@{top_k} | Recall@{candidate_k} | "
                    f"Hit@{candidate_k} | Avg latency (ms) |"
                ),
                "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for percentage, metrics in report[key].items():
            lines.append(
                f"| {percentage}% | {metrics['precision_at_k']:.4f} | "
                f"{metrics['recall_at_k']:.4f} | {metrics['mrr']:.4f} | "
                f"{metrics['map_at_k']:.4f} | {metrics['hit_at_k']:.4f} | "
                f"{metrics['candidate_recall_at_k']:.4f} | "
                f"{metrics['candidate_hit_at_k']:.4f} | "
                f"{metrics['average_latency_ms']:.2f} |"
            )
        lines.append("")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep Elasticsearch Nori cross_fields minimum_should_match without rerank."
        )
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help="Optional custom JSON; default is the holdout250 policy 63 subset.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/results/nori_cross_fields_msm_sweep.md"),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument(
        "--percentages",
        type=int,
        nargs="+",
        default=list(DEFAULT_PERCENTAGES),
        help="Values from 10 through 50; default: 10 15 ... 50.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    cases = (
        load_holdout250_policy_cases()
        if args.cases is None
        else load_retrieval_cases(args.cases)
    )
    report = evaluate_minimum_should_match(
        cases,
        settings=settings,
        percentages=args.percentages,
        top_k=args.top_k,
        candidate_k=args.candidate_k,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_markdown_report(
            report,
            top_k=args.top_k,
            candidate_k=args.candidate_k,
        ),
        encoding="utf-8",
    )
    print(f"markdown_report={args.output}")


if __name__ == "__main__":
    main()
