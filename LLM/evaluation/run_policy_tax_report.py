"""Run a bounded policy/tax evaluation and save JSON plus a Markdown report.

From the LLM directory:
    uv run --frozen python -m evaluation.run_policy_tax_report
    uv run --frozen python -m evaluation.run_policy_tax_report --half
    uv run --frozen python -m evaluation.run_policy_tax_report --full

The default is a fixed smoke run (4 policy cases, 2 tax scenarios / 4 turns).
The --half mode runs all 31 tax scenarios / 62 turns and skips policy evaluation.
The complete 63+62 holdout evaluation requires the explicit --full flag.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

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

from evaluation.run_policy_tax125 import PolicyProgressClient, TaxProgressClient


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "Docs" / "reports"
RESULT_DIR = ROOT / "LLM" / "evaluation" / "results"
SMOKE_POLICY_IDS = (
    "holdout-policy-techbiz-clinic",
    "holdout-policy-small-export-shipping",
    "holdout-policy-anyang-interest-support",
    "holdout-policy-youth-food-hub",
)
SMOKE_TAX_IDS = (
    "holdout-tax-business-transfer",
    "holdout-tax-general-vat-adjustments",
)


def _prioritized(items: list, ids: tuple[str, ...], id_field: str) -> list:
    by_id = {getattr(item, id_field): item for item in items}
    missing = set(ids) - by_id.keys()
    if missing:
        raise ValueError(f"Smoke case IDs missing: {sorted(missing)}")
    return [by_id[item_id] for item_id in ids] + [
        item for item in items if getattr(item, id_field) not in ids
    ]


def parser() -> argparse.ArgumentParser:
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("--base-url", default="http://127.0.0.1:8001")
    mode = options.add_mutually_exclusive_group()
    mode.add_argument("--half", action="store_true", help="run all 62 tax turns and skip policy")
    mode.add_argument("--full", action="store_true", help="run all 63 policy cases and 62 tax turns")
    options.add_argument("--policy-count", type=int, default=4)
    options.add_argument("--tax-scenarios", type=int, default=2)
    options.add_argument("--output", type=Path, help="Markdown output path; default is timestamped")
    options.add_argument("--policy-json", type=Path, help="existing policy JSON; requires --tax-json")
    options.add_argument("--tax-json", type=Path, help="existing tax JSON; requires --policy-json")
    return options


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _link(path: Path, report_path: Path) -> str:
    return Path(os.path.relpath(path.resolve(), report_path.parent.resolve())).as_posix()


def _collect_tax_latency_logs(since: datetime) -> list[str]:
    """Collect structured tax stage timings emitted by the local LLM container."""
    result = subprocess.run(
        ["docker", "compose", "logs", "--since", since.isoformat(), "llm"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        print("Warning: could not collect TAX_LATENCY Docker logs", flush=True)
        return []
    return [
        line[line.index("TAX_LATENCY"):]
        for line in result.stdout.splitlines()
        if "TAX_LATENCY" in line
    ]


def render_markdown(
    policy: EvaluationReport,
    tax: GraphEvaluationReport,
    *,
    report_path: Path,
    policy_path: Path,
    tax_path: Path,
    source: str,
) -> str:
    """Use the existing evaluators' metrics; do not rescore answers here."""
    policy_cases = policy.cases
    tax_scenarios = tax.scenarios
    turn_count = sum(len(item.turns) for item in tax_scenarios)
    passed_turns = sum(score.passed for item in tax_scenarios for score in item.turns)
    found_all = sum(
        bool(item.relevant_policy_ids)
        and set(item.relevant_policy_ids) <= set(item.predicted_policy_ids[: policy.summary.k])
        for item in policy_cases
    )
    policy_misses = [
        item.case_id for item in policy_cases
        if item.retrieval is not None and item.retrieval.recall_at_k < 1
    ]
    tax_failures = [
        (scenario.scenario_id, index, [name for name, ok in score.checks.items() if not ok])
        for scenario in tax_scenarios
        for index, score in enumerate(scenario.turns, start=1)
        if not score.passed
    ]
    lines = [
        f"# 정책·세금 평가 결과 — {datetime.now().astimezone():%Y-%m-%d %H:%M}",
        "",
        f"평가 범위: **{source}**. 기존 holdout250에서 정책·세금만 평가했습니다. "
        "Guardrail·로드맵은 포함하지 않았습니다.",
        "",
        "| 영역 | 실행 규모 | 핵심 결과 | 평균 응답 시간 |",
        "| --- | ---: | ---: | ---: |",
        f"| 정책 | {len(policy_cases)}문항 | R@{policy.summary.k} {_pct(policy.summary.recall_at_k)} | {policy.summary.average_latency_ms / 1000:.2f}초 |",
        f"| 세금 | {len(tax_scenarios)}시나리오·{turn_count}턴 | {passed_turns}/{turn_count} 통과 ({_pct(tax.turn_pass_rate)}) | {tax.average_latency_ms / 1000:.2f}초 |",
        "",
        "정책 R@5와 세금 턴 통과율은 다른 지표이므로 합산하지 않습니다. "
        "자동 채점 통과는 법률 해석이나 계산 금액의 정확성을 보증하지 않습니다.",
        "",
        "평가 ID: 정책 " + ", ".join(f"`{item.case_id}`" for item in policy_cases),
        "",
        "평가 ID: 세금 " + ", ".join(f"`{item.scenario_id}`" for item in tax_scenarios),
        "",
        "## 정책 검색",
        "",
        f"- R@{policy.summary.k}: **{_pct(policy.summary.recall_at_k)}**, "
        f"P@{policy.summary.k}: {_pct(policy.summary.precision_at_k)}, "
        f"MRR: {_pct(policy.summary.mrr)}",
        f"- 정답 정책을 모두 찾은 문항: **{found_all}/{len(policy_cases)}**",
        f"- 일부 또는 전체를 놓친 문항: {', '.join(f'`{case_id}`' for case_id in policy_misses) or '없음'}",
        "",
        "## 세금 답변",
        "",
        f"- 턴 통과: **{passed_turns}/{turn_count} ({_pct(tax.turn_pass_rate)})**",
        f"- 시나리오 전체 통과: **{sum(item.passed for item in tax_scenarios)}/{len(tax_scenarios)} "
        f"({_pct(tax.scenario_pass_rate)})**",
        "- 실패 턴:",
    ]
    lines.extend(
        f"  - `{scenario_id}` {index}턴: {', '.join(checks)}"
        for scenario_id, index, checks in tax_failures
    )
    if not tax_failures:
        lines.append("  - 없음")
    lines += [
        "",
        f"원시 결과: [정책 JSON]({_link(policy_path, report_path)}) · "
        f"[세금 JSON]({_link(tax_path, report_path)})",
        "",
    ]
    return "\n".join(lines)


