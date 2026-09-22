from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Literal, TypedDict

from src.core.config import Settings, get_settings
from src.evaluation.metrics import retrieval_metrics
from src.models import get_embedding_model
from src.vectorstores.elasticsearch import ElasticsearchBM25Search
from src.vectorstores.hybrid import BM25Search
from src.vectorstores.postgres import PostgresVectorSearch


class RetrievalCase(TypedDict):
    """LLM 답변 없이 검색 정확도만 측정하는 평가 문항."""

    case_id: str
    question: str
    relevant_policy_ids: list[int]


@dataclass(frozen=True, slots=True)
class RankingMetrics:
    """한 검색 방식의 평균 정확도와 지연시간."""

    precision_at_k: float
    recall_at_k: float
    mrr: float
    map_at_k: float
    hit_at_k: float
    average_latency_ms: float


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    """후보 정책 집합의 평균 Recall과 Hit."""

    recall_at_k: float
    hit_at_k: float


def policy_level_rrf(
    dense_results: list[dict[str, Any]],
    lexical_results: list[dict[str, Any]],
    *,
    rrf_k: int,
    top_k: int,
) -> list[dict[str, Any]]:
    """Dense와 BM25 결과를 정책 ID 기준으로 RRF 결합한다.

    Elasticsearch는 원천 문서 단위, Dense는 청크 단위일 수 있으므로 평가에서
    동일 정책의 청크 수가 많다는 이유만으로 순위가 유리해지지 않게 정책별 최고
    순위 하나만 사용한다.
    """
    if rrf_k < 1 or top_k < 1:
        raise ValueError("rrf_k and top_k must be at least 1")

    scores: dict[int, float] = {}
    representative: dict[int, dict[str, Any]] = {}
    first_seen: dict[int, int] = {}
    for results in (dense_results, lexical_results):
        seen_in_ranking: set[int] = set()
        logical_rank = 0
        for result in results:
            raw_policy_id = result.get("policy_id")
            if raw_policy_id is None:
                continue
            policy_id = int(raw_policy_id)
            if policy_id in seen_in_ranking:
                continue
            seen_in_ranking.add(policy_id)
            logical_rank += 1
            if policy_id not in representative:
                representative[policy_id] = dict(result)
                first_seen[policy_id] = len(first_seen)
            scores[policy_id] = scores.get(policy_id, 0.0) + 1 / (
                rrf_k + logical_rank
            )

    maximum_score = 2 / (rrf_k + 1)
    ranked_ids = sorted(
        scores,
        key=lambda policy_id: (-scores[policy_id], first_seen[policy_id]),
    )[:top_k]
    return [
        {
            **representative[policy_id],
            "policy_id": policy_id,
            "score": scores[policy_id] / maximum_score,
        }
        for policy_id in ranked_ids
    ]


def load_retrieval_cases(path: Path) -> list[RetrievalCase]:
    """기존 평가 JSON에서 정답 정책이 있는 검색 문항만 읽는다."""
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases = [
        RetrievalCase(
            case_id=str(case["case_id"]),
            question=str(case["question"]),
            relevant_policy_ids=[int(value) for value in case["relevant_policy_ids"]],
        )
        for case in raw_cases
        if case.get("relevant_policy_ids") and not case.get("should_block", False)
    ]
    if not cases:
        raise ValueError(f"No retrieval cases with relevant_policy_ids: {path}")
    return cases


def load_holdout250_policy_cases() -> list[RetrievalCase]:
    """holdout250에서 정책 검색 63문항만 개발용 A/B subset으로 읽는다."""
    from evaluation.holdout_cases_250 import HOLDOUT250_POLICY_CASES

    return [
        RetrievalCase(
            case_id=str(case["case_id"]),
            question=str(case["question"]),
            relevant_policy_ids=[int(value) for value in case["relevant_policy_ids"]],
        )
        for case in HOLDOUT250_POLICY_CASES
    ]


