"""Run the live policy graph, stopping before final answer generation."""

import argparse
import asyncio
from collections import Counter
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
from statistics import mean
from time import perf_counter
from zoneinfo import ZoneInfo

from src.core.config import get_settings
from src.core.database import connect_database
from src.evaluation.metrics import retrieval_metrics
from src.evaluation.run_evaluation import validate_holdout_database
from src.models.factory import get_embedding_model
from src.rag import graph as graph_module
from src.rag.guardrails import validate_question
from src.serving.rag_routes import RagRuntime, get_database_user_profile
from src.vectorstores.postgres import PostgresVectorSearch
from evaluation.holdout_cases_250 import HOLDOUT250_POLICY_CASES


async def run_before_answer(graph, graph_input):
    """Keep all preceding nodes; return the state and wall-clock node timings."""
    state, timings = {}, {}
    previous = perf_counter()
    async for mode, event in graph.astream(
        graph_input, stream_mode=["updates", "values"], interrupt_before=["answer"],
    ):
        if mode == "values":
            state = event
        elif mode == "updates":
            for node in event:
                if node.startswith("__"):
                    continue
                now = perf_counter()
                timings[node] = (now - previous) * 1000
                previous = now
    if "answer" in timings:
        raise RuntimeError("Final answer node unexpectedly executed")
    return state, timings


class ErrorCounter(logging.Handler):
    def __init__(self):
        super().__init__()
        self.counts = Counter()

    def emit(self, record):
        message = record.getMessage().lower()
        if record.levelno >= logging.ERROR:
            self.counts["error_logs"] += 1
        for name, token in {
            "cohere_fallback": "cohere rerank failed",
            "elasticsearch_disabled": "elasticsearch index is out of sync",
        }.items():
            if token in message:
                self.counts[name] += 1


def stage_ids(state, key):
    return [int(d["policy_id"]) for d in state.get(key, []) if d.get("policy_id") is not None]


def summarize(rows):
    metrics = [retrieval_metrics(r["top5"], set(r["gold"]), 5) for r in rows]
    return {
        "evaluated_cases": len(rows), "hit_at_5_count": sum(bool(set(r["top5"]) & set(r["gold"])) for r in rows),
        "hit_at_5": mean(bool(set(r["top5"]) & set(r["gold"])) for r in rows),
        "precision_at_5": mean(m.precision_at_k for m in metrics),
        "recall_at_5": mean(m.recall_at_k for m in metrics),
        "mrr": mean(m.reciprocal_rank for m in metrics),
        "map_at_5": mean(m.average_precision for m in metrics),
        "average_latency_ms": mean(r["latency_ms"] for r in rows),
        "average_router_ms": mean(r["node_timings_ms"].get("router", 0) for r in rows),
        "average_policy_search_rrf_ms": mean(max(0, r["node_timings_ms"].get("policy_node", 0) - r["cohere_ms"]) for r in rows),
        "average_cohere_ms": mean(r["cohere_ms"] for r in rows),
        "routes": dict(Counter(r["route"] for r in rows)),
        "personalized_cases": sum(r["personalized"] for r in rows),
        "stage_hits": {key: sum(bool(set(r[key]) & set(r["gold"])) for r in rows)
                       for key in ["dense", "bm25", "rrf", "rerank", "top5"]},
    }


