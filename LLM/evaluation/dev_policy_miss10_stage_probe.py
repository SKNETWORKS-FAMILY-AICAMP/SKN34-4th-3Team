"""Trace the ten remaining holdout policy misses through every retrieval stage."""

import asyncio
import json
from collections import Counter
from pathlib import Path

from evaluation.evaluation_cases import POLICY_CASES_BY_SUITE
from src.core.config import get_settings
from src.data.postgres_repository import get_user_profile
from src.models.factory import get_embedding_model, get_llm
from src.rag.graph import build_graph
from src.vectorstores.hybrid import HybridSearch
from src.vectorstores.postgres import PostgresVectorSearch


OUTPUT = Path("evaluation/results/policy_miss10_stage_probe_after_dedup_0913.json")
TARGET_IDS = {
    "holdout-policy-seoul-tech-consulting",
    "holdout-policy-seoul-success-school",
    "holdout-policy-workplace-improvement",
    "holdout-policy-small-business-special-guarantee",
    "holdout-policy-gyeonggi-business-card",
    "holdout-policy-food-export-expo",
    "holdout-policy-restaurant-facility-loan",
    "holdout-policy-small-export-shipping",
    "holdout-policy-small-business-fund",
    "holdout-policy-social-economy-fund",
}


def policy_ids(documents: list[dict]) -> list[int]:
    """Return policy IDs in rank order, retaining duplicate chunks."""
    return [
        int(document["policy_id"])
        for document in documents
        if document.get("policy_id") is not None
    ]


def gold_ranks(ids: list[int], gold: set[int]) -> list[int]:
    """Return one-based ranks occupied by relevant policies."""
    return [index for index, policy_id in enumerate(ids, start=1) if policy_id in gold]


def first_loss_stage(
    stages: dict[str, list[int]],
    gold: set[int],
    *,
    route: object,
) -> str:
    """Identify the first stage after which no relevant policy remains."""
    if route != "policy":
        return "route_mismatch"
    if gold & set(stages["final_sources"]):
        return "recovered"
    if gold & set(stages["unique_top5"]):
        return "final_citation"
    if gold & set(stages["rerank20"]):
        return "unique_top5"
    if gold & set(stages["rrf20"]):
        return "rerank20"
    if gold & (
        set(stages["dense_candidates"]) | set(stages["bm25_candidates"])
    ):
        return "rrf20"
    return "dense_bm25"


async def main() -> None:
    """Run the current Graph once per target case and save stage observations."""
    settings = get_settings()
    if settings.vector_store_backend != "postgres" or settings.retrieval_mode != "hybrid":
        raise SystemExit("This diagnostic requires the PostgreSQL hybrid index")

    cases = [
        case
        for case in POLICY_CASES_BY_SUITE["holdout250"]
        if case["case_id"] in TARGET_IDS
    ]
    if len(cases) != len(TARGET_IDS):
        found = {case["case_id"] for case in cases}
        raise SystemExit(f"Missing target cases: {sorted(TARGET_IDS - found)}")

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
        user_id: get_user_profile(user_id, settings)
        for user_id in {int(case["user_id"]) for case in cases}
    }

    rows: list[dict[str, object]] = []
    for case in cases:
        state = await graph.ainvoke(
            {
                "query": case["question"],
                "category": None,
                "policy_id": None,
                "top_k": settings.default_top_k,
                "decision": None,
                "user_context": profiles[int(case["user_id"])],
                "conversation_history": [],
                "roadmap_step": None,
            }
        )
        gold = {int(policy_id) for policy_id in case["relevant_policy_ids"]}
        stages = {
            "dense_candidates": policy_ids(state.get("dense_docs", [])),
            "bm25_candidates": policy_ids(state.get("bm25_docs", [])),
            "rrf20": policy_ids(state.get("retrieved_docs", [])),
            "rerank20": policy_ids(state.get("policy_ranked_candidates", [])),
            "unique_top5": policy_ids(state.get("reranked_docs", [])),
            "supporting_chunks": policy_ids(state.get("policy_supporting_docs", [])),
            "final_sources": policy_ids(state.get("answer_sources", [])),
        }
        loss_stage = first_loss_stage(stages, gold, route=state.get("route"))
        row = {
            "case_id": case["case_id"],
            "user_id": case["user_id"],
            "question": case["question"],
            "gold_policy_ids": sorted(gold),
            "route": state.get("route"),
            "personalized": state.get("personalized"),
            "search_query": state.get("search_query"),
            "personalized_search_query": state.get("personalized_search_query"),
            "answer_status": state.get("answer_status"),
            "termination_reason": state.get("termination_reason"),
            "guardrail_reason": state.get("guardrail_reason"),
            "first_loss_stage": loss_stage,
            "stages": stages,
            "gold_ranks": {
                stage: gold_ranks(ids, gold)
                for stage, ids in stages.items()
            },
        }
        rows.append(row)
        print(
            f"{case['case_id']}: loss={loss_stage} "
            f"dense={row['gold_ranks']['dense_candidates']} "
            f"bm25={row['gold_ranks']['bm25_candidates']} "
            f"rrf={row['gold_ranks']['rrf20']} "
            f"rerank={row['gold_ranks']['rerank20']} "
            f"top5={row['gold_ranks']['unique_top5']} "
            f"final={row['gold_ranks']['final_sources']}",
            flush=True,
        )

    loss_counts = Counter(str(row["first_loss_stage"]) for row in rows)
    result = {
        "suite": "holdout250_policy_remaining_miss10",
        "note": "Current Graph stage trace after personalization and policy-ID deduplication",
        "summary": {
            "cases": len(rows),
            "first_loss_counts": dict(sorted(loss_counts.items())),
            "recovered": loss_counts.get("recovered", 0),
            "still_missed": len(rows) - loss_counts.get("recovered", 0),
        },
        "cases": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY " + json.dumps(result["summary"], ensure_ascii=False), flush=True)
    print(f"Saved: {OUTPUT}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
