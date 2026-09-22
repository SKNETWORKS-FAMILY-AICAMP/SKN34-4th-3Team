# CatBoost Judge 운영 그래프 E2E 비교 — 2026-09-21 15:48

## 실험 계약

운영 `build_graph()`를 그대로 사용하고 **세금 근거 충분성 판정 의존성만 CatBoost로 교체**했다. Router, 질문 문맥화, Dense+Nori 검색, RRF, Cohere Rerank, 세금 Multi-hop, 계산기와 최종 LLM 답변은 운영과 동일하게 실행된다. 정책 경로에는 교체 대상 LLM Judge가 없으므로 기존 정책 판정 로직을 유지하며 회귀 검증으로만 사용한다.

세금 캐시는 과거 LLM Judge 결정을 재사용해 ML Judge를 우회할 수 있으므로 이 비교 실행에서만 비활성화했다. 운영 코드는 변경하지 않았다.

## CatBoost 오프라인 Validation

- RandomizedSearchCV: 20회, 5-fold, Macro F1
- 최적 파라미터: `{"random_strength": 5, "learning_rate": 0.03, "l2_leaf_reg": 5, "iterations": 200, "depth": 6, "border_count": 128}`
- Test 150건: 미사용(봉인 유지)

| Accuracy | Macro F1 | 충분 Precision | 충분 Recall | 불충분 Recall | FP/FPR | 혼동행렬 |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 0.733 | 0.694 | 0.901 | 0.726 | 0.757 | 9/0.243 | `[[28, 9], [31, 82]]` |

## 정책 63건 E2E 회귀 확인

정책 결과 변화는 ML Judge 효과가 아니다. 동일 운영 그래프의 재실행 편차와 회귀 여부를 확인하는 지표다.

| 지표 | Elasticsearch 운영 기준 | ML Judge 복제 그래프 | 변화 |
| --- | ---: | ---: | ---: |
| P@5 | 19.7% | 20.0% | +0.3%p |
| R@5 | 78.6% | 79.4% | +0.8%p |
| Hit@5 | 58/63 (92.1%) | 58/63 (92.1%) | +0.0%p |
| MRR | 0.806 | 0.798 | -0.008 |
| MAP@5 | 0.683 | 0.683 | -0.000 |
| 정답 전체 검색 | 41/63 | 42/63 | +1건 |
| 평균 E2E 지연 | 6.29초 | 8.29초 | +2.00초 |

## 세금 법령 9시나리오·18턴 E2E 비교

이 표가 Judge 교체 효과를 판단하는 주 비교다. 단순히 CatBoost가 1을 출력한 횟수가 아니라 최종 답변의 기대 status·grounded 등 자동검사를 통과한 결과다.

| 지표 | Elasticsearch + LLM Judge | Elasticsearch + CatBoost Judge | 변화 |
| --- | ---: | ---: | ---: |
| 턴 통과 | 14/18 (77.8%) | 4/18 (22.2%) | -55.6%p |
| 시나리오 통과 | 7/9 (77.8%) | 1/9 (11.1%) | -66.7%p |
| status 검사 | 14/18 (77.8%) | 4/18 (22.2%) | -55.6%p |
| grounded 검사 | 18/18 (100.0%) | 4/18 (22.2%) | -77.8%p |
| 평균 E2E 지연 | 12.46초 | 16.49초 | +4.03초 |

실패 항목:
- `holdout-tax-business-transfer` 1턴: status, grounded
- `holdout-tax-common-input-tax` 1턴: status, grounded
- `holdout-tax-common-input-tax` 2턴: status, grounded
- `holdout-tax-business-expense` 1턴: status, grounded
- `holdout-tax-business-expense` 2턴: status, grounded
- `holdout-tax-invoice-issue` 1턴: status, grounded
- `holdout-tax-invoice-issue` 2턴: status, grounded
- `holdout-tax-bad-debt-credit` 1턴: status, grounded
- `holdout-tax-withholding-deadline` 1턴: status, grounded
- `holdout-tax-withholding-deadline` 2턴: status, grounded
- `holdout-tax-corporate-expense` 1턴: status, grounded
- `holdout-tax-corporate-expense` 2턴: status, grounded
- `holdout-tax-startup-reduction-law` 1턴: status, grounded
- `holdout-tax-startup-reduction-law` 2턴: status, grounded

## ML Judge 진단

- 호출 46회: 충분 4회, 불충분 42회
- 평균 CatBoost 추론시간: 1.342ms
- 충분/불충분 출력 횟수는 정확도 지표가 아니며, 위 E2E 통과율과 함께 해석해야 한다.
- CatBoost는 이진 충분성만 제공하므로 세부 누락정보·계산값 추출이 필요한 계산 질문이 아닌 `legal_evidence` 범위만 비교한다.

## 결과 파일

- [통합 JSON](../../../LLM/evaluation/results/catboost_judge_comparison/catboost_judge_comparison.json)
- [정책 E2E JSON](../../../LLM/evaluation/results/catboost_judge_comparison/catboost_e2e_policy.json)
- [세금 E2E JSON](../../../LLM/evaluation/results/catboost_judge_comparison/catboost_e2e_tax_legal.json)
- [기준 보고서](ELASTICSEARCH_COMPARISON_REPORT.md)