def render_tax_markdown(
    tax: GraphEvaluationReport,
    *,
    report_path: Path,
    tax_path: Path,
    latency_path: Path | None = None,
) -> str:
    tax_scenarios = tax.scenarios
    turn_count = sum(len(item.turns) for item in tax_scenarios)
    passed_turns = sum(score.passed for item in tax_scenarios for score in item.turns)
    failures = [
        (scenario.scenario_id, index, [name for name, ok in score.checks.items() if not ok])
        for scenario in tax_scenarios
        for index, score in enumerate(scenario.turns, start=1)
        if not score.passed
    ]
    lines = [
        f"# 세금 RAG HALF 실평가 결과 — {datetime.now().astimezone():%Y-%m-%d %H:%M}",
        "",
        f"평가 범위: holdout250 세금 **{len(tax_scenarios)}개 시나리오·{turn_count}턴**",
        "",
        "| 통과 결과 | 시나리오 전체 통과 | 평균 응답 시간 |",
        "| ---: | ---: | ---: |",
        f"| {passed_turns}/{turn_count} ({_pct(tax.turn_pass_rate)}) | "
        f"{sum(item.passed for item in tax_scenarios)}/{len(tax_scenarios)} "
        f"({_pct(tax.scenario_pass_rate)}) | {tax.average_latency_ms / 1000:.2f}초 |",
        "",
        "평가 ID: " + ", ".join(f"`{item.scenario_id}`" for item in tax_scenarios),
        "",
        "## 실패 턴",
        "",
    ]
    lines.extend(
        f"- `{scenario_id}` {index}턴: {', '.join(checks)}"
        for scenario_id, index, checks in failures
    )
    if not failures:
        lines.append("- 없음")
    lines += ["", f"원시 결과: [세금 JSON]({_link(tax_path, report_path)})"]
    if latency_path is not None:
        lines.append(f"단계별 시간: [Latency 로그]({_link(latency_path, report_path)})")
    lines.append("")
    return "\n".join(lines)