def evaluate_retrievers(
    cases: list[RetrievalCase],
    *,
    settings: Settings,
    top_k: int,
    candidate_k: int,
    suite_name: str = "custom",
) -> dict[str, Any]:
    """BM25 단독과 동일 Dense를 공유한 Hybrid 검색을 A/B 평가한다.

    Cohere/Rerank, LangGraph Router/Judge와 최종 답변 LLM은 호출하지 않는다.
    Dense query embedding은 문항당 한 번만 생성해 두 Hybrid 실험군이 공유한다.
    """
    dense_search = PostgresVectorSearch(
        embedding=get_embedding_model(),
        settings=settings,
    )
    memory_bm25 = BM25Search(dense_search.get_chunks())
    elasticsearch_bm25 = ElasticsearchBM25Search(settings)
    if not elasticsearch_bm25.ready():
        raise RuntimeError(
            f"Elasticsearch alias is not ready: {settings.elasticsearch_index_alias}. "
            "Run the indexing command first."
        )

    rows: list[dict[str, Any]] = []
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

        branch_results: dict[str, dict[str, Any]] = {}
        for prefix, lexical_search in (
            ("memory", memory_bm25),
            ("elasticsearch", elasticsearch_bm25),
        ):
            lexical_started = perf_counter()
            lexical_results = lexical_search.search(
                question,
                source_types=("policy", "announcement"),
                require_policy_id=True,
                unique_policy_ids=True,
                top_k=candidate_k,
            )
            lexical_ms = (perf_counter() - lexical_started) * 1000
            lexical_ranking = _policy_ids(lexical_results, top_k)
            branch_results[f"{prefix}_bm25"] = _stage_result(
                lexical_ranking, relevant, top_k, lexical_ms
            )

            fusion_started = perf_counter()
            fused = policy_level_rrf(
                dense_results,
                lexical_results,
                rrf_k=settings.hybrid_rrf_k,
                top_k=candidate_k,
            )
            fusion_ms = (perf_counter() - fusion_started) * 1000
            hybrid_candidate_ranking = _policy_ids(fused, candidate_k)
            hybrid_result = _stage_result(
                hybrid_candidate_ranking[:top_k],
                relevant,
                top_k,
                dense_ms + lexical_ms + fusion_ms,
            )
            hybrid_result["candidate_ranking"] = hybrid_candidate_ranking
            hybrid_result["candidate_metrics"] = _candidate_metrics(
                hybrid_candidate_ranking, relevant, candidate_k
            )
            branch_results[f"{prefix}_hybrid"] = hybrid_result

        rows.append(
            {
                "case_id": case["case_id"],
                "question": question,
                "relevant_policy_ids": sorted(relevant),
                "dense_candidates": _policy_ids(dense_results, candidate_k),
                **branch_results,
            }
        )

    report: dict[str, Any] = {
        "suite": suite_name,
        "case_count": len(rows),
        "top_k": top_k,
        "candidate_k": candidate_k,
        "analyzer_version": "nori-v2-pos",
        "user_dictionary_applied": False,
        "pos_filter_applied": True,
        "index_search_analyzers_separated": True,
        "rerank_used": False,
        "rerank_call_count": 0,
        "memory_bm25": asdict(_aggregate(rows, "memory_bm25")),
        "elasticsearch_bm25": asdict(_aggregate(rows, "elasticsearch_bm25")),
        "memory_hybrid": asdict(_aggregate(rows, "memory_hybrid")),
        "elasticsearch_hybrid": asdict(_aggregate(rows, "elasticsearch_hybrid")),
        "memory_hybrid_candidate": asdict(
            _aggregate_candidate(rows, "memory_hybrid")
        ),
        "elasticsearch_hybrid_candidate": asdict(
            _aggregate_candidate(rows, "elasticsearch_hybrid")
        ),
        "hit_comparison": _hit_comparison(rows),
        "cases": rows,
    }
    return report


def _stage_result(
    ranking: list[int], relevant: set[int], top_k: int, latency_ms: float
) -> dict[str, Any]:
    """문항별 순위, 정확도와 지연시간을 공통 구조로 반환한다."""
    return {
        "ranking": ranking,
        "metrics": _case_metrics(ranking, relevant, top_k),
        "latency_ms": latency_ms,
    }


def _policy_ids(results: list[dict[str, Any]], limit: int) -> list[int]:
    """검색 결과를 중복 없는 정책 ID 순위로 변환한다."""
    ranking: list[int] = []
    seen: set[int] = set()
    for result in results:
        value = result.get("policy_id")
        if value is None or int(value) in seen:
            continue
        policy_id = int(value)
        seen.add(policy_id)
        ranking.append(policy_id)
        if len(ranking) >= limit:
            break
    return ranking