def markdown(report, prefix):
    s = report["summary"]
    settings = report["settings"]
    lines = ["# 정책 63문항 — 최종 답변 생성 직전 검색 평가", "",
             "기존 라우팅·개인화·Dense/Elasticsearch·RRF·Cohere를 실행하고 `answer` 노드 직전에 중단했습니다.",
             "최종 답변과 인용 선택은 생성하지 않았습니다. Top-5 정책 목록을 정답 정책 ID와 비교했습니다.", "",
             f"실행: {report['started_at_kst']} ~ {report['finished_at_kst']} (한국시간).", "",
             "Elasticsearch 검색은 기존 Nori 분석 및 BM25 설정을 그대로 사용했습니다. "
             f"RRF/Cohere 후보 {settings['cohere_rerank_candidate_k']}개, "
             f"검색 pool {settings['nori_retrieval_pool_k']}개를 사용했습니다.", "",
             "| 지표 | 결과 |", "| --- | ---: |",
             f"| Hit@5 | {s['hit_at_5_count']}/63 ({s['hit_at_5']:.1%}) |",
             f"| Precision@5 | {s['precision_at_5']:.1%} |",
             f"| Recall@5 | {s['recall_at_5']:.1%} |",
             f"| MRR | {s['mrr']:.3f} |", f"| MAP@5 | {s['map_at_5']:.3f} |",
             f"| 평균 응답 생성 전 처리 시간 | {s['average_latency_ms']/1000:.2f}초 |",
             f"| Router 평균 시간 | {s['average_router_ms']/1000:.2f}초 |",
             f"| 정책 검색·RRF 평균 시간 | {s['average_policy_search_rrf_ms']/1000:.2f}초 |",
             f"| Cohere 평균 시간 | {s['average_cohere_ms']/1000:.2f}초 |", "",
             "요청 간 대기 시간은 처리 시간에서 제외했습니다. 검색·RRF 시간은 정책 노드의 벽시계 시간에서 Cohere 시간을 뺀 값으로 병렬 검색과 결합·문맥 준비를 포함합니다. 같은 백엔드의 여러 검색어에서 등장한 정책은 가장 높은 순위의 RRF 기여도만 반영합니다.", "",
             "## 단계별 정답 포함", "", "| 단계 | 정답 포함 문항 |", "| --- | ---: |"]
    for key, label in [("dense", "Dense 후보 병합"), ("bm25", "Elasticsearch 후보 병합"),
                       ("rrf", "RRF 20개"), ("rerank", "Cohere 정렬 20개"), ("top5", "답변 입력 Top-5")]:
        lines.append(f"| {label} | {s['stage_hits'][key]}/63 |")
    lines += ["", "원시 후보는 검색어별 결과를 병합한 목록이며, 최종 Hit@5와 후보 수가 다릅니다.", "",
              f"라우트: `{s['routes']}`. 개인화: {s['personalized_cases']}/63.",
              f"최종 답변 생성 호출: {report['final_answer_calls']}회. 오류·fallback: `{report['errors']}`.", "",
              "이번 결과는 검색 단계 지표입니다. 기존 보고서의 최종 인용 Hit@5와 평가 대상이 다르므로 직접적인 개선 폭으로 해석하지 않습니다.", "",
              "## Top-5 미적중 문항", "", "| case ID | 정답 | Top-5 |", "| --- | --- | --- |"]
    for r in report["cases"]:
        if not set(r["top5"]) & set(r["gold"]):
            lines.append(f"| {r['case_id']} | {r['gold']} | {r['top5']} |")
    lines += ["", f"[설정·원본 결과 JSON]({prefix.name}.json)", ""]
    return "\n".join(lines)


