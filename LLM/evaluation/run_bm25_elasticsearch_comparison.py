"""Compare lexical backends through isolated instances of the existing Django API.

Run in an isolated Docker process with PGOPTIONS enforcing read-only transactions.
No HTTP listener, production runtime replacement, indexing or environment edit occurs.
Both arms run all 250 units with the same source corpus and source-level RRF.
"""

import argparse
import asyncio
from collections import Counter
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

from elasticsearch import Elasticsearch, helpers
from httpx import ASGITransport, AsyncClient

from src.core.config import get_settings
from src.core.database import connect_database
from src.evaluation.evaluator import EvaluationObservation, evaluate_cases
from src.evaluation.graph_evaluator import AnswerObservation, evaluate_scenarios
from src.evaluation.run_evaluation import (
    DEFAULT_DATASET, HttpChatClient, HttpLangGraphClient,
    load_evaluation_cases, validate_holdout_database, validate_users,
)
from src.features.elasticsearch_indexing import load_elasticsearch_source_documents
from src.models.factory import get_embedding_model
from src.serving.django_config.asgi import _django_application
from src.serving import django_views
from src.serving.rag_routes import RagRuntime
from src.vectorstores.elasticsearch import ElasticsearchBM25Search
from src.vectorstores.hybrid import BM25Search
from src.vectorstores.nori_hybrid import NoriHybridSearch
from src.vectorstores.postgres import PostgresVectorSearch


ROOT = Path("evaluation/results")
NOW = lambda: datetime.now(ZoneInfo("Asia/Seoul")).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    default=str).encode()).hexdigest()


class SourceBM25(BM25Search):
    """Reuse the existing scorer; tax corpus already has one record per source."""

    def __init__(self, chunks):
        super().__init__(chunks)
        self.calls = 0

    def search(self, query, *, unique_source_ids=False, **options):
        self.calls += 1
        if unique_source_ids:
            source_types = options.get("source_types")
            if not source_types or len(source_types) != 1:
                raise ValueError("unique sources require one source type")
        return super().search(query, **options)


class ObservedElasticsearch(ElasticsearchBM25Search):
    def __init__(self, settings):
        super().__init__(settings)
        self.calls = 0

    def search(self, *args, **kwargs):
        self.calls += 1
        return super().search(*args, **kwargs)


class ObservedGraph:
    def __init__(self, graph, runtime):
        self.graph, self.runtime = graph, runtime

    async def ainvoke(self, *args, **kwargs):
        state = await self.graph.ainvoke(*args, **kwargs)
        self.runtime.last_state = state
        return state


class IsolatedRuntime(RagRuntime):
    def __init__(self, dense, lexical, settings, counts):
        super().__init__()
        self.set_index(dense, document_count=counts[0], chunk_count=counts[1],
                       index_source="cache")
        self.controlled_search = NoriHybridSearch(
            dense_search=dense, bm25_search=lexical,
            retrieval_pool_k=settings.nori_retrieval_pool_k,
            rerank_candidate_k=settings.cohere_rerank_candidate_k,
            rrf_k=settings.hybrid_rrf_k,
        )
        self.last_state = {}
        self.observed_graph = None

    def require_hybrid_index(self, settings):
        return self.controlled_search

    def require_graph(self, settings, notice_search):
        graph = super().require_graph(settings, notice_search)
        if self.observed_graph is None or self.observed_graph.graph is not graph:
            self.observed_graph = ObservedGraph(graph, self)
        return self.observed_graph


class ErrorCounter(logging.Handler):
    def __init__(self):
        super().__init__()
        self.counts = Counter()

    def emit(self, record):
        message = record.getMessage()
        if record.exc_info and isinstance(record.exc_info[1], ValueError) and str(record.exc_info[1]) == "Tax intent calculation_required/type mismatch":
            self.counts["tax_intent_invalid_output"] += 1
            return
        if record.levelno >= logging.ERROR:
            self.counts["error_logs"] += 1
        for name, token in {
            "cohere_fallback": "Cohere rerank failed",
            "retrieval_error": "retrieval failed",
            "elasticsearch_error": "Elasticsearch BM25 search failed",
            "generation_error": "Unified answer generation failed",
        }.items():
            if token in message:
                self.counts[name] += 1
        if record.exc_info and "status_code: 429" in logging.Formatter().formatException(record.exc_info):
            self.counts["rate_limit_429"] += 1


class Limiter:
    def __init__(self):
        self.last = 0.0

    async def wait(self):
        await asyncio.sleep(max(0, 6.1 - (monotonic() - self.last)))
        self.last = monotonic()