def _case_metrics(ranking: list[int], relevant: set[int], top_k: int) -> dict[str, float]:
    metrics = retrieval_metrics(ranking, relevant, top_k)
    return {
        "precision_at_k": metrics.precision_at_k,
        "recall_at_k": metrics.recall_at_k,
        "reciprocal_rank": metrics.reciprocal_rank,
        "average_precision": metrics.average_precision,
        "hit_at_k": float(bool(set(ranking[:top_k]) & relevant)),
    }


def _candidate_metrics(
    ranking: list[int], relevant: set[int], candidate_k: int
) -> dict[str, float]:
    """고유 정책 후보 순위의 Recall@candidate_k와 Hit@candidate_k를 계산한다."""
    relevant_hits = set(ranking[:candidate_k]) & relevant
    return {
        "recall_at_k": len(relevant_hits) / len(relevant) if relevant else 0.0,
        "hit_at_k": float(bool(relevant_hits)),
    }


def _aggregate(
    rows: list[dict[str, Any]],
    stage: Literal[
        "memory_bm25",
        "elasticsearch_bm25",
        "memory_hybrid",
        "elasticsearch_hybrid",
    ],
) -> RankingMetrics:
    values = [row[stage] for row in rows]
    return RankingMetrics(
        precision_at_k=mean(value["metrics"]["precision_at_k"] for value in values),
        recall_at_k=mean(value["metrics"]["recall_at_k"] for value in values),
        mrr=mean(value["metrics"]["reciprocal_rank"] for value in values),
        map_at_k=mean(value["metrics"]["average_precision"] for value in values),
        hit_at_k=mean(value["metrics"]["hit_at_k"] for value in values),
        average_latency_ms=mean(value["latency_ms"] for value in values),
    )


def _aggregate_candidate(
    rows: list[dict[str, Any]],
    stage: Literal["memory_hybrid", "elasticsearch_hybrid"],
) -> CandidateMetrics:
    values = [row[stage]["candidate_metrics"] for row in rows]
    return CandidateMetrics(
        recall_at_k=mean(value["recall_at_k"] for value in values),
        hit_at_k=mean(value["hit_at_k"] for value in values),
    )


def _hit_comparison(rows: list[dict[str, Any]]) -> dict[str, int]:
    """두 Hybrid 방식의 문항별 Hit/Miss 교차 건수를 계산한다."""
    counts = {"memory_only": 0, "nori_only": 0, "both_hit": 0, "both_miss": 0}
    for row in rows:
        memory_hit = bool(row["memory_hybrid"]["metrics"]["hit_at_k"])
        nori_hit = bool(row["elasticsearch_hybrid"]["metrics"]["hit_at_k"])
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
    """BM25 단독·Hybrid A/B 결과를 Markdown 보고서로 변환한다."""
    hit = report["hit_comparison"]
    lines = [
        "# Nori POS Analyzer 검색 A/B 평가 보고서",
        "",
        "## 평가 설정",
        "",
        f"- 평가셋: {report['suite']}",
        f"- 평가 문항: {report['case_count']}건",
        f"- Top-K: {report['top_k']}",
        f"- candidate_k: {report['candidate_k']}",
        "- Cohere Rerank: 미사용",
        f"- Cohere 호출: {report['rerank_call_count']}회",
        "- 기존 방식: Dense + Memory BM25 + 정책 단위 RRF",
        "- 개선 방식: Dense + Elasticsearch Nori POS BM25 + 정책 단위 RRF",
        "- 후보 구성: 각 검색기에서 중복 없는 policy_id 20개",
        "- 사용자 사전: 미사용",
        "- custom nori_part_of_speech: 적용",
        "- index/search analyzer: 분리 적용",
        "- 최종 답변·LangGraph Router·Judge: 미실행",
        "- 주의: 기존 평가에 노출된 개발용 A/B subset이며 신규 홀드아웃 성능이 아님",
        "",
        "## BM25 단독 성능",
        "",
        *_markdown_metric_table(
            report["memory_bm25"],
            report["elasticsearch_bm25"],
            "기존 Memory BM25",
            "개선 Nori BM25",
        ),
        "",
        "## Hybrid 성능",
        "",
        *_markdown_metric_table(
            report["memory_hybrid"],
            report["elasticsearch_hybrid"],
            "기존 Hybrid",
            "개선 Nori Hybrid",
        ),
        "",
        f"## Hybrid 고유 정책 후보 Top-{report['candidate_k']} 성능",
        "",
        *_markdown_candidate_metric_table(report),
        "",
        "## Hybrid Hit@5 비교 요약",
        "",
        f"- 기존만 성공: {hit['memory_only']}건",
        f"- 개선 Nori만 성공: {hit['nori_only']}건",
        f"- 둘 다 성공: {hit['both_hit']}건",
        f"- 둘 다 실패: {hit['both_miss']}건",
    ]
    lines.extend(["", "## 결과 해석", "", *_interpretation_lines(report), ""])
    return "\n".join(lines)


