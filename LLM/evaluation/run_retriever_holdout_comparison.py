"""Evaluate only holdout250 questions that exercise the production retriever.

Scope is intentionally fixed to:

* 63 allowed policy questions with gold policy IDs.
* 9 tax ``legal_evidence`` scenarios (18 turns).

Guardrail, roadmap, calculation-only, need-more-info, unsupported-year and
out-of-scope tax cases are excluded.  The script saves raw JSON and a Markdown
comparison against the latest pre-Elasticsearch figures recorded in
``Docs/reports/06_EVAL_250_COMPARISON.md``.

Run from ``LLM``::

    uv run --frozen python -m evaluation.run_retriever_holdout_comparison

Render again without API calls::

    uv run --frozen python -m evaluation.run_retriever_holdout_comparison \
      --policy-json evaluation/results/retriever_policy_YYYYMMDD_HHMMSS.json \
      --tax-json evaluation/results/retriever_tax_YYYYMMDD_HHMMSS.json

The live run calls the operating graph, so question embedding, Cohere Rerank
and LLM costs can occur.  Request starts are spaced by 6.1 seconds by default.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic

from src.evaluation.evaluator import EvaluationReport, evaluate_cases
from src.evaluation.graph_evaluator import GraphEvaluationReport, evaluate_scenarios
from src.evaluation.run_evaluation import (
    DEFAULT_DATASET,
    HttpChatClient,
    HttpLangGraphClient,
    database_user_context,
    load_evaluation_cases,
    validate_holdout_database,
    validate_users,
)


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "Docs" / "reports"
RESULT_DIR = ROOT / "LLM" / "evaluation" / "results"
BASELINE_REPORT = REPORT_DIR / "06_EVAL_250_COMPARISON.md"
EXPECTED_POLICY_CASES = 63
EXPECTED_TAX_SCENARIOS = 9
EXPECTED_TAX_TURNS = 18
DEFAULT_REQUEST_INTERVAL_SECONDS = 6.1


@dataclass(frozen=True)
class PolicyBaseline:
    precision_at_5: float = 0.187
    recall_at_5: float = 0.730
    hit: int = 53
    mrr: float = 0.758
    map_at_5: float = 0.655
    complete: int = 39
    total: int = 63
    average_latency_seconds: float = 3.85


@dataclass(frozen=True)
class TaxLegalBaseline:
    passed_turns: int = 13
    total_turns: int = 18
    passed_scenarios: int = 6
    total_scenarios: int = 9
    status_passed: int = 13
    grounded_passed: int = 18


POLICY_BASELINE = PolicyBaseline()
TAX_BASELINE = TaxLegalBaseline()


class RequestStartLimiter:
    """Space client request starts to reduce burst pressure on external APIs."""

    def __init__(self, minimum_interval_seconds: float) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds must be nonnegative")
        self.minimum_interval_seconds = minimum_interval_seconds
        self._last_started_at: float | None = None

    async def wait(self) -> None:
        now = monotonic()
        if self._last_started_at is not None:
            remaining = self.minimum_interval_seconds - (now - self._last_started_at)
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last_started_at = monotonic()


class PolicyProgressClient:
    def __init__(
        self, client: HttpLangGraphClient, total: int, limiter: RequestStartLimiter,
    ) -> None:
        self.client = client
        self.total = total
        self.completed = 0
        self.limiter = limiter

    async def recommend(self, *, user_id: int, question: str, top_k: int):
        await self.limiter.wait()
        result = await self.client.recommend(
            user_id=user_id, question=question, top_k=top_k
        )
        self.completed += 1
        print(f"policy {self.completed}/{self.total}", flush=True)
        return result


class TaxProgressClient:
    def __init__(
        self, client: HttpChatClient, total: int, limiter: RequestStartLimiter,
    ) -> None:
        self.client = client
        self.total = total
        self.completed = 0
        self.limiter = limiter

    async def answer(
        self, *, user_id: int, category: str, question: str,
        history: list[dict[str, str]], roadmap_step: str | None,
    ):
        await self.limiter.wait()
        result = await self.client.answer(
            user_id=user_id,
            category=category,
            question=question,
            history=history,
            roadmap_step=roadmap_step,
        )
        self.completed += 1
        print(f"tax legal {self.completed}/{self.total}", flush=True)
        return result


def parser() -> argparse.ArgumentParser:
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("--base-url", default="http://127.0.0.1:8001")
    options.add_argument("--output", type=Path, help="Markdown output; default is timestamped")
    options.add_argument("--policy-json", type=Path, help="existing raw policy result")
    options.add_argument("--tax-json", type=Path, help="existing raw tax result")
    options.add_argument(
        "--request-interval-seconds",
        type=float,
        default=DEFAULT_REQUEST_INTERVAL_SECONDS,
        help="minimum interval between HTTP request starts (default: 6.1)",
    )
    options.add_argument(
        "--dry-run", action="store_true",
        help="validate and print the fixed evaluation scope without API calls",
    )
    return options


def load_retriever_scope():
    policy_cases = [
        case
        for case in load_evaluation_cases(DEFAULT_DATASET, mode="policy", suite="holdout250")
        if case.relevant_policy_ids and not case.should_block
    ]
    tax_scenarios = [
        scenario
        for scenario in load_evaluation_cases(DEFAULT_DATASET, mode="graph", suite="holdout250")
        if scenario.category == "tax" and "legal_evidence" in scenario.tags
    ]
    tax_turns = sum(len(scenario.turns) for scenario in tax_scenarios)
    if len(policy_cases) != EXPECTED_POLICY_CASES:
        raise ValueError(
            f"holdout250 policy scope changed: expected {EXPECTED_POLICY_CASES}, "
            f"got {len(policy_cases)}"
        )
    if (len(tax_scenarios), tax_turns) != (EXPECTED_TAX_SCENARIOS, EXPECTED_TAX_TURNS):
        raise ValueError(
            "holdout250 tax legal scope changed: expected "
            f"{EXPECTED_TAX_SCENARIOS} scenarios/{EXPECTED_TAX_TURNS} turns, "
            f"got {len(tax_scenarios)}/{tax_turns}"
        )
    return policy_cases, tax_scenarios


async def run_live(base_url: str, request_interval_seconds: float):
    validate_holdout_database()
    policy_cases, tax_scenarios = load_retriever_scope()
    validate_users({case.user_id for case in policy_cases}, "db")
    validate_users({scenario.user_id for scenario in tax_scenarios}, "db")
    limiter = RequestStartLimiter(request_interval_seconds)

    async with HttpLangGraphClient(base_url, timeout_seconds=90) as client:
        policy_report = await evaluate_cases(
            policy_cases,
            PolicyProgressClient(client, len(policy_cases), limiter),
            k=5,
        )

    async with HttpChatClient(
        base_url,
        timeout_seconds=180,
        user_context_provider=database_user_context,
    ) as client:
        tax_report = await evaluate_scenarios(
            tax_scenarios,
            TaxProgressClient(client, EXPECTED_TAX_TURNS, limiter),
        )
    return policy_report, tax_report


def validate_reports(policy: EvaluationReport, tax: GraphEvaluationReport) -> None:
    if policy.summary.k != 5 or len(policy.cases) != EXPECTED_POLICY_CASES:
        raise ValueError("policy JSON is not the fixed holdout250 63-case R@5 result")
    if policy.summary.retrieval_cases != EXPECTED_POLICY_CASES:
        raise ValueError("policy JSON contains non-retrieval or blocked cases")
    turn_count = sum(len(scenario.turns) for scenario in tax.scenarios)
    if (len(tax.scenarios), turn_count) != (EXPECTED_TAX_SCENARIOS, EXPECTED_TAX_TURNS):
        raise ValueError("tax JSON is not the 9-scenario/18-turn legal_evidence result")
    if any("legal_evidence" not in scenario.tags for scenario in tax.scenarios):
        raise ValueError("tax JSON contains a non-legal_evidence scenario")


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _delta(current: float, baseline: float, *, unit: str = "%p") -> str:
    difference = (current - baseline) * (100 if unit == "%p" else 1)
    if abs(difference) < 0.0005:
        return "0.0%p" if unit == "%p" else "0.00"
    return f"{difference:+.1f}%p" if unit == "%p" else f"{difference:+.2f}"


def _count_rate(count: int, total: int) -> str:
    return f"{count}/{total} ({_pct(count / total if total else 0.0)})"


def _relative_link(path: Path, report_path: Path) -> str:
    return Path(os.path.relpath(path.resolve(), report_path.parent.resolve())).as_posix()


def render_markdown(
    policy: EvaluationReport,
    tax: GraphEvaluationReport,
    *,
    report_path: Path,
    policy_path: Path,
    tax_path: Path,
) -> str:
    validate_reports(policy, tax)
    summary = policy.summary
    found_all = sum(
        set(case.relevant_policy_ids) <= set(case.predicted_policy_ids[: summary.k])
        for case in policy.cases
    )
    hit_count = sum(
        bool(set(case.relevant_policy_ids) & set(case.predicted_policy_ids[: summary.k]))
        for case in policy.cases
    )
    hit_at_5 = hit_count / len(policy.cases)
    tax_scores = [score for scenario in tax.scenarios for score in scenario.turns]
    passed_turns = sum(score.passed for score in tax_scores)
    passed_scenarios = sum(scenario.passed for scenario in tax.scenarios)
    status_passed = sum(score.checks.get("status", False) for score in tax_scores)
    grounded_passed = sum(score.checks.get("grounded", False) for score in tax_scores)
    composite_current = found_all + passed_turns
    composite_baseline = POLICY_BASELINE.complete + TAX_BASELINE.passed_turns
    failed_policy = [
        case.case_id
        for case in policy.cases
        if case.retrieval is not None and case.retrieval.recall_at_k < 1
    ]
    failed_tax = [
        (scenario.scenario_id, turn_index, [name for name, ok in score.checks.items() if not ok])
        for scenario in tax.scenarios
        for turn_index, score in enumerate(scenario.turns, start=1)
        if not score.passed
    ]

    baseline_link = _relative_link(BASELINE_REPORT, report_path)
    policy_link = _relative_link(policy_path, report_path)
    tax_link = _relative_link(tax_path, report_path)
    lines = [
        f"# Elasticsearch 검색기 holdout250 비교 — {datetime.now().astimezone():%Y-%m-%d %H:%M}",
        "",
        "## 결론",
        "",
        "이 평가는 holdout250 중 **운영 Dense + Elasticsearch Nori BM25 → policy/source-level "
        "RRF → Cohere Rerank 검색기를 사용하는 81턴**만 대상으로 한다. 기준선은 "
        f"[{BASELINE_REPORT.name}]({baseline_link})의 2026-09-16 결과다.",
        "",
        "| 보고용 범위 | 기존 | Elasticsearch 적용 후 | 변화 |",
        "| --- | ---: | ---: | ---: |",
        f"| 정책 정답 완전 검색 | {_count_rate(POLICY_BASELINE.complete, POLICY_BASELINE.total)} | "
        f"**{_count_rate(found_all, len(policy.cases))}** | "
        f"{_delta(found_all / len(policy.cases), POLICY_BASELINE.complete / POLICY_BASELINE.total)} |",
        f"| 세금 법령 답변 통과 | {_count_rate(TAX_BASELINE.passed_turns, TAX_BASELINE.total_turns)} | "
        f"**{_count_rate(passed_turns, len(tax_scores))}** | "
        f"{_delta(passed_turns / len(tax_scores), TAX_BASELINE.passed_turns / TAX_BASELINE.total_turns)} |",
        f"| 보고용 복합 통과¹ | {_count_rate(composite_baseline, 81)} | "
        f"**{_count_rate(composite_current, 81)}** | "
        f"{_delta(composite_current / 81, composite_baseline / 81)} |",
        "",
        "¹ 정책의 ‘정답 완전 검색’ 63건과 세금의 ‘답변 자동검사 통과’ 18건을 기존 "
        "보고 방식처럼 합산한 참고값이다. 두 항목의 의미가 다르므로 순수 검색 Recall로 해석하지 않는다.",
        "",
        "## 평가 범위와 공정성 조건",
        "",
        "- 정책: 허용 질문 63건. 상위 5개 고유 policy_id를 기존 정답 policy_id와 비교한다.",
        "- 세금: `legal_evidence` 9개 시나리오·18턴. status·grounded 등 기존 자동검사를 그대로 사용한다.",
        "- 제외: Guardrail 63건, 로드맵 62턴, 세금 계산 20턴, 추가정보 요구 12턴, "
        "지원연도 초과 6턴, 범위 밖 6턴.",
        "- 현재 운영 설정을 그대로 호출하므로 질문 임베딩·Cohere Rerank·최종 LLM 생성까지 포함한 "
        "종단 간 평가다. 검색기 단독 A/B가 아니다.",
        "- 세금에는 정답 문서 ID가 없어 정책과 같은 Recall을 계산할 수 없다. 따라서 기존 보고서와 "
        "동일하게 답변 통과율과 grounded/status를 비교한다.",
        "",
        "## 정책 검색 성능",
        "",
        "| 지표 | 기존 | Elasticsearch 적용 후 | 변화 |",
        "| --- | ---: | ---: | ---: |",
        f"| P@5 | {_pct(POLICY_BASELINE.precision_at_5)} | **{_pct(summary.precision_at_k)}** | "
        f"{_delta(summary.precision_at_k, POLICY_BASELINE.precision_at_5)} |",
        f"| R@5 | {_pct(POLICY_BASELINE.recall_at_5)} | **{_pct(summary.recall_at_k)}** | "
        f"{_delta(summary.recall_at_k, POLICY_BASELINE.recall_at_5)} |",
        f"| Hit@5 | {_count_rate(POLICY_BASELINE.hit, POLICY_BASELINE.total)} | "
        f"**{_count_rate(hit_count, len(policy.cases))}** | "
        f"{_delta(hit_at_5, POLICY_BASELINE.hit / POLICY_BASELINE.total)} |",
        f"| MRR | {POLICY_BASELINE.mrr:.3f} | **{summary.mrr:.3f}** | "
        f"{_delta(summary.mrr, POLICY_BASELINE.mrr, unit='value')} |",
        f"| MAP@5 | {POLICY_BASELINE.map_at_5:.3f} | **{summary.map:.3f}** | "
        f"{_delta(summary.map, POLICY_BASELINE.map_at_5, unit='value')} |",
        f"| 정답 완전 검색 | {_count_rate(POLICY_BASELINE.complete, POLICY_BASELINE.total)} | "
        f"**{_count_rate(found_all, len(policy.cases))}** | "
        f"{found_all - POLICY_BASELINE.complete:+d}건 |",
        f"| 평균 종단 간 시간 | {POLICY_BASELINE.average_latency_seconds:.2f}초 | "
        f"**{summary.average_latency_ms / 1000:.2f}초** | "
        f"{summary.average_latency_ms / 1000 - POLICY_BASELINE.average_latency_seconds:+.2f}초 |",
        "",
        f"정답 일부/전체 미검색 {len(failed_policy)}건: "
        + (", ".join(f"`{case_id}`" for case_id in failed_policy) or "없음"),
        "",
        "Hit@5는 정답 policy_id가 여러 개인 문항에서도 그중 하나 이상이 Top-5에 있으면 "
        "1로 계산한다. 기존 53/63은 기준 보고서의 완전 검색 39건과 부분 검색 14건의 합이다.",
        "",
        "## 세금 법령 검색 기반 답변",
        "",
        "| 지표 | 기존 | Elasticsearch 적용 후 | 변화 |",
        "| --- | ---: | ---: | ---: |",
        f"| 턴 통과 | {_count_rate(TAX_BASELINE.passed_turns, TAX_BASELINE.total_turns)} | "
        f"**{_count_rate(passed_turns, len(tax_scores))}** | "
        f"{_delta(passed_turns / len(tax_scores), TAX_BASELINE.passed_turns / TAX_BASELINE.total_turns)} |",
        f"| 시나리오 전체 통과 | {_count_rate(TAX_BASELINE.passed_scenarios, TAX_BASELINE.total_scenarios)} | "
        f"**{_count_rate(passed_scenarios, len(tax.scenarios))}** | "
        f"{_delta(passed_scenarios / len(tax.scenarios), TAX_BASELINE.passed_scenarios / TAX_BASELINE.total_scenarios)} |",
        f"| status 검사 | {_count_rate(TAX_BASELINE.status_passed, TAX_BASELINE.total_turns)} | "
        f"**{_count_rate(status_passed, len(tax_scores))}** | "
        f"{_delta(status_passed / len(tax_scores), TAX_BASELINE.status_passed / TAX_BASELINE.total_turns)} |",
        f"| grounded 검사 | {_count_rate(TAX_BASELINE.grounded_passed, TAX_BASELINE.total_turns)} | "
        f"**{_count_rate(grounded_passed, len(tax_scores))}** | "
        f"{_delta(grounded_passed / len(tax_scores), TAX_BASELINE.grounded_passed / TAX_BASELINE.total_turns)} |",
        f"| 현재 평균 종단 간 시간 | 기존 법령 subset 값 없음 | **{tax.average_latency_ms / 1000:.2f}초** | 비교 제외 |",
        "",
        "실패 턴:",
    ]
    lines.extend(
        f"- `{scenario_id}` {turn_index}턴: {', '.join(checks)}"
        for scenario_id, turn_index, checks in failed_tax
    )
    if not failed_tax:
        lines.append("- 없음")
    lines += [
        "",
        "## 해석 제한",
        "",
        "- 기준선 보고서에는 세금 법령 18턴의 별도 latency가 없어 시간 증감은 정책만 비교했다.",
        "- 세금 자동검사의 grounded 통과는 근거 출처가 존재한다는 뜻이며, 정답 법령 문서를 찾았다는 "
        "Recall 지표는 아니다.",
        "- 운영 그래프 전체를 호출하므로 성능 변화에는 검색기 외에도 현재 Router·Rerank·LLM·캐시 "
        "상태가 영향을 줄 수 있다. Elasticsearch의 순수 기여도를 분리하려면 동일 후보에 대한 별도 "
        "retrieval-only A/B가 필요하다.",
        "",
        f"원시 결과: [정책 JSON]({policy_link}) · [세금 법령 JSON]({tax_link})",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    args = parser().parse_args()
    if (args.policy_json is None) != (args.tax_json is None):
        raise SystemExit("--policy-json and --tax-json must be provided together")
    if args.request_interval_seconds < 6.0 and args.policy_json is None and not args.dry_run:
        raise SystemExit("live evaluation requires --request-interval-seconds >= 6.0")
    policy_cases, tax_scenarios = load_retriever_scope()
    if args.dry_run:
        print(
            f"scope valid: policy={len(policy_cases)}, "
            f"tax_scenarios={len(tax_scenarios)}, tax_turns={EXPECTED_TAX_TURNS}, total=81"
        )
        return

    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    report_path = args.output or REPORT_DIR / f"07_RETRIEVER_HOLDOUT_COMPARISON_{stamp}.md"
    if report_path.exists():
        raise SystemExit(f"Output already exists: {report_path}")

    if args.policy_json is not None:
        policy_path = args.policy_json
        tax_path = args.tax_json
        policy_report = EvaluationReport.model_validate_json(
            policy_path.read_text(encoding="utf-8")
        )
        tax_report = GraphEvaluationReport.model_validate_json(
            tax_path.read_text(encoding="utf-8")
        )
    else:
        policy_report, tax_report = asyncio.run(
            run_live(args.base_url, args.request_interval_seconds)
        )
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        policy_path = RESULT_DIR / f"retriever_policy_{stamp}.json"
        tax_path = RESULT_DIR / f"retriever_tax_legal_{stamp}.json"
        policy_path.write_text(policy_report.model_dump_json(indent=2), encoding="utf-8")
        tax_path.write_text(tax_report.model_dump_json(indent=2), encoding="utf-8")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_markdown(
            policy_report,
            tax_report,
            report_path=report_path,
            policy_path=policy_path,
            tax_path=tax_path,
        ),
        encoding="utf-8",
    )
    print(f"Saved: {report_path}", flush=True)


if __name__ == "__main__":
    main()
