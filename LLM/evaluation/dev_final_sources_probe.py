"""Trace legacy80 policy cases through one Graph request to final sources.

This diagnostic runs the existing Graph without changing its implementation or
configuration. It does not evaluate or modify holdout250.
"""

import asyncio
import json
from pathlib import Path

from evaluation.evaluation_cases import POLICY_CASES
from src.core.config import get_settings
from src.data.postgres_repository import get_user_profile
from src.models.factory import get_embedding_model, get_llm
from src.rag.graph import build_graph
from src.vectorstores.hybrid import HybridSearch
from src.vectorstores.postgres import PostgresVectorSearch


OUTPUT = Path("evaluation/results/dev_final_sources_probe_0912.json")


def policy_ids(documents: list[dict]) -> list[int]:
    return [int(item["policy_id"]) for item in documents if item.get("policy_id") is not None]


async def main() -> None:
    settings = get_settings()
    if settings.vector_store_backend != "postgres" or settings.retrieval_mode != "hybrid":
        raise SystemExit("This diagnostic requires the PostgreSQL hybrid index")
    if len(POLICY_CASES) != 20:
        raise SystemExit("Expected exactly 20 legacy80 policy cases")
    dense = PostgresVectorSearch(get_embedding_model(settings), settings)
    search = HybridSearch(
        dense_search=dense,
        chunks=dense.get_chunks(),
        dense_candidate_k=settings.hybrid_dense_candidate_k,
        bm25_candidate_k=settings.hybrid_bm25_candidate_k,
        rrf_k=settings.hybrid_rrf_k,
    )
    graph = build_graph(
        get_llm(settings), policy_search=search, tax_search=search, settings=settings,
    )
    profiles = {
        user_id: get_user_profile(user_id, settings)
        for user_id in {case["user_id"] for case in POLICY_CASES}
    }

    rows: list[dict] = []
    for case in POLICY_CASES:
        state = await graph.ainvoke({
            "query": case["question"],
            "category": None,
            "policy_id": None,
            "top_k": settings.default_top_k,
            "decision": None,
            "user_context": profiles[case["user_id"]],
            "conversation_history": [],
            "roadmap_step": None,
        })
        gold = set(case["relevant_policy_ids"])
        rrf_ids = policy_ids(state.get("retrieved_docs", []))
        rerank_ids = policy_ids(state.get("reranked_docs", []))
        source_ids = policy_ids(state.get("answer_sources", []))
        row = {
            "case_id": case["case_id"],
            "gold_policy_ids": sorted(gold),
            "route": state.get("route"),
            "personalized": state.get("personalized"),
            "search_query": state.get("search_query"),
            "answer_status": state.get("answer_status"),
            "termination_reason": state.get("termination_reason"),
            "guardrail_reason": state.get("guardrail_reason"),
            "rrf_policy_ids": rrf_ids,
            "rerank_policy_ids": rerank_ids,
            "final_source_policy_ids": source_ids,
            "rrf_gold": bool(gold & set(rrf_ids)),
            "rerank_gold": bool(gold & set(rerank_ids)),
            "final_source_gold": bool(gold & set(source_ids)),
            "cited_source_numbers": state.get("cited_source_numbers", []),
        }
        rows.append(row)
        print(
            f"{case['case_id']}: route={row['route']} personalized={row['personalized']} "
            f"rrf={row['rrf_gold']} rerank={row['rerank_gold']} "
            f"final={row['final_source_gold']} status={row['answer_status']}",
            flush=True,
        )

    summary = {
        "cases": len(rows),
        "policy_route": sum(row["route"] == "policy" for row in rows),
        "personalized": sum(row["personalized"] is True for row in rows),
        "rrf_gold": sum(row["rrf_gold"] for row in rows),
        "rerank_gold": sum(row["rerank_gold"] for row in rows),
        "final_source_gold": sum(row["final_source_gold"] for row in rows),
        "lost_between_rerank_and_final": [
            row["case_id"] for row in rows
            if row["rerank_gold"] and not row["final_source_gold"]
        ],
    }
    result = {
        "suite": "legacy80_policy_only",
        "note": "New single-pass Graph diagnostic; not the historical legacy80 run",
        "summary": summary,
        "cases": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, ensure_ascii=False))
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