async def run_evaluation(
    *,
    base_url: str,
    full: bool,
    half: bool,
    policy_count: int,
    tax_count: int,
):
    validate_holdout_database()
    tax_scenarios = [
        scenario for scenario in load_evaluation_cases(DEFAULT_DATASET, mode="graph", suite="holdout250")
        if scenario.category == "tax"
    ]
    if len(tax_scenarios) != 31 or sum(len(s.turns) for s in tax_scenarios) != 62:
        raise ValueError("holdout250 tax case counts changed; inspect the dataset")
    if half:
        validate_users({scenario.user_id for scenario in tax_scenarios}, "db")
        async with HttpChatClient(
            base_url, timeout_seconds=130, user_context_provider=database_user_context
        ) as client:
            tax_report = await evaluate_scenarios(
                tax_scenarios,
                TaxProgressClient(client, sum(len(s.turns) for s in tax_scenarios)),
            )
        return None, tax_report

    policy_cases = [
        case for case in load_evaluation_cases(DEFAULT_DATASET, mode="policy", suite="holdout250")
        if case.relevant_policy_ids and not case.should_block
    ]
    if len(policy_cases) != 63:
        raise ValueError("holdout250 policy case counts changed; inspect the dataset")
    if not full:
        policy_cases = _prioritized(policy_cases, SMOKE_POLICY_IDS, "case_id")[:policy_count]
        tax_scenarios = _prioritized(tax_scenarios, SMOKE_TAX_IDS, "scenario_id")[:tax_count]
    validate_users({case.user_id for case in policy_cases}, "db")
    validate_users({scenario.user_id for scenario in tax_scenarios}, "db")
    async with HttpLangGraphClient(base_url, timeout_seconds=60) as client:
        policy_report = await evaluate_cases(
            policy_cases, PolicyProgressClient(client, len(policy_cases)), k=5
        )
    async with HttpChatClient(
        base_url, timeout_seconds=130, user_context_provider=database_user_context
    ) as client:
        tax_report = await evaluate_scenarios(
            tax_scenarios,
            TaxProgressClient(client, sum(len(s.turns) for s in tax_scenarios)),
        )
    return policy_report, tax_report


def main() -> None:
    args = parser().parse_args()
    evaluation_started_at = datetime.now(timezone.utc)
    if (args.policy_json is None) != (args.tax_json is None):
        raise SystemExit("--policy-json and --tax-json must be provided together")
    if args.full and (args.policy_json or args.policy_count != 4 or args.tax_scenarios != 2):
        raise SystemExit("--full cannot be combined with JSON inputs or sample limits")
    if args.half and (args.policy_json or args.policy_count != 4 or args.tax_scenarios != 2):
        raise SystemExit("--half cannot be combined with JSON inputs or sample limits")
    if args.policy_count < 1 or args.tax_scenarios < 1:
        raise SystemExit("sample limits must be positive")
    from_json = args.policy_json is not None
    label = "기존 JSON 재렌더링" if from_json else ("전체 125건" if args.full else "소규모 점검")
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    mode = "TAX_HALF" if args.half else ("FULL" if args.full else "SMOKE")
    prefix = "LLM" if args.half else "LLM_POLICY_TAX"
    output = args.output or REPORT_DIR / f"{prefix}_{mode}_{stamp}.md"
    if output.exists():
        raise SystemExit(f"Output already exists: {output}")
    latency_path = None
    if from_json:
        policy_path, tax_path = args.policy_json, args.tax_json
        policy_report = EvaluationReport.model_validate_json(policy_path.read_text(encoding="utf-8"))
        tax_report = GraphEvaluationReport.model_validate_json(tax_path.read_text(encoding="utf-8"))
    else:
        policy_report, tax_report = asyncio.run(run_evaluation(
            base_url=args.base_url,
            full=args.full,
            half=args.half,
            policy_count=args.policy_count,
            tax_count=args.tax_scenarios,
        ))
        tax_path = RESULT_DIR / f"tax_{stamp}.json"
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        tax_path.write_text(tax_report.model_dump_json(indent=2), encoding="utf-8")
        if policy_report is not None:
            policy_path = RESULT_DIR / f"policy_{stamp}.json"
            policy_path.write_text(policy_report.model_dump_json(indent=2), encoding="utf-8")
        if args.half:
            latency_lines = _collect_tax_latency_logs(evaluation_started_at)
            if latency_lines:
                latency_path = RESULT_DIR / f"tax_latency_{stamp}.log"
                latency_path.write_text(
                    "\n".join(latency_lines) + "\n", encoding="utf-8"
                )
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.half:
        report = render_tax_markdown(
            tax_report,
            report_path=output,
            tax_path=tax_path,
            latency_path=latency_path,
        )
    else:
        report = render_markdown(
            policy_report, tax_report,
            report_path=output, policy_path=policy_path, tax_path=tax_path, source=label,
        )
    output.write_text(report, encoding="utf-8")
    print(f"Saved: {output}", flush=True)


if __name__ == "__main__":
    main()