async def main(resume_prefix: Path | None = None):
    request_interval_seconds = 8.5
    settings = get_settings()
    if "default_transaction_read_only=on" not in os.environ.get("PGOPTIONS", ""):
        raise RuntimeError("Require PGOPTIONS='-c default_transaction_read_only=on'")
    assert settings.cohere_rerank_candidate_k == 20 and settings.nori_retrieval_pool_k == 40
    assert not settings.tax_cache_enabled
    with connect_database(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SHOW default_transaction_read_only")
            assert cursor.fetchone()[0] == "on"
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d_%H%M%S")
    prefix = resume_prefix or Path("evaluation/results") / f"policy63_pre_answer_{stamp}"
    prefix.parent.mkdir(parents=True, exist_ok=True)
    errors = ErrorCounter()
    log = logging.FileHandler(str(prefix) + "_server.log", encoding="utf-8")
    log.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().addHandler(errors)
    logging.getLogger().addHandler(log)
    logging.getLogger().setLevel(logging.INFO)
    runtime = RagRuntime()
    runtime.set_index(PostgresVectorSearch(get_embedding_model(settings), settings),
                      document_count=14550, chunk_count=18481, index_source="cache")
    assert runtime.require_hybrid_index(settings).bm25_search.ready()
    graph = runtime.require_graph(settings, runtime.notice_search)
    expected_settings = {k: getattr(settings, k) for k in ["llm_model", "embedding_model", "cohere_rerank_model",
                         "cohere_rerank_candidate_k", "nori_retrieval_pool_k", "hybrid_rrf_k", "tax_cache_enabled"]}
    if resume_prefix is not None:
        report = json.loads(Path(str(prefix) + ".json").read_text(encoding="utf-8"))
        assert report["status"] == "aborted" and len(report["cases"]) < len(HOLDOUT250_POLICY_CASES)
        assert report["settings"] == expected_settings
        assert report["dataset_sha256"] == hashlib.sha256(Path("evaluation/holdout_cases_250.py").read_bytes()).hexdigest()
        assert report["database"] == validate_holdout_database(settings=settings)
        report["status"] = "running"
        report["errors"] = {}
        report.pop("finished_at_kst", None)
        report["resumed_at_kst"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    else:
        report = {
        "started_at_kst": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "status": "running", "cutoff": "interrupt_before=['answer']", "db_read_only": True,
        "request_interval_seconds": request_interval_seconds,
        "database": validate_holdout_database(settings=settings),
        "dataset_sha256": hashlib.sha256(Path("evaluation/holdout_cases_250.py").read_bytes()).hexdigest(),
        "policy_query_normalizer_sha256": hashlib.sha256(Path("src/rag/discovery.py").read_bytes()).hexdigest(),
        "policy_rrf_mode": "best_rank_per_backend",
        "policy_graph_sha256": hashlib.sha256(Path("src/rag/graph.py").read_bytes()).hexdigest(),
        "source_level_rrf_sha256": hashlib.sha256(Path("src/vectorstores/nori_hybrid.py").read_bytes()).hexdigest(),
        "settings": {k: getattr(settings, k) for k in ["llm_model", "embedding_model", "cohere_rerank_model",
                     "cohere_rerank_candidate_k", "nori_retrieval_pool_k", "hybrid_rrf_k", "tax_cache_enabled"]},
        "cases": [], "final_answer_calls": 0, "errors": {},
        }
    original_rerank = graph_module.rerank_documents
    rerank_times = []

    def observed_rerank(*args, **kwargs):
        started = perf_counter()
        try:
            return original_rerank(*args, **kwargs)
        finally:
            rerank_times.append((perf_counter() - started) * 1000)

    async def forbidden_final_answer(*args, **kwargs):
        report["final_answer_calls"] += 1
        raise RuntimeError("Final answer generation must not run")

    graph_module.rerank_documents = observed_rerank
    graph_module.generate_unified_answer = forbidden_final_answer
    previous_request = 0.0

    def save():
        Path(str(prefix) + ".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("RUN_STAMP", stamp, flush=True)
    save()
    try:
        assert len(HOLDOUT250_POLICY_CASES) == 63
        for case in HOLDOUT250_POLICY_CASES[len(report["cases"]):]:
            await asyncio.sleep(max(0, request_interval_seconds - (perf_counter() - previous_request)))
            context = get_database_user_profile(case["user_id"], settings)
            graph_input = {"query": validate_question(case["question"], max_length=settings.max_question_length),
                           "category": None, "policy_id": None, "top_k": 5, "decision": None,
                           "user_context": context, "conversation_history": [], "roadmap_step": None,
                           "backend_notice_results": None}
            rerank_times.clear()
            previous_request = started = perf_counter()
            state, timings = await run_before_answer(graph, graph_input)
            elapsed = (perf_counter() - started) * 1000
            if errors.counts or report["final_answer_calls"]:
                raise RuntimeError("Evaluation stopped on exception/fallback or final-answer execution")
            if state.get("answer"):
                raise RuntimeError("Answer unexpectedly generated before cutoff")
            row = {"case_id": case["case_id"], "question": case["question"], "gold": case["relevant_policy_ids"],
                   "route": state.get("route"), "personalized": bool(state.get("personalized")),
                   "search_query": state.get("search_query"), "personalized_search_query": state.get("personalized_search_query"),
                   "policy_search_queries": state.get("policy_search_queries", []),
                   "evidence_sufficient": state.get("evidence_sufficient"), "termination_reason": state.get("termination_reason"),
                   "node_timings_ms": timings, "latency_ms": elapsed, "cohere_ms": sum(rerank_times)}
            for key, field in [("dense", "dense_docs"), ("bm25", "bm25_docs"), ("rrf", "retrieved_docs"),
                               ("rerank", "policy_ranked_candidates"), ("top5", "reranked_docs")]:
                row[key] = stage_ids(state, field)
            assert len(row["rrf"]) <= 20 and len(row["top5"]) <= 5
            report["cases"].append(row)
            save()
            print("PROGRESS", len(report["cases"]), "/63", case["case_id"], "hit", bool(set(row["top5"]) & set(row["gold"])), flush=True)
        report["summary"] = summarize(report["cases"])
        report["status"] = "complete"
        report["finished_at_kst"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
        save()
        Path(str(prefix) + ".md").write_text(markdown(report, prefix), encoding="utf-8")
        print("COMPLETE", json.dumps(report["summary"]), flush=True)
    except Exception:
        report["status"] = "aborted"
        report["errors"] = dict(errors.counts)
        save()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-prefix", type=Path)
    asyncio.run(main(parser.parse_args().resume_prefix))
