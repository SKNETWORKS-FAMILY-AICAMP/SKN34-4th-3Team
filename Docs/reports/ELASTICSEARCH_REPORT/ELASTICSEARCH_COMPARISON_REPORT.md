# Elasticsearch 검색기 holdout250 비교 — 2026-09-21 12:51

## 결론

이 평가는 holdout250 중 **운영 Dense + Elasticsearch Nori BM25 → policy/source-level RRF → Cohere Rerank 검색기를 사용하는 81턴**만 대상으로 한다. 기준선은 [06_EVAL_250_COMPARISON.md](06_EVAL_250_COMPARISON.md)의 2026-09-16 결과다.

| 보고용 범위 | 기존 | Elasticsearch 적용 후 | 변화 |
| --- | ---: | ---: | ---: |
| 정책 정답 완전 검색 | 39/63 (61.9%) | **41/63 (65.1%)** | +3.2%p |
| 세금 법령 답변 통과 | 13/18 (72.2%) | **14/18 (77.8%)** | +5.6%p |
| 보고용 복합 통과¹ | 52/81 (64.2%) | **55/81 (67.9%)** | +3.7%p |

¹ 정책의 ‘정답 완전 검색’ 63건과 세금의 ‘답변 자동검사 통과’ 18건을 기존 보고 방식처럼 합산한 참고값이다. 두 항목의 의미가 다르므로 순수 검색 Recall로 해석하지 않는다.

## 평가 범위와 공정성 조건

- 정책: 허용 질문 63건. 상위 5개 고유 policy_id를 기존 정답 policy_id와 비교한다.
- 세금: `legal_evidence` 9개 시나리오·18턴. status·grounded 등 기존 자동검사를 그대로 사용한다.
- 제외: Guardrail 63건, 로드맵 62턴, 세금 계산 20턴, 추가정보 요구 12턴, 지원연도 초과 6턴, 범위 밖 6턴.
- 현재 운영 설정을 그대로 호출하므로 질문 임베딩·Cohere Rerank·최종 LLM 생성까지 포함한 종단 간 평가다. 검색기 단독 A/B가 아니다.
- 세금에는 정답 문서 ID가 없어 정책과 같은 Recall을 계산할 수 없다. 따라서 기존 보고서와 동일하게 답변 통과율과 grounded/status를 비교한다.

## 정책 검색 성능

| 지표 | 기존 | Elasticsearch 적용 후 | 변화 |
| --- | ---: | ---: | ---: |
| P@5 | 18.7% | **19.7%** | +1.0%p |
| R@5 | 73.0% | **78.6%** | +5.6%p |
| Hit@5 | 53/63 (84.1%) | **58/63 (92.1%)** | +7.9%p |
| MRR | 0.758 | **0.806** | +0.05 |
| MAP@5 | 0.655 | **0.683** | +0.03 |
| 정답 완전 검색 | 39/63 (61.9%) | **41/63 (65.1%)** | +2건 |
| 평균 종단 간 시간 | 3.85초 | **6.29초** | +2.44초 |

정답 일부/전체 미검색 22건: `holdout-policy-seoul-success-school`, `holdout-policy-startup-center-space`, `holdout-policy-seoul-special-guarantee`, `holdout-policy-cloud-open-innovation`, `holdout-policy-small-business-ai`, `holdout-policy-software-project-finance`, `holdout-policy-seoul-tourism-tech`, `holdout-policy-seoul-incubation-space`, `holdout-policy-seoul-center-options`, `holdout-policy-ip-prototype-training`, `holdout-policy-workplace-improvement`, `holdout-policy-food-export-expo`, `holdout-policy-influencer-programs`, `holdout-policy-restaurant-facility-loan`, `holdout-policy-suwon-guarantees`, `holdout-policy-anyang-small-guarantees`, `holdout-policy-youth-food-hub`, `holdout-policy-small-business-fund`, `holdout-policy-startup-interest-options`, `holdout-policy-consulting-options`, `holdout-policy-japan-market`, `holdout-policy-local-digital-options`

Hit@5는 정답 policy_id가 여러 개인 문항에서도 그중 하나 이상이 Top-5에 있으면 1로 계산한다. 기존 53/63은 기준 보고서의 완전 검색 39건과 부분 검색 14건의 합이다.

## 세금 법령 검색 기반 답변

| 지표 | 기존 | Elasticsearch 적용 후 | 변화 |
| --- | ---: | ---: | ---: |
| 턴 통과 | 13/18 (72.2%) | **14/18 (77.8%)** | +5.6%p |
| 시나리오 전체 통과 | 6/9 (66.7%) | **7/9 (77.8%)** | +11.1%p |
| status 검사 | 13/18 (72.2%) | **14/18 (77.8%)** | +5.6%p |
| grounded 검사 | 18/18 (100.0%) | **18/18 (100.0%)** | 0.0%p |
| 현재 평균 종단 간 시간 | 기존 법령 subset 값 없음 | **12.46초** | 비교 제외 |

실패 턴:
- `holdout-tax-business-expense` 1턴: status
- `holdout-tax-business-expense` 2턴: status
- `holdout-tax-corporate-expense` 1턴: status
- `holdout-tax-corporate-expense` 2턴: status

## 해석 제한

- 기준선 보고서에는 세금 법령 18턴의 별도 latency가 없어 시간 증감은 정책만 비교했다.
- 세금 자동검사의 grounded 통과는 근거 출처가 존재한다는 뜻이며, 정답 법령 문서를 찾았다는 Recall 지표는 아니다.
- 운영 그래프 전체를 호출하므로 성능 변화에는 검색기 외에도 현재 Router·Rerank·LLM·캐시 상태가 영향을 줄 수 있다. Elasticsearch의 순수 기여도를 분리하려면 동일 후보에 대한 별도 retrieval-only A/B가 필요하다.

원시 결과: [정책 JSON](../../LLM/evaluation/results/retriever_policy_20260921_124026.json) · [세금 법령 JSON](../../LLM/evaluation/results/retriever_tax_legal_20260921_124026.json)
