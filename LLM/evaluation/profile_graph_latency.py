"""Measure node wall time for representative policy and tax questions.

Run with the existing PostgreSQL index and configured model APIs. This sends
the selected evaluation questions and retrieved evidence to model providers.
"""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from evaluation.evaluation_cases import (
    GRAPH_SCENARIOS_BY_SUITE,
    POLICY_CASES_BY_SUITE,
)
from src.core.config import get_settings
from src.data.postgres_repository import get_user_profile
from src.models.factory import get_embedding_model, get_llm
from src.evaluation.graph_evaluator import AnswerExpectation, AnswerObservation, score_answer
from src.rag.graph import build_graph
from src.vectorstores.hybrid import HybridSearch
from src.vectorstores.postgres import PostgresVectorSearch


SAMPLES = (
    ("policy", "holdout-policy-techbiz-clinic"),
    ("tax", "holdout-tax-business-transfer"),
    ("tax", "holdout-tax-bookkeeping-penalty"),
    ("tax", "holdout-tax-general-vat-adjustments"),
    ("tax", "holdout-tax-missing-family"),
    ("tax", "holdout-tax-future-2027"),
)
OUTPUT = Path("evaluation/results/graph_latency_profile_0913.json")


async def main(selected: set[str], output: Path) -> None:
    if output.exists():
        raise SystemExit(f"Output already exists: {output}")
    settings = get_settings()
    dense = PostgresVectorSearch(get_embedding_model(settings), settings)
    search = HybridSearch(
        dense_search=dense,
        chunks=dense.get_chunks(),
        dense_candidate_k=settings.hybrid_dense_candidate_k,
        bm25_candidate_k=settings.hybrid_bm25_candidate_k,
        rrf_k=settings.hybrid_rrf_k,
    )
    graph = build_graph(
        get_llm(settings), policy_search=search, tax_search=search,
        settings=settings,
    )
    rows = []
    for kind, sample_id in SAMPLES:
        if sample_id not in selected:
            continue
        if kind == "policy":
            case = next(
                case for case in POLICY_CASES_BY_SUITE["holdout250"]
                if case["case_id"] == sample_id
            )
            state = {
                "query": case["question"], "top_k": 5,
                "user_context": get_user_profile(case["user_id"], settings),
            }
        else:
            scenario = next(
                scenario for scenario in GRAPH_SCENARIOS_BY_SUITE["holdout250"]
                if scenario["scenario_id"] == sample_id
            )
            state = {
                "query": scenario["turns"][0]["question"],
                "category": "tax", "top_k": 5,
                "user_context": get_user_profile(scenario["user_id"], settings),
                "conversation_history": [],
            }
        started = perf_counter()
        previous = started
        nodes = []
        final_state = dict(state)
        print(f"START {sample_id}", flush=True)
        async for update in graph.astream(state, stream_mode="updates"):
            now = perf_counter()
            for node_name, node_update in update.items():
                elapsed_ms = round((now - previous) * 1000, 1)
                nodes.append({"node": node_name, "elapsed_ms": elapsed_ms})
                if isinstance(node_update, dict):
                    final_state.update(node_update)
                print(f"  {node_name}: {elapsed_ms} ms", flush=True)
            previous = now
        total_ms = round((perf_counter() - started) * 1000, 1)
        result = {"sample_id": sample_id, "total_ms": total_ms, "nodes": nodes}
        if kind == "tax":
            expected = AnswerExpectation.model_validate(scenario["turns"][0]["expected"])
            observed = AnswerObservation(
                route=final_state["route"], status=final_state["answer_status"],
                answer=final_state["answer"],
                grounded=bool(final_state.get("answer_sources")),
                guardrail_reason=final_state.get("guardrail_reason"),
                latency_ms=total_ms,
            )
            score = score_answer(expected, observed)
            result.update({"status": observed.status, "passed": score.passed,
                           "checks": score.checks, "hop_count": final_state.get("hop_count", 0)})
        rows.append(result)
        print(f"TOTAL {sample_id}: {total_ms} ms", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="append", choices=[item[1] for item in SAMPLES])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    asyncio.run(main(set(args.sample or [item[1] for item in SAMPLES]), args.output))
