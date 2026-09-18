"""Probe legacy80 retrieval stages without calling the graph or the holdout suite.

This is a development-set diagnostic, not a reproduction of the router's query
choice or an end-to-end evaluation. It reads the existing DB index and requests
query embeddings; it never changes DB rows, model settings, or the holdout data.
"""

from collections import defaultdict
from statistics import mean

from evaluation.evaluation_cases import POLICY_CASES
from src.core.config import get_settings
from src.data.postgres_repository import get_user_profile
from src.models.factory import get_embedding_model
from src.rag.discovery import build_personalized_query
from src.vectorstores.hybrid import BM25Search, reciprocal_rank_fusion
from src.vectorstores.postgres import PostgresVectorSearch


def recall(results: list[dict], relevant: set[int]) -> float:
    found = {item["policy_id"] for item in results if item["policy_id"] is not None}
    return len(found & relevant) / len(relevant)


def summarize(values: list[float]) -> str:
    return f"R={mean(values):.3f}, hit={sum(value > 0 for value in values)}/{len(values)}"


def main() -> None:
    settings = get_settings()
    if settings.vector_store_backend != "postgres" or settings.retrieval_mode != "hybrid":
        raise SystemExit("This diagnostic requires the PostgreSQL hybrid index")
    dense_search = PostgresVectorSearch(get_embedding_model(settings), settings)
    bm25_search = BM25Search(dense_search.get_chunks())
    profiles = {user_id: get_user_profile(user_id, settings) for user_id in {case["user_id"] for case in POLICY_CASES}}

    for mode in ("raw", "personalized"):
        stage_scores: dict[str, list[float]] = defaultdict(list)
        stage_misses: dict[str, list[str]] = defaultdict(list)
        for case in POLICY_CASES:
            query = case["question"]
            if mode == "personalized":
                query = build_personalized_query(query, profiles[case["user_id"]])
            relevant = set(case["relevant_policy_ids"])
            dense = dense_search.search(query, top_k=40)
            bm25 = bm25_search.search(query, top_k=40)
            variants = {
                "dense20": dense[:20],
                "bm25_20": bm25[:20],
                "union20": dense[:20] + bm25[:20],
            }
            for dense_k, bm25_k in ((20, 20), (40, 20), (20, 40), (40, 40)):
                for rrf_k in (10, 30, 60, 100):
                    key = f"rrf20:d{dense_k}:b{bm25_k}:k{rrf_k}"
                    variants[key] = reciprocal_rank_fusion(
                        [dense[:dense_k], bm25[:bm25_k]], rrf_k=rrf_k, top_k=20,
                    )
            for stage, results in variants.items():
                value = recall(results, relevant)
                stage_scores[stage].append(value)
                if value < 1:
                    stage_misses[stage].append(case["case_id"])

        baseline = "rrf20:d20:b20:k60"
        print(f"\nMODE={mode}; legacy80 policy cases={len(POLICY_CASES)}")
        for key in ("dense20", "bm25_20", "union20", baseline):
            print(f"{key}: {summarize(stage_scores[key])}; incomplete={len(stage_misses[key])}")
        print("baseline incomplete IDs: " + ", ".join(stage_misses[baseline]))
        print("tuning variants (R@20 candidate-pool, not final R@5):")
        ordered = sorted(
            (key for key in stage_scores if key.startswith("rrf20:")),
            key=lambda key: (-mean(stage_scores[key]), key),
        )
        for key in ordered:
            print(f"{key}: {summarize(stage_scores[key])}")


if __name__ == "__main__":
    main()