def _markdown_metric_table(
    memory: dict[str, float],
    elastic: dict[str, float],
    memory_label: str,
    elastic_label: str,
) -> list[str]:
    """기존·Elasticsearch 지표와 개선 폭을 Markdown 표로 만든다."""
    labels = (
        ("Precision@5", "precision_at_k"),
        ("Recall@5", "recall_at_k"),
        ("MRR", "mrr"),
        ("MAP@5", "map_at_k"),
        ("Hit@5", "hit_at_k"),
        ("평균 지연시간(ms)", "average_latency_ms"),
    )
    rows = [
        f"| 지표 | {memory_label} | {elastic_label} | 차이(Nori-기존) |",
        "|---|---:|---:|---:|",
    ]
    for label, key in labels:
        memory_value = float(memory[key])
        elastic_value = float(elastic[key])
        rows.append(
            f"| {label} | {memory_value:.4f} | {elastic_value:.4f} | "
            f"{elastic_value - memory_value:+.4f} |"
        )
    return rows


def _markdown_candidate_metric_table(report: dict[str, Any]) -> list[str]:
    """고유 정책 candidate_k 기준 Hybrid Recall과 Hit 표를 만든다."""
    candidate_k = report["candidate_k"]
    memory = report["memory_hybrid_candidate"]
    elastic = report["elasticsearch_hybrid_candidate"]
    rows = [
        "| 지표 | 기존 Hybrid | 개선 Nori Hybrid | 차이(Nori-기존) |",
        "|---|---:|---:|---:|",
    ]
    for label, key in (
        (f"Recall@{candidate_k}", "recall_at_k"),
        (f"Hit@{candidate_k}", "hit_at_k"),
    ):
        difference = float(elastic[key]) - float(memory[key])
        rows.append(
            f"| {label} | {float(memory[key]):.4f} | "
            f"{float(elastic[key]):.4f} | {difference:+.4f} |"
        )
    return rows


def _interpretation_lines(report: dict[str, Any]) -> list[str]:
    """Hybrid 주요 지표 차이를 방향 그대로 기술한다."""
    lines: list[str] = []
    for label, key in (
        ("Recall@5", "recall_at_k"),
        ("MRR", "mrr"),
        ("MAP@5", "map_at_k"),
        ("Hit@5", "hit_at_k"),
    ):
        difference = (
            float(report["elasticsearch_hybrid"][key])
            - float(report["memory_hybrid"][key])
        )
        direction = "개선" if difference > 0 else "하락" if difference < 0 else "동일"
        lines.append(f"- Hybrid {label}: {direction} ({difference:+.4f})")
    lines.append("- 이 정책 평가 결과만으로 세금 검색 성능을 결론내리지 않는다.")
    return lines


def _markdown_cell(value: object) -> str:
    """Markdown 표 구분자가 셀 내용을 깨뜨리지 않도록 이스케이프한다."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Dense+memory BM25 and Dense+Elasticsearch BM25 without LLM answers."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help="Optional custom JSON. If omitted, holdout250 policy 63 cases are used.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Explicit marker retained for this retrieval-only experiment.",
    )
    return parser.parse_args()


def main() -> None:
    """검색 A/B 평가 CLI. Elasticsearch 적재는 자동 실행하지 않는다."""
    args = _parse_args()
    if args.top_k < 1 or args.candidate_k < args.top_k:
        raise ValueError("candidate-k must be greater than or equal to top-k")
    settings = get_settings()
    if args.cases is None:
        cases = load_holdout250_policy_cases()
        suite_name = "holdout250-policy63-development-subset"
    else:
        cases = load_retrieval_cases(args.cases)
        suite_name = f"custom:{args.cases.as_posix()}"
    report = evaluate_retrievers(
        cases,
        settings=settings,
        top_k=args.top_k,
        candidate_k=args.candidate_k,
        suite_name=suite_name,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_output = args.output.with_suffix(".md")
    markdown_output.write_text(
        render_markdown_report(report),
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, ensure_ascii=False, indent=2))
    print(f"json_report={args.output}")
    print(f"markdown_report={markdown_output}")


if __name__ == "__main__":
    main()
