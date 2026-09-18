"""Trace the fourteen failed holdout Tax legal-evidence turns."""

import asyncio
import json
from collections import Counter
from pathlib import Path

from pydantic import TypeAdapter

from evaluation.evaluation_cases import GRAPH_SCENARIOS_BY_SUITE
from src.core.config import get_settings
from src.data.postgres_repository import get_user_profile
from src.evaluation.graph_evaluator import ConversationScenario
from src.models.factory import get_embedding_model, get_llm
from src.rag.graph import build_graph
from src.vectorstores.hybrid import HybridSearch
from src.vectorstores.postgres import PostgresVectorSearch


BASELINE = Path("evaluation/results/tax_roadmap_holdout250_after_logic_v2_0912.json")
OUTPUT = Path("evaluation/results/tax_legal14_stage_probe_after_targeted_search_0913.json")


def diagnose(state: dict[str, object], *, passed: bool) -> str:
    """Classify the earliest observable failure boundary for a Tax turn."""
    if passed:
        return "recovered"
    if state.get("route") != "tax":
        return "route_mismatch"
    trace = state.get("tax_retrieval_trace", [])
    if not isinstance(trace, list) or not trace:
        return "retrieval_not_run"
    if not any(hop.get("rerank") for hop in trace if isinstance(hop, dict)):
        return "retrieval_empty"
    if state.get("evidence_sufficient") is not True:
        return "evidence_insufficient"
    if not state.get("answer_sources"):
        return "final_citation"
    return "status_or_contract"


def expected_checks(turn: object, state: dict[str, object]) -> dict[str, bool]:
    """Score the checks used by legal-evidence holdout turns."""
    expected = turn.expected
    checks: dict[str, bool] = {}
    if expected.route is not None:
        checks["route"] = state.get("route") == expected.route
    if expected.status is not None:
        checks["status"] = state.get("answer_status") == expected.status
    if expected.should_block is not None:
        checks["block"] = (
            state.get("guardrail_reason") == "out_of_scope"
        ) == expected.should_block
    if expected.require_grounded is not None:
        checks["grounded"] = bool(state.get("answer_sources")) == expected.require_grounded
    return checks


async def main() -> None:
    """Replay target conversations and save search and evidence traces."""
    if OUTPUT.exists():
        raise SystemExit(f"Output already exists: {OUTPUT}")
    settings = get_settings()
    if settings.vector_store_backend != "postgres" or settings.retrieval_mode != "hybrid":
        raise SystemExit("This diagnostic requires the PostgreSQL hybrid index")

    scenarios = TypeAdapter(list[ConversationScenario]).validate_python(
        GRAPH_SCENARIOS_BY_SUITE["holdout250"]
    )
    scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    targets: dict[str, set[int]] = {}
    for scenario_result in baseline["scenarios"]:
        scenario_id = scenario_result["scenario_id"]
        scenario = scenario_by_id.get(scenario_id)
        if scenario is None or "legal_evidence" not in scenario.tags:
            continue
        failed_turns = {
            index
            for index, turn_result in enumerate(scenario_result["turns"])
            if not turn_result["passed"]
        }
        if failed_turns:
            targets[scenario_id] = failed_turns
    if sum(len(indices) for indices in targets.values()) != 14:
        raise SystemExit(f"Expected 14 failed turns, found {targets}")

    dense = PostgresVectorSearch(get_embedding_model(settings), settings)
    search = HybridSearch(
        dense_search=dense,
        chunks=dense.get_chunks(),
        dense_candidate_k=settings.hybrid_dense_candidate_k,
        bm25_candidate_k=settings.hybrid_bm25_candidate_k,
        rrf_k=settings.hybrid_rrf_k,
    )
    graph = build_graph(
        get_llm(settings),
        policy_search=search,
        tax_search=search,
        settings=settings,
    )
    profiles = {
        scenario_by_id[scenario_id].user_id: get_user_profile(
            scenario_by_id[scenario_id].user_id, settings
        )
        for scenario_id in targets
    }

    rows: list[dict[str, object]] = []
    setup_turns = 0
    for scenario_id, failed_turn_indices in targets.items():
        scenario = scenario_by_id[scenario_id]
        history: list[dict[str, str]] = []
        for turn_index, turn in enumerate(scenario.turns):
            if turn_index > max(failed_turn_indices):
                break
            state = await graph.ainvoke(
                {
                    "query": turn.question,
                    "category": scenario.category,
                    "policy_id": None,
                    "top_k": settings.default_top_k,
                    "decision": None,
                    "user_context": profiles[scenario.user_id],
                    "conversation_history": [item.copy() for item in history],
                    "roadmap_step": scenario.roadmap_step,
                }
            )
            answer = str(state.get("answer") or "")
            history.extend(
                (
                    {"role": "user", "content": turn.question},
                    {"role": "assistant", "content": answer},
                )
            )
            if turn_index not in failed_turn_indices:
                setup_turns += 1
                continue

            checks = expected_checks(turn, state)
            passed = bool(checks) and all(checks.values())
            diagnosis = diagnose(state, passed=passed)
            row = {
                "scenario_id": scenario_id,
                "turn": turn_index + 1,
                "question": turn.question,
                "expected": turn.expected.model_dump(mode="json"),
                "actual": {
                    "route": state.get("route"),
                    "status": state.get("answer_status"),
                    "grounded": bool(state.get("answer_sources")),
                    "guardrail_reason": state.get("guardrail_reason"),
                    "termination_reason": state.get("termination_reason"),
                    "evidence_sufficient": state.get("evidence_sufficient"),
                    "hop_count": state.get("hop_count"),
                    "search_history": state.get("search_history", []),
                    "source_chunk_ids": [
                        source.get("chunk_id")
                        for source in state.get("answer_sources", [])
                    ],
                },
                "checks": checks,
                "passed": passed,
                "diagnosis": diagnosis,
                "retrieval_trace": state.get("tax_retrieval_trace", []),
            }
            rows.append(row)
            print(
                f"{scenario_id} turn={turn_index + 1}: "
                f"diagnosis={diagnosis} status={state.get('answer_status')} "
                f"grounded={bool(state.get('answer_sources'))} "
                f"hops={state.get('hop_count')}",
                flush=True,
            )

    diagnosis_counts = Counter(str(row["diagnosis"]) for row in rows)
    result = {
        "suite": "holdout250_tax_legal_evidence_failed14",
        "note": "Replay of the fourteen legal-evidence turns that failed in the V2 report",
        "summary": {
            "target_turns": len(rows),
            "setup_turns_executed": setup_turns,
            "diagnosis_counts": dict(sorted(diagnosis_counts.items())),
            "recovered": diagnosis_counts.get("recovered", 0),
            "still_failed": len(rows) - diagnosis_counts.get("recovered", 0),
        },
        "turns": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY " + json.dumps(result["summary"], ensure_ascii=False), flush=True)
    print(f"Saved: {OUTPUT}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
