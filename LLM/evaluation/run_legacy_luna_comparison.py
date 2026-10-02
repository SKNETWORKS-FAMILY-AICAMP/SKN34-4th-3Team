"""Restore September 21 model options only inside a read-only evaluation process."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from langchain_openai import ChatOpenAI

from evaluation import run_bm25_elasticsearch_comparison as comparison
from src.models.factory import configure_chat_model
from src.rag import graph as graph_module


DEFAULT_BASELINE = Path(
    "evaluation/results/holdout250_policy_tax_bm25_vs_elasticsearch_20261002_125639"
)
PROFILE = {
    "model": "gpt-5.6-luna",
    "requested_temperature": 0,
    "effective_temperature": None,
    "temperature_sent": False,
    "langchain_openai_version": "1.6.0 (same as historical lockfile)",
    "fast_reasoning_effort": "low",
    "contextualization_reasoning_effort": "unspecified",
    "historical_code_commit": "8e6de7e",
    "scope": "model options only; current graph, prompts and dataset retained",
}


def historical_configure(llm, **options):
    configured = configure_chat_model(llm, **options)
    if isinstance(llm, ChatOpenAI):
        configured = configured.model_copy(update={"temperature": llm.temperature})
        assert configured.temperature == llm.temperature
    return configured


class HistoricalRuntime(comparison.IsolatedRuntime):
    def __init__(self, dense, lexical, settings, counts):
        super().__init__(dense, lexical, settings, counts)
        self._llm_factory = lambda: ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )


def read_result(prefix, suffix):
    return json.loads(Path(str(prefix) + suffix).read_text(encoding="utf-8"))


def policy_stats(report):
    cases = [case for case in report["cases"] if not case["should_block"]]
    hits = sum(bool(set(case["relevant_policy_ids"]) & set(case["predicted_policy_ids"][:5]))
               for case in cases)
    assert len(cases) == 63
    return hits, report["summary"]


def tax_stats(report):
    rows = [row for row in report["scenarios"] if "tax" in row["tags"]]
    turns = [turn for row in rows for turn in row["turns"]]
    assert len(rows) == 31 and len(turns) == 62
    return sum(turn["passed"] for turn in turns), sum(row["passed"] for row in rows), sum(
        turn["latency_ms"] for turn in turns
    ) / 62 / 1000


def write_report(prefix, metadata, baseline_prefix):
    baseline = read_result(baseline_prefix, "_validation.json")
    for key in ("dataset_sha256", "source_sha256", "database", "elasticsearch_indices"):
        assert metadata[key] == baseline[key], f"Model comparison inputs changed: {key}"
    for key, value in baseline["settings"].items():
        if key != "llm_model":
            assert metadata["settings"][key] == value, f"Model comparison setting changed: {key}"
    metadata["model_baseline_prefix"] = str(baseline_prefix)
    metadata["model_baseline_inputs_equal"] = True
    Path(str(prefix) + "_validation.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    arms = ("basic_bm25", "elasticsearch")
    stats = []
    for base in (baseline_prefix, prefix):
        for arm in arms:
            hits, policy = policy_stats(read_result(base, f"_{arm}_policy.json"))
            tax = tax_stats(read_result(base, f"_{arm}_graph.json"))
            stats.append((hits, policy, tax))
    lines = [
        "# 정책·세금 평가 — 5.6-luna 과거 설정 복원 비교", "",
        f"새 평가 시작: {metadata['started_at_kst']} · 종료: {metadata['finished_at_kst']} (한국시간).", "",
        "## 모델·검색기 비교", "",
        "6-luna 수치는 2026-10-02 12:56~13:40 평가의 기존 결과이며 다시 실행하지 않았습니다. "
        "이번에는 5.6-luna 설정에서 기본 BM25와 Elasticsearch의 정책 63문항·세금 62턴을 각각 실행했습니다.", "",
        "| 지표 | 6-luna 기본 BM25 (이전) | 6-luna Elasticsearch (이전) | 5.6-luna 기본 BM25 (신규) | 5.6-luna Elasticsearch (신규) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    def row(label, values):
        lines.append("| " + label + " | " + " | ".join(values) + " |")
    row("정책 최종 인용 Hit@5", [f"{s[0]}/63 ({s[0]/63:.1%})" for s in stats])
    for label, key, percent in (("Precision@5", "precision_at_k", True),
                                ("Recall@5", "recall_at_k", True),
                                ("MRR", "mrr", False), ("MAP@5", "map", False)):
        row(label, [f"{s[1][key]:.1%}" if percent else f"{s[1][key]:.3f}" for s in stats])
    row("정책 평균 응답 시간", [f"{s[1]['average_latency_ms']/1000:.2f}초" for s in stats])
    row("세금 자동 검사 턴 통과", [f"{s[2][0]}/62 ({s[2][0]/62:.1%})" for s in stats])
    row("세금 시나리오 전체 통과", [f"{s[2][1]}/31" for s in stats])
    row("세금 평균 응답 시간", [f"{s[2][2]:.2f}초" for s in stats])
    lines += ["", "## 새 5.6-luna 평가의 검색 단계", "",
              "| 정답 정책 포함 단계 | 기본 BM25 | Elasticsearch |", "| --- | ---: | ---: |"]
    traces = [read_result(prefix, f"_{arm}_stages.json") for arm in arms]
    for stage, label in (("dense", "Dense 후보"), ("bm25", "키워드 후보"),
                         ("rrf", "RRF 상위 20개"), ("top5", "Cohere 상위 5개"), ("cited", "최종 인용")):
        values = [sum(bool(set(r[stage]) & set(r["gold"])) for r in rows) for rows in traces]
        lines.append(f"| {label} | {values[0]}/63 | {values[1]}/63 |")
    lines += ["", "## 복원 및 격리 조건", "",
              "9월 21일 코드 8e6de7e의 모델 옵션만 복원했습니다. 모델 gpt-5.6-luna, 생성 코드의 temperature=0이며, "
              "당시와 현재 잠금 파일의 langchain-openai 버전은 모두 1.6.0입니다. 이 버전의 모델 검증기는 "
              "gpt-5 계열에서 추론 강도 none이 아니면 temperature=0을 자동 제거합니다. 오프라인 요청 옵션 검증에서 "
              "실제 temperature는 None이고 API 요청에 temperature 항목이 없음을 확인했습니다. "
              "정책·세금 Router, 세금 의도/근거 판정/추가 검색어/계산 입력 생성 및 정책·세금 최종 답변은 "
              "reasoning_effort=low를 유지합니다. 문맥 복원은 추론 강도를 별도 지정하지 않습니다.", "",
              "운영 .env와 src 코드는 수정하지 않고 별도 Docker 프로세스의 모델 팩토리와 설정 함수만 교체했습니다. "
              "운영 서비스 재시작·HTTP 요청·Elasticsearch 재색인 없이 내부 ASGI를 실행했습니다. "
              "DB는 읽기 전용이며 세금 응답/근거 캐시는 OFF입니다. 원본 문서 14,550개, 검색 풀 40개, "
              "RRF/Cohere 후보 20개, 최종 Top-5와 기존 Dense·질의 재작성·프롬프트를 유지했습니다.", "",
              "## 평가셋 및 지표 해석", "",
              "holdout_cases_250.py의 새 데이터 기반 정책 허용 질문 63개와 세금 31개 2턴 시나리오만 실행했습니다. "
              "가드레일·로드맵은 이번 평가에서 제외했습니다. 정책 Hit@5/MRR/MAP은 최종 인용 정책 ID 기준이며 "
              "LLM 답변 생성을 포함합니다. 세금은 기존 route/status/grounded/필수 문구 등 자동 검사 통과율로, "
              "정답 세법 문서 검색 Hit@K나 모든 계산 금액의 정확도가 아닙니다.", "",
              "정책 예시: 서울의 IT·소프트웨어 개인사업자(업력 2년 반)가 투자자 미팅 및 후속 투자 논의를 지원하는 제도를 찾는 질문.",
              "세금 예시: ‘종합소득세 과세표준이 4천8백만원 정도인데 연도를 안 정해도 세액 계산이 되나요?’ 이후 귀속연도를 추가하는 2턴 질문.", "",
              "코드상 temperature 0을 복원했지만 라이브러리가 제거하므로, 양쪽 모두 temperature를 전송하지 않습니다. "
              "실제 비교 변수는 LLM 모델이며 주요 단계의 추론 강도 low는 같습니다. "
              "검색기마다 1회 실행이고 6-luna는 이전 실행값이므로 모델 변동과 실행 시점의 영향이 포함됩니다. "
              "9월 21일의 92.1%는 구형 평가셋 결과라 직접 재현 기준으로 사용하지 않습니다.", "",
              "## 오류 및 입력 검증", ""]
    for arm in arms:
        lines.append(f"- {arm}: 오류 {metadata['arms'][arm]['errors'] or '0건'}, "
                     f"키워드 검색 호출 {metadata['arms'][arm]['lexical_search_calls']}회")
    lines += ["", "세금 의도 calculation_required/type 불일치는 관측된 응답을 기존 자동 검사 기준으로 채점합니다. "
              "검색·Cohere·최종 생성의 외부 호출 오류가 감지되면 평가를 중단하며, 완료까지 실패를 감추지 않습니다.", "",
              f"원본 문서·평가셋·DB·ES alias·코드 불변: {all(metadata[k] for k in ('source_unchanged', 'dataset_unchanged', 'database_unchanged', 'elasticsearch_alias_unchanged', 'code_unchanged'))}. "
              "기존 6-luna 결과와 문서·평가셋·프로필·검색 설정 일치: True.", "",
              "## 원본 결과", "",
              f"- [이전 6-luna 비교 보고서]({baseline_prefix.name}_REPORT.md)",
              f"- [실행 검증]({prefix.name}_validation.json)"]
    for arm in arms:
        for kind in ("policy", "graph", "stages"):
            filename = f"{prefix.name}_{arm}_{kind}.json"
            lines.append(f"- [{arm} {kind}]({filename})")
    Path(str(prefix) + "_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_policy_report(prefix, metadata, baseline_prefix):
    baseline = read_result(baseline_prefix, "_validation.json")
    for key in ("dataset_sha256", "source_sha256", "database", "elasticsearch_indices"):
        assert metadata[key] == baseline[key], f"Model comparison inputs changed: {key}"
    for key, value in baseline["settings"].items():
        if key != "llm_model":
            assert metadata["settings"][key] == value, f"Model comparison setting changed: {key}"
    metadata["evaluation_scope"] = "policy 63 only per backend; tax, guardrail and roadmap excluded"
    metadata["policy_tax_only"] = False
    metadata["model_baseline_prefix"] = str(baseline_prefix)
    metadata["model_baseline_inputs_equal"] = True
    metadata["discarded_tax_turns"] = metadata["arms"].get("basic_bm25", {}).get("graph_completed", 0)
    Path(str(prefix) + "_validation.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    arms = ("basic_bm25", "elasticsearch")
    stats = [policy_stats(read_result(base, f"_{arm}_policy.json"))
             for base in (baseline_prefix, prefix) for arm in arms]
    lines = [
        "# 정책 63문항 — 5.6-luna 과거 설정 복원 및 검색기 비교", "",
        f"평가 시작: {metadata['started_at_kst']} · 종료: {metadata['finished_at_kst']} (한국시간).", "",
        "## 비교 결과", "",
        "6-luna 수치는 2026-10-02 12:56~13:40 평가의 기존 결과를 사용했습니다. "
        "이번 5.6-luna 평가에서 완료한 기본 BM25 정책 63건을 그대로 사용하고, Elasticsearch 정책 63건을 새로 실행했습니다.", "",
        "| 지표 | 6-luna 기본 BM25 (이전) | 6-luna Elasticsearch (이전) | 5.6-luna 기본 BM25 (신규) | 5.6-luna Elasticsearch (신규) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    def row(label, values):
        lines.append("| " + label + " | " + " | ".join(values) + " |")
    row("최종 인용 Hit@5", [f"{s[0]}/63 ({s[0]/63:.1%})" for s in stats])
    for label, key, percent in (("Precision@5", "precision_at_k", True),
                                ("Recall@5", "recall_at_k", True),
                                ("MRR", "mrr", False), ("MAP@5", "map", False)):
        row(label, [f"{s[1][key]:.1%}" if percent else f"{s[1][key]:.3f}" for s in stats])
    row("평균 응답 시간", [f"{s[1]['average_latency_ms']/1000:.2f}초" for s in stats])
    lines += ["", "## 5.6-luna 검색 단계별 정답 포함", "",
              "| 단계 | 기본 BM25 | Elasticsearch |", "| --- | ---: | ---: |"]
    traces = [read_result(prefix, f"_{arm}_stages.json") for arm in arms]
    for stage, label in (("dense", "Dense 후보"), ("bm25", "키워드 후보"),
                         ("rrf", "RRF 상위 20개"), ("top5", "Cohere 상위 5개"), ("cited", "최종 인용")):
        values = [sum(bool(set(r[stage]) & set(r["gold"])) for r in rows) for rows in traces]
        lines.append(f"| {label} | {values[0]}/63 | {values[1]}/63 |")
    lines += ["", "## 실제 복원한 설정과 격리", "",
              "9월 21일 8e6de7e의 모델 생성 코드를 평가 프로세스에서 복원했습니다. gpt-5.6-luna에 "
              "temperature=0을 지정하지만 당시와 현재 모두 langchain-openai 1.6.0이 이를 자동 제거합니다. "
              "실제 요청에 temperature는 없으며, 주요 정책 Router·답변 생성은 reasoning_effort=low입니다. "
              "문맥 복원은 추론 강도를 별도 지정하지 않습니다. API 호출 전 실제 요청 옵션으로 확인했습니다.", "",
              "운영 .env와 src 코드는 수정하지 않았으며 운영 서비스도 재시작하지 않았습니다. "
              "별도 Docker 프로세스에서 내부 ASGI만 호출하고 DB는 읽기 전용, 세금 캐시는 OFF로 설정했습니다. "
              "문서 14,550개, 검색 풀 40개, RRF/Cohere 후보 20개, 최종 Top-5이며, "
              "현재 Dense·Router 질의 재작성·프롬프트를 그대로 유지했습니다. ES 재색인도 하지 않았습니다.", "",
              f"범위 변경 전에 실행된 세금 {metadata['discarded_tax_turns']}턴은 보존만 하고 보고서에서 제외했습니다. "
              "가드레일·로드맵 및 이후 세금 평가는 실행하지 않았습니다.", "",
              "## 평가셋 및 해석", "",
              "새 데이터 기반 holdout_cases_250.py의 정책 허용 질문 63개를 사용했습니다. "
              "예시: ‘서울에서 IT·소프트웨어 개인사업을 운영한 지 2년 반 정도 됐어요. 온라인으로 여러 투자자와 "
              "미팅을 잡아 제품과 사업모델을 설명하고 후속 투자 논의를 이어가고 싶어요 이런 지원을 받을 수 있는지 찾아봐줘.’", "",
              "Hit@5/MRR/MAP은 최종 인용 정책 ID 기준이며 답변 생성까지 포함합니다. "
              "두 모델 모두 실제 temperature를 전송하지 않아 실질적인 변경 변수는 모델입니다. "
              "각 검색기 1회 실행, 6-luna는 이전 실행값이므로 모델 응답 변동과 실행 시점 영향이 포함됩니다. "
              "과거 92.1%는 구형 평가셋 값이므로 이번 평가의 직접 재현 기준이 아닙니다.", "",
              "## 검증 및 원본 결과", "",
              f"문서·평가셋·DB·ES alias·검색 코드 불변: {all(metadata[k] for k in ('source_unchanged', 'dataset_unchanged', 'database_unchanged', 'elasticsearch_alias_unchanged', 'code_unchanged'))}. "
              "기존 6-luna 결과와 문서·평가셋·프로필·검색 설정 일치: True.", "",
              f"- [이전 6-luna 보고서]({baseline_prefix.name}_REPORT.md)",
              f"- [실행 검증]({prefix.name}_validation.json)"]
    for arm in arms:
        for kind in ("policy", "stages"):
            filename = f"{prefix.name}_{arm}_{kind}.json"
            lines.append(f"- [{arm} {kind}]({filename})")
    Path(str(prefix) + "_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main(baseline_prefix, resume_prefix=None, policy_only=False):
    settings = comparison.get_settings()
    assert settings.llm_model == PROFILE["model"] and not settings.tax_cache_enabled
    baseline = read_result(baseline_prefix, "_validation.json")
    assert baseline["status"] == "complete" and baseline["settings"]["llm_model"] == "gpt-6-luna"
    for path in ("src/rag/graph.py", "src/rag/discovery.py", "src/rag/answer.py", "src/rag/tax.py"):
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == baseline["code_sha256"][path], path
    probe = ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0)
    fast = historical_configure(probe, reasoning_effort="low")
    assert probe.temperature is None and fast.temperature is None and fast.reasoning_effort == "low"
    assert "temperature" not in fast._default_params
    print("MODEL_PROFILE", json.dumps(PROFILE), flush=True)
    comparison.IsolatedRuntime = HistoricalRuntime
    graph_module.configure_chat_model = historical_configure
    comparison.write_report = lambda prefix, metadata: write_report(prefix, metadata, baseline_prefix)
    comparison.write_policy_report = lambda prefix, metadata: write_policy_report(prefix, metadata, baseline_prefix)
    if policy_only and resume_prefix is None:
        raise ValueError("Policy-only continuation requires completed basic BM25 policy results")
    await comparison.main(resume_prefix, policy_only=policy_only, policy_tax_only=not policy_only, previous_prefix=baseline_prefix,
                          run_profile=PROFILE)


if __name__ == "__main__":
    if "default_transaction_read_only=on" not in os.environ.get("PGOPTIONS", ""):
        raise SystemExit("Require read-only PGOPTIONS")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-prefix", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--resume-prefix", type=Path)
    parser.add_argument("--policy-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.baseline_prefix, args.resume_prefix, args.policy_only))
