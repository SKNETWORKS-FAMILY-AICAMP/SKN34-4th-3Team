from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import mean
from time import perf_counter, sleep
from typing import Any, Callable, Literal, TypedDict

from src.core.config import Settings, get_settings
from src.evaluation.metrics import retrieval_metrics
from src.models import get_embedding_model
from src.rag.reranker import CohereRerankError, rerank_documents
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


class RequestIntervalLimiter:
    """외부 API 요청 시작 간 최소 간격을 보장하는 단순 rate limiter."""

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
        """필요한 만큼 대기하고 실제 대기 요청 시간을 초 단위로 반환한다."""
        now = self._clock()
        wait_seconds = 0.0
        if self._last_request_started is not None:
            elapsed = now - self._last_request_started
            wait_seconds = max(0.0, self._minimum_interval_seconds - elapsed)
            if wait_seconds:
                self._sleeper(wait_seconds)
        self._last_request_started = self._clock()
        return wait_seconds


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
    with_rerank: bool,
    suite_name: str = "custom",
    rerank_min_interval_seconds: float = 1.6,
) -> dict[str, Any]:
    """기존 BM25와 Elasticsearch BM25를 동일 Dense 결과로 A/B 평가한다.

    LangGraph Router, 근거 충분성 Judge와 최종 답변 LLM은 호출하지 않는다.
    Dense query embedding은 문항당 한 번만 생성해 두 실험군이 공유한다.
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

    rerank_limiter = RequestIntervalLimiter(rerank_min_interval_seconds)
    total_throttle_wait_seconds = 0.0

    rows: list[dict[str, Any]] = []
    for case in cases:
        question = case["question"]
        relevant = set(case["relevant_policy_ids"])

        dense_started = perf_counter()
        dense_results = dense_search.search(
            question,
            source_types=("policy", "announcement"),
            require_policy_id=True,
            top_k=candidate_k,
        )
        dense_ms = (perf_counter() - dense_started) * 1000

        branch_results: dict[str, dict[str, Any]] = {}
        for name, lexical_search in (
            ("memory_bm25", memory_bm25),
            ("elasticsearch_bm25", elasticsearch_bm25),
        ):
            branch_started = perf_counter()
            lexical_results = lexical_search.search(
                question,
                source_types=("policy", "announcement"),
                require_policy_id=True,
                top_k=candidate_k,
            )
            fused = policy_level_rrf(
                dense_results,
                lexical_results,
                rrf_k=settings.hybrid_rrf_k,
                top_k=candidate_k,
            )
            retrieval_ms = dense_ms + (perf_counter() - branch_started) * 1000
            pre_rerank_ids = _policy_ids(fused, top_k)
            branch: dict[str, Any] = {
                "ranking": pre_rerank_ids,
                "metrics": _case_metrics(pre_rerank_ids, relevant, top_k),
                "latency_ms": retrieval_ms,
                "dense_candidates": _policy_ids(dense_results, candidate_k),
                "bm25_candidates": _policy_ids(lexical_results, candidate_k),
            }
            if with_rerank:
                total_throttle_wait_seconds += rerank_limiter.wait()
                rerank_started = perf_counter()
                try:
                    reranked = rerank_documents(
                        question,
                        fused,
                        top_n=top_k,
                        settings=settings,
                    )
                except CohereRerankError as exc:
                    raise RuntimeError(f"Rerank failed for {case['case_id']}: {exc}") from exc
                rerank_ids = _policy_ids(reranked, top_k)
                branch["rerank"] = {
                    "ranking": rerank_ids,
                    "metrics": _case_metrics(rerank_ids, relevant, top_k),
                    "latency_ms": retrieval_ms
                    + (perf_counter() - rerank_started) * 1000,
                }
            branch_results[name] = branch

        rows.append(
            {
                "case_id": case["case_id"],
                "question": question,
                "relevant_policy_ids": sorted(relevant),
                **branch_results,
            }
        )

    report: dict[str, Any] = {
        "suite": suite_name,
        "case_count": len(rows),
        "top_k": top_k,
        "candidate_k": candidate_k,
        "with_rerank": with_rerank,
        "rerank_min_interval_seconds": (
            rerank_min_interval_seconds if with_rerank else None
        ),
        "rerank_throttle_wait_seconds": total_throttle_wait_seconds,
        "memory_bm25": asdict(_aggregate(rows, "memory_bm25", top_k)),
        "elasticsearch_bm25": asdict(
            _aggregate(rows, "elasticsearch_bm25", top_k)
        ),
        "cases": rows,
    }
    if with_rerank:
        report["memory_bm25_rerank"] = asdict(
            _aggregate(rows, "memory_bm25", top_k, stage="rerank")
        )
        report["elasticsearch_bm25_rerank"] = asdict(
            _aggregate(rows, "elasticsearch_bm25", top_k, stage="rerank")
        )
    return report


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


def _aggregate(
    rows: list[dict[str, Any]],
    branch: Literal["memory_bm25", "elasticsearch_bm25"],
    top_k: int,
    *,
    stage: Literal["rerank"] | None = None,
) -> RankingMetrics:
    values = [row[branch][stage] if stage else row[branch] for row in rows]
    return RankingMetrics(
        precision_at_k=mean(value["metrics"]["precision_at_k"] for value in values),
        recall_at_k=mean(value["metrics"]["recall_at_k"] for value in values),
        mrr=mean(value["metrics"]["reciprocal_rank"] for value in values),
        map_at_k=mean(value["metrics"]["average_precision"] for value in values),
        hit_at_k=mean(value["metrics"]["hit_at_k"] for value in values),
        average_latency_ms=mean(value["latency_ms"] for value in values),
    )


def render_markdown_report(report: dict[str, Any]) -> str:
    """A/B 평가 JSON 결과를 사람이 읽기 쉬운 Markdown 보고서로 변환한다."""
    lines = [
        "# 검색 방식 A/B 평가 보고서",
        "",
        "## 평가 설정",
        "",
        f"- 평가셋: {report.get('suite', 'custom')}",
        f"- 평가 문항: {report['case_count']}건",
        f"- 최종 평가 순위: Top-{report['top_k']}",
        f"- RRF 후보 수: {report['candidate_k']}",
        f"- Rerank 포함: {'예' if report['with_rerank'] else '아니요'}",
        f"- Cohere 최소 호출 간격: {report.get('rerank_min_interval_seconds') or 0}초",
        "- 기존 방식: Dense + 메모리 BM25 + 정책 단위 RRF + Rerank",
        "- 개선 방식: Dense + Elasticsearch Nori BM25 + 정책 단위 RRF + Rerank",
        "- 최종 자연어 답변 생성 및 LLM 근거 충분성 판단: 미실행",
        "- 주의: 기존 평가에 노출된 개발용 A/B subset이며 신규 홀드아웃 성능이 아님",
        "",
        "## 최종 결과",
        "",
    ]
    final_memory_key = (
        "memory_bm25_rerank" if report["with_rerank"] else "memory_bm25"
    )
    final_elastic_key = (
        "elasticsearch_bm25_rerank"
        if report["with_rerank"]
        else "elasticsearch_bm25"
    )
    lines.extend(
        _markdown_metric_table(
            report[final_memory_key],
            report[final_elastic_key],
        )
    )
    if report["with_rerank"]:
        lines.extend(
            [
                "",
                "## Rerank 전 결과",
                "",
                *_markdown_metric_table(
                    report["memory_bm25"],
                    report["elasticsearch_bm25"],
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## 문항별 최종 순위",
            "",
            "| Case | 정답 정책 ID | 기존 방식 Top-K | Elasticsearch 방식 Top-K | 기존 Hit | ES Hit |",
            "|---|---|---|---|---:|---:|",
        ]
    )
    stage = "rerank" if report["with_rerank"] else None
    for case in report["cases"]:
        memory = case["memory_bm25"][stage] if stage else case["memory_bm25"]
        elastic = (
            case["elasticsearch_bm25"][stage]
            if stage
            else case["elasticsearch_bm25"]
        )
        relevant = ", ".join(map(str, case["relevant_policy_ids"]))
        memory_ranking = ", ".join(map(str, memory["ranking"])) or "-"
        elastic_ranking = ", ".join(map(str, elastic["ranking"])) or "-"
        lines.append(
            f"| {_markdown_cell(case['case_id'])} | {relevant} | {memory_ranking} | "
            f"{elastic_ranking} | {int(memory['metrics']['hit_at_k'])} | "
            f"{int(elastic['metrics']['hit_at_k'])} |"
        )
    lines.extend(
        [
            "",
            "## 해석 주의사항",
            "",
            "- 두 방식은 동일한 Dense 검색 결과를 공유한다.",
            "- 최종 비교는 Rerank가 포함된 결과를 기준으로 한다.",
            "- Elasticsearch는 원천 문서 단위, 기존 검색은 청크 단위이므로 정책 ID 단위로 중복을 제거해 평가한다.",
            "- 본 보고서는 검색 정확도 평가이며 최종 LLM 답변 품질을 측정하지 않는다.",
            "",
        ]
    )
    return "\n".join(lines)


def _markdown_metric_table(
    memory: dict[str, float], elastic: dict[str, float]
) -> list[str]:
    """기존·Elasticsearch 지표와 개선 폭을 Markdown 표로 만든다."""
    labels = (
        ("Precision@K", "precision_at_k"),
        ("Recall@K", "recall_at_k"),
        ("MRR", "mrr"),
        ("MAP@K", "map_at_k"),
        ("Hit@K", "hit_at_k"),
        ("평균 지연시간(ms)", "average_latency_ms"),
    )
    rows = [
        "| 지표 | 기존 방식 | Elasticsearch 방식 | 차이(ES-기존) |",
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
        "--rerank-min-interval-seconds",
        type=float,
        default=1.6,
        help="Minimum interval between Cohere calls. Default 1.6s (about 37.5/min).",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_false",
        dest="with_rerank",
        help="Disable Cohere rerank only for intermediate retrieval diagnostics.",
    )
    parser.set_defaults(with_rerank=True)
    return parser.parse_args()


def main() -> None:
    """검색 A/B 평가 CLI. Elasticsearch 적재는 자동 실행하지 않는다."""
    args = _parse_args()
    if args.top_k < 1 or args.candidate_k < args.top_k:
        raise ValueError("candidate-k must be greater than or equal to top-k")
    if args.rerank_min_interval_seconds < 1.5:
        raise ValueError(
            "rerank-min-interval-seconds must be at least 1.5 to stay at or below 40/min"
        )
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
        with_rerank=args.with_rerank,
        suite_name=suite_name,
        rerank_min_interval_seconds=args.rerank_min_interval_seconds,
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