def write_report(prefix, metadata):
    """Render the completed comparison, including unfavorable results."""
    def read_from(base, arm, kind):
        return json.loads(Path(str(base) + f"_{arm}_{kind}.json").read_text(encoding="utf-8"))

    def read(arm, kind):
        return read_from(prefix, arm, kind)

    def pct(value):
        return f"{value * 100:.1f}%"

    def hit(case):
        return bool(set(case["relevant_policy_ids"]) & set(case["predicted_policy_ids"][:5]))

    def graph_stats(rows):
        turns = [t for row in rows for t in row["turns"]]
        return (sum(t["passed"] for t in turns), len(turns),
                sum(row["passed"] for row in rows), len(rows),
                sum(t["latency_ms"] for t in turns) / len(turns) / 1000)

    arms = ("basic_bm25", "elasticsearch")
    policies = [read(arm, "policy") for arm in arms]
    graphs = [read(arm, "graph") for arm in arms]
    traces = [read(arm, "stages") for arm in arms]
    previous_prefix = None
    previous_metadata = None
    previous_guardrail = None
    if metadata.get("policy_tax_only"):
        previous_prefix = Path(metadata["reuse_previous_prefix"])
        previous_metadata = json.loads(
            Path(str(previous_prefix) + "_validation.json").read_text(encoding="utf-8")
        )
        previous_policies = [read_from(previous_prefix, arm, "policy") for arm in arms]
        previous_graphs = [read_from(previous_prefix, arm, "graph") for arm in arms]
        previous_guardrail = [report["summary"]["guardrail"] for report in previous_policies]
        for index, graph in enumerate(graphs):
            graph["scenarios"].extend(
                scenario
                for scenario in previous_graphs[index]["scenarios"]
                if "roadmap" in scenario["tags"]
            )
    cases = [{c["case_id"]: c for c in p["cases"] if not c["should_block"]} for p in policies]
    assert cases[0].keys() == cases[1].keys() and len(cases[0]) == 63
    gains = [k for k in cases[0] if not hit(cases[0][k]) and hit(cases[1][k])]
    losses = [k for k in cases[0] if hit(cases[0][k]) and not hit(cases[1][k])]
    hits = [sum(hit(c) for c in arm.values()) for arm in cases]
    candidate_k = metadata["settings"]["cohere_rerank_candidate_k"]
    pool_k = metadata["settings"]["nori_retrieval_pool_k"]
    tax_totals = [graph_stats([r for r in g["scenarios"] if "tax" in r["tags"]]) for g in graphs]
    roadmap_totals = [graph_stats([r for r in g["scenarios"] if "roadmap" in r["tags"]]) for g in graphs]
    guardrail_metrics = previous_guardrail or [
        report["summary"]["guardrail"] for report in policies
    ]
    guardrail_false_positives = [metric["false_positive"] for metric in guardrail_metrics]
    lines = ["# 기본 BM25 대비 Elasticsearch Nori BM25 고도화 비교", "",
             f"평가 시작: {metadata['started_at_kst']} · 종료: {metadata['finished_at_kst']} (한국시간).", "",
             "## 정책·세금 재평가 및 이전 결과 비교표" if metadata.get("policy_tax_only") else "## 전체 250개 평가 비교표", "",
             "| 평가 영역 | 기본 BM25 | Elasticsearch Nori BM25 | 변화 |",
             "| --- | ---: | ---: | ---: |",
             f"| 정책 최종 인용 Hit@5 | {hits[0]}/63 ({pct(hits[0]/63)}) | {hits[1]}/63 ({pct(hits[1]/63)}) | {hits[1]-hits[0]:+d}건 |",
             f"| 정책 질문 오차단 | {guardrail_false_positives[0]}/63 | {guardrail_false_positives[1]}/63 | {guardrail_false_positives[1]-guardrail_false_positives[0]:+d}건 |",
             f"| 세금 자동 검사 턴 통과 | {tax_totals[0][0]}/{tax_totals[0][1]} | {tax_totals[1][0]}/{tax_totals[1][1]} | {tax_totals[1][0]-tax_totals[0][0]:+d}건 |",
             f"| 로드맵 자동 검사 턴 통과 | {roadmap_totals[0][0]}/{roadmap_totals[0][1]} | {roadmap_totals[1][0]}/{roadmap_totals[1][1]} | {roadmap_totals[1][0]-roadmap_totals[0][0]:+d}건 |",
             "", "서로 다른 자동 검사 기준의 영역을 합산해 하나의 전체 정확도로 계산하지 않았습니다.", "",
             "## 평가 범위와 비교 조건", "",
             (
                 "이번 실행에서 정책 검색·응답 63문항과 세금 31개 시나리오·62턴을 다시 평가했습니다. "
                 "가드레일과 로드맵은 이전 전체 비교 보고서의 결과를 사용합니다. 이 두 영역의 값은 이번 코드 변경을 반영한 재평가 결과가 아닙니다."
                 if metadata.get("policy_tax_only")
                 else "각 방식에서 신규 holdout250의 전체 250개 평가 단위를 실행했습니다. 정책 검색·응답 63문항과 "
                 "같은 63문항의 가드레일 판정, 세금 62턴, 로드맵 62턴입니다."
             ) + " 사용자 ID 1·2·4의 실제 DB 프로필을 사용했습니다.", "",
             "기본 방식은 저장소의 BM25Search(어절·문자 2-gram, k1=1.5, b=0.75)를 재사용했습니다. "
             "고도화 방식은 현재 Elasticsearch Nori BM25입니다. 두 방식 모두 같은 원본 문서 14,550개와 "
             "동일한 PostgreSQL Dense 검색을 사용합니다. 정책/원천 문서 단위 중복 제거·RRF 결합을 유지하며 "
             f"각 검색 풀 {pool_k}개, RRF·Cohere 후보 {candidate_k}개, RRF 상수 60, 최종 Top-5를 사용했습니다.", "",
             "두 평가군 모두 현재 Router를 사용해 한 번의 LLM 호출에서 분기와 검색용 질의를 함께 생성했습니다. "
             "질의에는 검색 결과를 나누는 지역·대상·업종·기간·수치·제외 조건을 남기며, "
             "초기 검색에는 재작성 질의를, Cohere 재정렬·근거 확인·최종 답변에는 전체 질문을 전달합니다. "
             "따라서 이 비교는 새 Router 질의 재작성 흐름을 공통 조건으로 둔 기본 BM25와 Elasticsearch BM25 비교입니다.", "",
             "정책의 원문·개인화 검색은 동일한 source-level RRF로 합치고, 같은 백엔드의 결과에서 "
             "동일 정책은 최상위 순위만 반영합니다. Dense 검색, 프롬프트, 프로필, RRF와 Cohere 후보 수는 양쪽에서 같습니다. "
             "세금 검색도 같은 Router 질의 재작성 조건으로 실행합니다.", "",
             "현재 운영 LangGraph의 독립 인스턴스를 별도 Docker 프로세스에서 실행했습니다. "
             "Django API는 ASGI로 프로세스 내부에서 호출했으며 운영 서버의 설정·프로세스·색인을 변경하지 않았습니다. "
             "DB 연결은 읽기 전용이고 세금 캐시는 OFF입니다. 모델·프롬프트·질문·프로필은 동일합니다.", "",
             "Elasticsearch는 Nori analyzer와 현재 live index에 설정된 stoptag를 사용하며, "
             "품사별 BM25 가중치는 적용하지 않습니다. 코드의 NNB stoptag 추가분은 live index 설정에 아직 반영되지 않았습니다. "
             "문서 단위를 동일하게 맞춘 검색 백엔드 비교이므로 과거 청크 기반 BM25 파이프라인을 그대로 재현한 실험은 아닙니다. "
             "두 방식의 토큰화·필드 처리·BM25 파라미터 차이를 포함한 키워드 검색 방식의 효과를 비교합니다.", "",
             "## 정책 검색·가드레일", "",
             "| 지표 | 기본 BM25 | 고도화 Elasticsearch Nori BM25 | 변화 |",
             "| --- | ---: | ---: | ---: |"]
    for label, key in [("Precision@5", "precision_at_k"), ("Recall@5", "recall_at_k")]:
        values = [p["summary"][key] for p in policies]
        lines.append(f"| {label} | {pct(values[0])} | {pct(values[1])} | {(values[1]-values[0])*100:+.1f}%p |")
    lines.append(f"| Hit@5 | {hits[0]}/63 ({pct(hits[0]/63)}) | {hits[1]}/63 ({pct(hits[1]/63)}) | {hits[1]-hits[0]:+d}문항 |")
    for label, key in [("MRR", "mrr"), ("MAP@5", "map")]:
        values = [p["summary"][key] for p in policies]
        lines.append(f"| {label} | {values[0]:.3f} | {values[1]:.3f} | {values[1]-values[0]:+.3f} |")
    latency = [sum(c["latency_ms"] for c in arm.values()) / 63 / 1000 for arm in cases]
    lines.append(f"| 정책 평균 응답 시간 | {latency[0]:.2f}초 | {latency[1]:.2f}초 | {latency[1]-latency[0]:+.2f}초 |")
    values = [metric["accuracy"] for metric in guardrail_metrics]
    lines.append(f"| 정책군 차단 판정 정확도 | {pct(values[0])} | {pct(values[1])} | {(values[1]-values[0])*100:+.1f}%p |")
    lines += ["", "최종 Hit@5는 답변 sources[].policy_id에 정답 정책이 하나 이상 포함됐는지 측정합니다. "
              "검색뿐 아니라 답변 생성과 인용 선택까지 포함한 지표입니다. 정책 평가 63개는 모두 허용 질문이므로 "
              "차단하면 안 되는 질문의 오차단만 확인하며, 차단 대상 질문의 탐지 성능은 측정하지 않습니다.", "",
              "### 검색 단계별 정답 포함", "",
              "| 단계 | 기본 BM25 | 고도화 Elasticsearch |", "| --- | ---: | ---: |"]
    for stage, label in [("dense", "Dense 검색 후보"), ("bm25", "키워드 검색 후보"), ("rrf", f"RRF 상위 {candidate_k}개"),
                         ("top5", "Cohere 재정렬 후 상위 5개"), ("cited", "최종 인용")]:
        values = [sum(bool(set(row[stage]) & set(row["gold"])) for row in arm) for arm in traces]
        lines.append(f"| {label} | {values[0]}/63 | {values[1]}/63 |")
    lines += ["", "## 평가셋 구성과 질문 예시", "",
              "holdout_cases_250.py는 새 데이터 추가 후의 정책 검색 및 세금·로드맵 대화 흐름을 확인하도록 만든 고정 평가셋입니다. "
              "정책은 허용 대상 검색 질문 63개와 차단 대상 가드레일 질문 63개로 구성됩니다. "
              "LangGraph는 세금 31개와 로드맵 31개 시나리오이며, 각 시나리오가 2턴으로 구성되어 총 124턴입니다. "
              "이번 새 실행은 정책 허용 질문 63개와 세금 62턴이며, 가드레일·로드맵 지표는 이전 보고서 값입니다.", "",
              "### 정책 질문 샘플", "",
              "1. `holdout-policy-investor-meeting` — 서울의 IT·소프트웨어 개인사업자(업력 2년 반)가 투자자 미팅 및 후속 투자 논의를 지원하는 제도를 찾는 질문.",
              "   > 서울에서 IT·소프트웨어 개인사업을 운영한 지 2년 반 정도 됐어요. 온라인으로 여러 투자자와 미팅을 잡아 제품과 사업모델을 설명하고 후속 투자 논의를 이어가고 싶어요 이런 지원을 받을 수 있는지 찾아봐줘.",
              "2. `holdout-policy-tech-competitiveness` — 사업자 프로필을 기준으로 기술력 진단과 기술 보완 컨설팅 제도를 찾는 질문.",
              "   > 등록된 제 사업자 정보 기준으로 보고 싶어요. 서비스 기술력과 경쟁력을 전문가에게 진단받고 어떤 기술을 보완해야 할지 컨설팅을 받고 싶어요 지금 제 조건에서 볼 만한 제도가 있는지 알려주세요.",
              "", 
              "### 세금 질문 샘플", "",
              "1. `holdout-tax-v2-income-year-v2` — 귀속연도 누락 시 추가 정보 요청 여부와 이후 연도 지정 계산을 확인하는 2턴 시나리오.",
              "   > 종합소득세 과세표준이 4천8백만원 정도인데 연도를 안 정해도 세액 계산이 되나요?",
              "2. `holdout-tax-v2-vat-adjustments-v2` — 공급가액·매입세액·세액공제·가산세를 반영한 부가가치세 계산 시나리오.",
              "   > 공급가액 3500만원에 매입세액 120만원이고 세액공제 20만원, 가산세 10만원이면 최종 부가세 얼마예요?",
              "", 
              "위 질문들은 평가셋에서 발췌한 예시입니다. 정책은 최종 답변의 인용 정책 ID를 정답과 비교하고, "
              "세금·로드맵은 route/status/grounded/필수 문구 등 기존 자동 검사 기준을 사용합니다.", "",
              "## LangGraph 대화", "",
              "| 영역 | 기본: 턴 통과 | 고도화: 턴 통과 | 기본/고도화 시나리오 통과 | 기본/고도화 평균 시간 |",
              "| --- | ---: | ---: | --- | --- |"]
    for tag, label in [("tax", "세금"), ("roadmap", "로드맵"), (None, "합계")]:
        values = [graph_stats([r for r in g["scenarios"] if tag is None or tag in r["tags"]]) for g in graphs]
        a, b = values
        lines.append(f"| {label} | {a[0]}/{a[1]} ({pct(a[0]/a[1])}) | {b[0]}/{b[1]} ({pct(b[0]/b[1])}) | "
                     f"{a[2]}/{a[3]} · {b[2]}/{b[3]} | {a[4]:.2f}초 · {b[4]:.2f}초 |")
    lines += ["", "대화 통과는 기존 route·status·차단 여부·grounded·필수 문구·답변 길이 자동 검사를 사용합니다. "
              "세금 계산 금액이나 정답 세법 문서 ID를 직접 측정한 정확도가 아닙니다. 로드맵·가드레일은 "
              "키워드 검색 고도화의 직접 효과로 해석하지 않습니다.", "", "## 문항별 변화", "",
              f"기본 방식 대비 고도화 방식에서 실패 → 성공 {len(gains)}건, 성공 → 실패 {len(losses)}건입니다.", ""]
    for label, keys in [("실패 → 성공", gains), ("성공 → 실패", losses)]:
        for key in keys:
            lines.append(f"- {label}: {key}")
    lines += ["", "## 해석과 검증", "",
              f"고도화 방식의 최종 Hit@5 변화는 {(hits[1]-hits[0])/63*100:+.1f}%p입니다. "
              "고도화라는 명칭과 별개로 실제 지표가 좋아진 영역과 그렇지 않은 영역을 표에 모두 기재했습니다. "
              "각 방식 1회 실행이므로 모델 응답 변동과 실행 순서의 영향이 포함될 수 있습니다. "
              "구버전 평가셋의 92.1%와는 질문·정답 구성이 달라 직접 전후 비교하지 않습니다.", "",
              f"원본 문서 변경 없음: {metadata['source_unchanged']} · 평가셋 변경 없음: "
              f"{metadata['dataset_unchanged']} · Elasticsearch alias 변경 없음: {metadata['elasticsearch_alias_unchanged']} · "
              f"DB 변경 없음: {metadata['database_unchanged']} · 검색 코드 불변: {metadata['code_unchanged']}.", ""]
    for arm in arms:
        lines.append(f"- {arm}: 실행 오류 {metadata['arms'][arm]['errors'] or '0건'}, "
                     f"키워드 검색 호출 {metadata['arms'][arm]['lexical_search_calls']}회"
                     + (" (재개 이후 측정값)" if metadata['arms'][arm].get('lexical_search_calls_scope') else ""))
    intent_errors = [metadata["arms"][arm]["errors"].get("tax_intent_invalid_output", 0) for arm in arms]
    if any(intent_errors):
        lines += ["", f"세금 평가 중 calculation_required/type 불일치 출력이 기본 BM25 {intent_errors[0]}회, "
                  f"Elasticsearch {intent_errors[1]}회 로그에 기록됐습니다. 해당 턴은 평가기의 관측된 응답을 기존 자동 검사 기준으로 채점했으며, "
                  "이 횟수는 인프라 검색 오류가 아니라 세금 의도 분류 출력 검증 오류입니다."]
    if metadata.get("recovered_failed_turn"):
        lines += ["", "기본 BM25 세금 41번째 턴에서 LLM의 계산 필요 여부와 계산 종류가 모순되는 출력 오류가 발생했습니다. "
                  "이 턴은 성공할 때까지 재시도하지 않았고 실패로 반영했습니다. 중단 전에 관측값이 저장되지 않아 "
                  "오류 로그와 코드의 고정 오류 응답으로 복원했습니다. 해당 턴의 시간 4.83초는 로그에 남은 세금 노드 "
                  "처리 시간이며 전체 API 시간은 아닙니다. 완료된 166개 응답은 평가 체크포인트에서 재사용했으며, "
                  "응답 캐시를 활성화한 것이 아닙니다. 이후 모델의 같은 의미적 오류는 실패 응답으로 기록하고 평가를 계속합니다. "
                  "통신·검색·재정렬 예외가 발생하면 계속 중단합니다."]
    lines += ["", "## 원본 결과", ""]
    for arm in arms:
        for kind in ("policy", "graph", "stages"):
            path = Path(str(prefix) + f"_{arm}_{kind}.json")
            lines.append(f"- [{arm} {kind}]({path.name})")
    lines.append(f"- [실행 검증 JSON]({prefix.name}_validation.json)")
    if previous_prefix is not None:
        lines += ["", f"가드레일·로드맵 원본 실행은 {previous_prefix.name}이며, 이번에는 재실행하지 않았습니다. "
                  "해당 실행은 중복 요청 문구 정규화 제거 전 코드에서 생성된 보고서이므로, "
                  "그 값은 이번 정책·세금 재평가와 실행 시점 및 질의 전처리 조건이 다릅니다."]
        lines.append(f"- [재사용한 이전 전체 보고서]({Path(str(previous_prefix) + '_REPORT.md').name})")
        lines.append(f"- [이전 가드레일·로드맵 원본 결과]({Path(str(previous_prefix) + '_basic_bm25_graph.json').name})")
    Path(str(prefix) + "_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_policy_report(prefix, metadata):
    policy = json.loads(Path(str(prefix) + "_elasticsearch_policy.json").read_text(encoding="utf-8"))
    traces = json.loads(Path(str(prefix) + "_elasticsearch_stages.json").read_text(encoding="utf-8"))
    cases = [case for case in policy["cases"] if not case["should_block"]]
    total = len(cases)
    hit5 = sum(bool(set(case["relevant_policy_ids"]) & set(case["predicted_policy_ids"][:5])) for case in cases)
    summary = policy["summary"]
    pct = lambda value: f"{value * 100:.1f}%"
    lines = [
        "# Elasticsearch 정책 평가 — Nori BM25", "",
        f"평가 시작: {metadata['started_at_kst']} · 종료: {metadata['finished_at_kst']} (한국시간).", "",
        "## 정책 63문항 결과", "",
        "| 지표 | 결과 |", "| --- | ---: |",
        f"| 최종 인용 Hit@5 | {hit5}/{total} ({pct(hit5 / total)}) |",
        f"| Precision@5 | {pct(summary['precision_at_k'])} |",
        f"| Recall@5 | {pct(summary['recall_at_k'])} |",
        f"| MRR | {summary['mrr']:.3f} |",
        f"| MAP@5 | {summary['map']:.3f} |",
        f"| 평균 응답 시간 | {summary['average_latency_ms'] / 1000:.2f}초 |", "",
        "Hit@5는 최종 답변의 sources[].policy_id에 정답 정책이 하나 이상 포함됐는지 측정합니다. "
        "검색뿐 아니라 Cohere 재정렬, 답변 생성, 최종 인용 선택을 포함합니다.", "",
        "## 검색 단계별 정답 포함", "",
        "| 단계 | 정답 포함 문항 |", "| --- | ---: |",
    ]
    for stage, label in [("dense", "Dense 후보"), ("bm25", "Elasticsearch Nori BM25 후보"),
                         ("rrf", "RRF 후보"), ("rerank", "재정렬 후보"),
                         ("top5", "재정렬 후 상위 5개"), ("cited", "최종 인용")]:
        count = sum(bool(set(row[stage]) & set(row["gold"])) for row in traces)
        lines.append(f"| {label} | {count}/{total} |")
    settings = metadata["settings"]
    lines += ["", "## 실행 조건", "",
              f"정책 질의 {total}건만 실행했습니다. 가드레일, 기본 BM25, 세금 및 로드맵 평가는 실행하지 않았습니다. "
              "기존 Nori BM25 검색과 재정렬 파이프라인을 사용했습니다. "
              f"검색 풀 {settings['nori_retrieval_pool_k']}개, Cohere/RRF 후보 "
              f"{settings['cohere_rerank_candidate_k']}개, 최종 Top-5입니다.", "",
              f"모델: {settings['llm_model']} · Cohere 재정렬 모델: {settings['cohere_rerank_model']} · "
              f"세금 캐시: OFF · DB 읽기 전용: {metadata['db_read_only']} · "
              f"원본 문서 {metadata['source_documents']:,}개.", "",
              f"평가셋 SHA-256: `{metadata['dataset_sha256']}` · "
              f"원본 문서 불변: {metadata['source_unchanged']} · "
              f"평가셋 불변: {metadata['dataset_unchanged']} · "
              f"Elasticsearch alias 불변: {metadata['elasticsearch_alias_unchanged']} · "
              f"DB 불변: {metadata['database_unchanged']} · 코드 불변: {metadata['code_unchanged']}.", "",
              "## 결과 파일", "",
              f"- [정책 문항별 결과]({Path(str(prefix) + '_elasticsearch_policy.json').name})",
              f"- [검색 단계별 추적]({Path(str(prefix) + '_elasticsearch_stages.json').name})",
              f"- [실행 검증 JSON]({Path(str(prefix) + '_validation.json').name})",
              f"- [서버 로그]({Path(str(prefix) + '_server.log').name})"]
    Path(str(prefix) + "_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main(
    resume_prefix: Path | None = None,
    policy_only: bool = False,
    policy_tax_only: bool = False,
    previous_prefix: Path | None = None,
    run_profile: dict | None = None,
):
    if policy_only and policy_tax_only:
        raise ValueError("--policy-only and --policy-tax-only cannot be combined")
    if policy_tax_only and previous_prefix is None:
        raise ValueError("--policy-tax-only requires --reuse-previous-prefix")
    settings = get_settings()
    assert settings.cohere_rerank_candidate_k == 20
    assert settings.nori_retrieval_pool_k == 40
    assert not settings.tax_cache_enabled
    ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d_%H%M%S")
    default_prefix = (
        f"holdout250_policy_tax_bm25_vs_elasticsearch_{stamp}"
        if policy_tax_only
        else f"holdout250_bm25_vs_elasticsearch_{stamp}"
    )
    if run_profile is not None:
        default_prefix += "_gpt56_temp0"
    prefix = resume_prefix or ROOT / default_prefix
    file_handler = logging.FileHandler(str(prefix) + "_server.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    errors = ErrorCounter()
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().addHandler(errors)
    print("RUN_STAMP", stamp, flush=True)
    with connect_database(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SHOW default_transaction_read_only")
            assert cursor.fetchone()[0] == "on", "Require read-only DB connections"
            cursor.execute("SELECT count(*) FROM rag_documents WHERE embedding_status='ready'")
            chunk_count = cursor.fetchone()[0]
    documents = load_elasticsearch_source_documents(settings)
    original_hash = digest(documents)
    es = Elasticsearch(settings.elasticsearch_url, request_timeout=60)
    alias = settings.elasticsearch_index_alias
    es_documents = {hit["_id"]: hit["_source"] for hit in helpers.scan(
        es, index=alias, query={"query": {"match_all": {}}}, size=500,
    )}
    assert es_documents == {d["document_id"]: dict(d) for d in documents}, "DB and ES differ"
    indices = list(es.indices.get_alias(name=alias))
    policy_cases = load_evaluation_cases(DEFAULT_DATASET, mode="policy", suite="holdout250")
    policy_cases = [case for case in policy_cases if not case.should_block]
    scenarios = [] if policy_only else load_evaluation_cases(DEFAULT_DATASET, mode="graph", suite="holdout250")
    if policy_tax_only:
        scenarios = [scenario for scenario in scenarios if "tax" in scenario.tags]
    assert len(policy_cases) == 63
    if policy_tax_only:
        assert sum(len(scenario.turns) for scenario in scenarios) == 62
    elif not policy_only:
        assert sum(len(s.turns) for s in scenarios) == 124
    graph_turn_total = sum(len(scenario.turns) for scenario in scenarios)
    validate_users({c.user_id for c in policy_cases + scenarios}, "db")
    metadata = {
        "started_at_kst": NOW(), "execution_environment": "isolated Docker process; ASGI in process",
        "status": "running", "policy_rrf_mode": "best_rank_per_backend",
        "db_read_only": True, "database": validate_holdout_database(),
        "dataset_sha256": hashlib.sha256(Path("evaluation/holdout_cases_250.py").read_bytes()).hexdigest(),
        "source_sha256": original_hash, "source_documents": len(documents),
        "vector_chunks": chunk_count, "elasticsearch_indices": indices,
        "request_interval_seconds": 6.1, "tax_cache_enabled": False,
        "evaluation_scope": (
            "policy 63 + tax 62; guardrail and roadmap reused from prior comparison"
            if policy_tax_only
            else "elasticsearch policy 63 only" if policy_only
            else "full comparison"
        ),
        "policy_tax_only": policy_tax_only,
        "reuse_previous_prefix": str(previous_prefix) if previous_prefix else None,
        "settings": {key: getattr(settings, key) for key in (
            "llm_model", "embedding_model", "cohere_rerank_model", "cohere_rerank_candidate_k",
            "nori_retrieval_pool_k", "hybrid_rrf_k", "min_relevance_score", "tax_max_hops",
        )}, "arms": {},
        "comparison_scope": (
            "Policy and tax rerun; guardrail and roadmap reused from prior comparison"
            if policy_tax_only
            else "Elasticsearch policy only" if policy_only
            else "Lexical backend only; same source-document corpus and source-level RRF"
        ),
        "baseline": "Existing BM25Search (word + character bigrams, k1=1.5, b=0.75); not historical chunk pipeline",
    }
    if run_profile is not None:
        metadata["run_profile"] = run_profile
        metadata["evaluation_scope"] = "policy 63 + tax 62 only; no guardrail or roadmap evaluation"
        metadata["comparison_scope"] = "Restored gpt-5.6-luna historical model configuration; effective options recorded in run_profile"
    source_paths = ["src/rag/graph.py", "src/rag/discovery.py", "src/rag/answer.py", "src/rag/tax.py",
                    "src/vectorstores/nori_hybrid.py", "src/vectorstores/hybrid.py", "src/vectorstores/elasticsearch.py",
                    "src/features/elasticsearch_indexing.py"]
    metadata["code_sha256"] = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in source_paths}
    metadata_path = Path(str(prefix) + "_validation.json")
    if resume_prefix is not None:
        previous = json.loads(metadata_path.read_text(encoding="utf-8"))
        for key in ("database", "dataset_sha256", "source_sha256", "elasticsearch_indices", "settings", "code_sha256", "run_profile"):
            assert previous.get(key) == metadata.get(key), f"Cannot resume: {key} changed"
        metadata = previous
        metadata["status"] = "running"
        metadata.setdefault("resumed_at_kst", []).append(NOW())
    def save_metadata():
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    save_metadata()
    chunks = [{"chunk_id": d["document_id"], "policy_id": d["policy_id"],
               "title": d["title"], "source": d["source"], "page": 1,
               "content": d["content"], "source_type": d["source_type"],
               "source_id": d["source_id"]} for d in documents]
    dense = PostgresVectorSearch(get_embedding_model(settings), settings)
    if policy_only:
        arms = {"elasticsearch": IsolatedRuntime(dense, ObservedElasticsearch(settings), settings,
                                                  (len(documents), chunk_count))}
    else:
        print("Building existing BM25 over", len(chunks), "source documents", flush=True)
        basic = SourceBM25(chunks)
        arms = {"basic_bm25": IsolatedRuntime(dense, basic, settings, (len(documents), chunk_count)),
                "elasticsearch": IsolatedRuntime(dense, ObservedElasticsearch(settings), settings,
                                                 (len(documents), chunk_count))}
    limiter = Limiter()

    for arm, runtime in arms.items():
        django_views.set_runtime(runtime)
        metadata["arms"].setdefault(arm, {"started_at_kst": NOW()})
        errors.counts.clear()
        if resume_prefix is not None:
            errors.counts.update(metadata["arms"][arm].get("errors", {}))
        trace_path = Path(str(prefix) + f"_{arm}_stages.json")
        traces = json.loads(trace_path.read_text(encoding="utf-8")) if resume_prefix is not None and trace_path.exists() else []
        transport = ASGITransport(app=_django_application)
        checkpoint = Path(str(prefix) + f"_{arm}_observations.jsonl")
        saved = [json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()] if resume_prefix is not None and checkpoint.exists() else []
        policy_saved = [row for row in saved if row["kind"] == "policy"]
        graph_saved = [row for row in saved if row["kind"] == "graph"]

        def save_observation(kind, request, observation):
            with checkpoint.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"kind": kind, "request": request,
                    "observation": observation.model_dump(mode="json")}, ensure_ascii=False) + "\n")

        def reject_degraded_comparison():
            if any(count for name, count in errors.counts.items() if name != "tax_intent_invalid_output"):
                metadata["arms"][arm].update({"aborted_at_kst": NOW(),
                                             "errors": dict(errors.counts)})
                save_metadata()
                raise RuntimeError("Comparison stopped: retrieval/rerank/generation exception; see server log")

        class PolicyClient(HttpLangGraphClient):
            def __init__(self):
                super().__init__("http://testserver")
                self._client = AsyncClient(transport=transport, base_url="http://testserver", timeout=180)
                self.count = 0

            async def recommend(self, **kwargs):
                if self.count < len(policy_saved):
                    row = policy_saved[self.count]
                    assert row["request"] == kwargs, "Policy checkpoint request differs"
                    self.count += 1
                    return EvaluationObservation.model_validate(row["observation"])
                if kwargs["question"] not in blocked:
                    await limiter.wait()
                observation = await super().recommend(**kwargs)
                reject_degraded_comparison()
                self.count += 1
                case = policy_cases[self.count - 1]
                if case.relevant_policy_ids:
                    state = runtime.last_state
                    row = {"case_id": case.case_id, "gold": case.relevant_policy_ids,
                           "route": state.get("route"), "status": state.get("answer_status")}
                    row["search_queries"] = state.get("policy_search_queries", [])
                    for stage, key in [("dense", "dense_docs"), ("bm25", "bm25_docs"),
                                       ("rrf", "retrieved_docs"), ("rerank", "policy_ranked_candidates"),
                                       ("top5", "reranked_docs"), ("cited", "answer_sources")]:
                        row[stage] = [int(d["policy_id"]) for d in state.get(key, [])
                                      if d.get("policy_id") is not None]
                    traces.append(row)
                    assert len(row["rrf"]) <= settings.cohere_rerank_candidate_k
                    Path(str(prefix) + f"_{arm}_stages.json").write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")
                save_observation("policy", kwargs, observation)
                metadata["arms"][arm]["policy_completed"] = self.count
                save_metadata()
                print("PROGRESS", arm, "policy", self.count, "/63", flush=True)
                return observation

        class GraphClient(HttpChatClient):
            def __init__(self):
                super().__init__("http://testserver")
                self._client = AsyncClient(transport=transport, base_url="http://testserver", timeout=180)
                self.count = 0

            async def answer(self, **kwargs):
                if self.count < len(graph_saved):
                    row = graph_saved[self.count]
                    assert row["request"] == kwargs, "Graph checkpoint request/history differs"
                    self.count += 1
                    return AnswerObservation.model_validate(row["observation"])
                await limiter.wait()
                observation = await super().answer(**kwargs)
                reject_degraded_comparison()
                self.count += 1
                save_observation("graph", kwargs, observation)
                metadata["arms"][arm]["graph_completed"] = self.count
                save_metadata()
                print("PROGRESS", arm, "graph", self.count, "/", graph_turn_total, flush=True)
                return observation

        blocked = {c.question for c in policy_cases if c.should_block}
        async with PolicyClient() as client:
            policy = await evaluate_cases(policy_cases, client, k=5)
        Path(str(prefix) + f"_{arm}_policy.json").write_text(policy.model_dump_json(indent=2), encoding="utf-8")
        Path(str(prefix) + f"_{arm}_stages.json").write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")
        if not policy_only:
            async with GraphClient() as client:
                graph = await evaluate_scenarios(scenarios, client)
            Path(str(prefix) + f"_{arm}_graph.json").write_text(graph.model_dump_json(indent=2), encoding="utf-8")
        metadata["arms"][arm].update({"finished_at_kst": NOW(), "errors": dict(errors.counts),
                                     "lexical_search_calls": runtime.controlled_search.bm25_search.calls
                                     if hasattr(runtime.controlled_search.bm25_search, "calls") else None})
        if saved:
            metadata["arms"][arm]["lexical_search_calls_scope"] = "resumed process only; completed observations replayed"
        save_metadata()
        print("ARM_COMPLETE", arm, flush=True)
    metadata["finished_at_kst"] = NOW()
    metadata["source_unchanged"] = original_hash == digest(load_elasticsearch_source_documents(settings))
    metadata["dataset_unchanged"] = metadata["dataset_sha256"] == hashlib.sha256(
        Path("evaluation/holdout_cases_250.py").read_bytes()).hexdigest()
    metadata["elasticsearch_alias_unchanged"] = indices == list(es.indices.get_alias(name=alias))
    metadata["database_unchanged"] = metadata["database"] == validate_holdout_database(settings=settings)
    metadata["code_unchanged"] = metadata["code_sha256"] == {
        path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in source_paths}
    assert all(metadata[key] for key in ("source_unchanged", "dataset_unchanged", "elasticsearch_alias_unchanged",
                                        "database_unchanged", "code_unchanged")), "Comparison inputs changed during evaluation"
    metadata["status"] = "complete"
    save_metadata()
    if policy_only:
        write_policy_report(prefix, metadata)
    else:
        write_report(prefix, metadata)
    print("COMPLETE", stamp, flush=True)


if __name__ == "__main__":
    if "default_transaction_read_only=on" not in os.environ.get("PGOPTIONS", ""):
        raise SystemExit("Set PGOPTIONS='-c default_transaction_read_only=on' in the one-off container")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-prefix", type=Path)
    parser.add_argument("--policy-only", action="store_true")
    parser.add_argument("--policy-tax-only", action="store_true")
    parser.add_argument("--reuse-previous-prefix", type=Path)
    args = parser.parse_args()
    asyncio.run(
        main(
            args.resume_prefix,
            args.policy_only,
            args.policy_tax_only,
            args.reuse_previous_prefix,
        )
    )
