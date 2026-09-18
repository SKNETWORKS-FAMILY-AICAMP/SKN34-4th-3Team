"""Measure RRF-to-Rerank loss on the legacy80 policy development cases only.

The script reproduces retrieval stages for raw and profile-enriched questions.
It does not reproduce the graph router's per-question query choice or final
answer/source generation. Existing DB rows and holdout data are read-only.
"""

import json
from pathlib import Path

from evaluation.evaluation_cases import POLICY_CASES
from src.core.config import get_settings
from src.data.postgres_repository import get_user_profile
from src.models.factory import get_embedding_model
from src.rag.discovery import build_personalized_query
from src.rag.reranker import CohereRerankError, rerank_documents
from src.vectorstores.hybrid import HybridSearch
from src.vectorstores.postgres import PostgresVectorSearch


OUTPUT = Path("evaluation/results/dev_rerank_stage_probe_0912.json")


def policy_ids(results: list[dict]) -> list[int]:
    return [item["policy_id"] for item in results if item["policy_id"] is not None]


def summarize(rows: list[dict]) -> dict[str, object]:
    return {
        "cases": len(rows),
        "rrf_pool_gold": sum(row["rrf_pool_gold"] for row in rows),
        "rrf_top5_gold": sum(row["rrf_top5_gold"] for row in rows),
        "rerank_top5_gold": sum(row["rerank_top5_gold"] for row in rows),
        "rerank_lost_gold": [
            row["case_id"] for row in rows
            if row["rrf_pool_gold"] and not row["rerank_top5_gold"]
        ],
        "rerank_lost_vs_rrf_top5": [
            row["case_id"] for row in rows
            if row["rrf_top5_gold"] and not row["rerank_top5_gold"]
        ],
        "rerank_gained_vs_rrf_top5": [
            row["case_id"] for row in rows
            if not row["rrf_top5_gold"] and row["rerank_top5_gold"]
        ],
        "rerank_top5_duplicate_policy_cases": sum(
            row["rerank_top5_distinct_policies"] < len(row["rerank_top5_policy_ids"])
            for row in rows
        ),
        "mean_distinct_policies_in_rerank_top5": round(
            sum(row["rerank_top5_distinct_policies"] for row in rows) / len(rows), 3,
        ),
    }


def main() -> None:
    settings = get_settings()
    if settings.vector_store_backend != "postgres" or settings.retrieval_mode != "hybrid":
        raise SystemExit("This diagnostic requires the PostgreSQL hybrid index")
    if not settings.cohere_configured:
        raise SystemExit("Cohere Rerank is not configured")
    assert len(POLICY_CASES) == 20
    dense_search = PostgresVectorSearch(get_embedding_model(settings), settings)
    hybrid_search = HybridSearch(
        dense_search=dense_search,
        chunks=dense_search.get_chunks(),
        dense_candidate_k=settings.hybrid_dense_candidate_k,
        bm25_candidate_k=settings.hybrid_bm25_candidate_k,
        rrf_k=settings.hybrid_rrf_k,
    )
    profiles = {
        user_id: get_user_profile(user_id, settings)
        for user_id in {case["user_id"] for case in POLICY_CASES}
    }
    result: dict[str, object] = {
        "suite": "legacy80_policy_only",
        "note": "Stage-only diagnostic; actual Router query and final sources not observed",
        "settings": {
            "dense_candidate_k": settings.hybrid_dense_candidate_k,
            "bm25_candidate_k": settings.hybrid_bm25_candidate_k,
            "rrf_k": settings.hybrid_rrf_k,
            "rerank_candidate_k": settings.cohere_rerank_candidate_k,
            "top_n": settings.default_top_k,
            "rerank_model": settings.cohere_rerank_model,
        },
        "modes": {},
    }

    for mode in ("raw", "personalized"):
        rows: list[dict] = []
        for case in POLICY_CASES:
            query = case["question"]
            if mode == "personalized":
                query = build_personalized_query(query, profiles[case["user_id"]])
            _, _, rrf_results = hybrid_search.search_stages(
                query, top_k=settings.cohere_rerank_candidate_k,
            )
            rrf_policy_results = [item for item in rrf_results if item["policy_id"] is not None]
            try:
                reranked = rerank_documents(
                    query, rrf_policy_results,
                    top_n=settings.default_top_k, settings=settings,
                )
            except CohereRerankError as exc:
                raise RuntimeError(f"Rerank failed at {mode}/{case['case_id']}; no retry") from exc
            gold = set(case["relevant_policy_ids"])
            pool_ids = policy_ids(rrf_policy_results)
            rrf_top5_ids = policy_ids(rrf_policy_results[:settings.default_top_k])
            rerank_ids = policy_ids(reranked)
            rows.append({
                "case_id": case["case_id"],
                "gold_policy_ids": sorted(gold),
                "rrf_pool_gold": bool(gold & set(pool_ids)),
                "rrf_top5_gold": bool(gold & set(rrf_top5_ids)),
                "rerank_top5_gold": bool(gold & set(rerank_ids)),
                "rrf_policy_candidate_count": len(rrf_policy_results),
                "rrf_top5_policy_ids": rrf_top5_ids,
                "rerank_top5_policy_ids": rerank_ids,
                "rerank_top5_distinct_policies": len(set(rerank_ids)),
            })
        result["modes"][mode] = {"summary": summarize(rows), "cases": rows}
        print(mode, json.dumps(result["modes"][mode]["summary"], ensure_ascii=False))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
