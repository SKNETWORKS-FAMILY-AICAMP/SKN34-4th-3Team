# LLM LangGraph holdout250 일회성 평가 — 2026-09-12

## 결론: 다음에 무엇을 보강할까?

**1순위는 정책 검색, 2순위는 세금의 법적 근거 답변이다.** 로드맵과 범위 밖 질문 차단은 이번 사전 목표를 통과했으므로 우선 유지·회귀 검사 대상으로 둔다.

| 영역 | 이번 결과 | 판단 | 다음 개발 작업 |
| --- | ---: | --- | --- |
| **정책 검색** | 정답을 상위 5개에서 찾은 정도 **R@5 64.3%** | 목표 70% 미달. 63문항 중 정답 전부 누락 16개, 일부 누락 13개 | **검색 단계를 분해해 진단:** 개인화 검색어 → dense/BM25 후보 → RRF 통합 후보 → Cohere 재정렬 상위 5개 중 *어디서* 정답이 빠지는지 확인 |
| **세금 대화** | **41/62턴 통과(66.1%)** | 목표 60%는 통과했지만 법적 근거 유형은 **4/18턴**뿐 | 법적 근거 질문에서 기대 상태와 근거 판정이 왜 어긋나는지 응답·출처 trace를 확인하고 개발셋에서 수정 |
| **로드맵 대화** | **57/62턴 통과(91.9%)** | 목표 90% 통과. 단, E단계는 **5/8턴** | 전체 흐름은 유지하고 E단계의 상태·차단 판정만 개발셋에서 회귀 점검 |
| **범위 밖 차단** | **63/63 정확히 차단**, 정상 정책 질문 오차단 0/63 | 목표 통과 | 현재 동작 유지, 회귀 테스트 지속 |

정책 검색을 특히 먼저 볼 이유는 **정책 질문 63/63개가 차단 없이 검색 경로에 진입했기 때문**이다. 문제는 “입구에서 막힘”보다 “상위 5개 결과에 정답이 충분히 남지 않음”에 가깝다. 그중 사용자 조건을 질문에 직접 쓰지 않은 `implicit_profile` 유형의 R@5는 **51.6%**, 직접 쓴 `explicit_profile`은 **76.6%**였다. 따라서 개인화 검색어 구성은 우선 점검할 만한 **가설**이다. 다만 현재 결과만으로 검색어 생성, 후보 검색, 재정렬 중 어느 단계가 원인인지 확정할 수는 없다.

**실행 순서:** 실패 ID를 개발용 `legacy80` 또는 별도 개발셋의 유사 질문으로 재현 → 단계별 후보·응답 trace를 비교 → 원인이 확인된 부분만 수정 → 개발셋으로 회귀 검사. **이번 `holdout250`을 다시 돌리거나 그 문항에 맞춘 예외 규칙을 추가하지 않는다.** 다음 대외 검증은 새 홀드아웃으로 한다.

> 지표 읽는 법: **턴**은 답변 1개, **시나리오**는 연결된 2턴 대화다. 세금·로드맵을 합친 시나리오 통과율은 **45/62(72.6%)**, 턴 통과율은 **98/124(79.0%)**다. **R@5**는 문항별 정답 정책 중 상위 5개에 든 비율의 평균이므로 정책 검색의 별도 지표이며, “63문항 중 64.3% 성공”이라는 뜻은 아니다.

## 평가 방법과 보존 조건

`holdout250`은 개발·회귀용 `legacy80`과 분리된 일회성 홀드아웃이다. 평가셋·DB·평가 로직은 결과에 맞추어 수정하지 않았다. 사전 검증은 `evaluation.evaluation_cases`, `--suite holdout250 --user-source db --mode policy --validate-only`, `pytest -q` 순으로 통과했다(291 tests). DB 사용자 3명, 정답 정책 63개와 해당 `rag_documents` 청크 63개가 확인됐고, 사용자/정책 fingerprint는 인수인계 문서의 값과 일치했다. `/rag/ready`는 `index_ready=true`, `index_source=cache`였다. 강제 재색인 없이 아래 유료 명령을 각각 한 번만 실행했고 둘 다 정상 종료했다. 실패 문항 재시도는 없었다.

```powershell
uv run --no-sync python -m src.evaluation.run_evaluation --mode policy --suite holdout250 --user-source db --k 5 --output evaluation/results/policy_guardrail_holdout250_0912.json
uv run --no-sync python -m src.evaluation.run_evaluation --mode graph --suite holdout250 --user-source db --output evaluation/results/tax_roadmap_holdout250_0912.json
```

원시 결과: [정책·Guardrail](../../LLM/evaluation/results/policy_guardrail_holdout250_0912.json), [세금·로드맵](../../LLM/evaluation/results/tax_roadmap_holdout250_0912.json). 전체 250단위는 정책·Guardrail 126문항과 그래프 124턴이다. 아래의 **전체 통과 195/250(78.0%)**은 Guardrail 정분류 63건, 정책 정답 *전부*가 상위 5개에 포함된 34건, 그래프 통과 98턴을 합친 보고용 합성 지표다. 정책 검색의 공식 연속형 지표 및 그래프 시나리오 통과율과 혼동해서는 안 된다. 합성 기준의 실패는 정책 부분/완전 누락 29건과 그래프 실패 26턴, 총 55단위다.

## 상세 결과 1 — Guardrail과 정책 검색

| 지표 | 결과 | 분모 |
| --- | ---: | ---: |
| Guardrail TP / FP / TN / FN | 63 / 0 / 63 / 0 | 126문항 |
| Precision / Recall / F1 / Accuracy | 1.000 / 1.000 / 1.000 / 1.000 | 양성 63, 음성 63 |
| 정책 검색 진입률 | 1.000 | 허용 정책 문항 63/63 |
| 종단 간 P@5 / R@5 / MRR / MAP | 0.165 / 0.643 / 0.664 / 0.565 | 정책 63문항 |
| Guardrail 통과 조건부 P@5 / R@5 / MRR / MAP | 0.165 / 0.643 / 0.664 / 0.565 | 차단되지 않은 정책 63문항 |
| 정책 정답 전부 검색 / 일부만 검색 / 전부 누락 | 34 / 13 / 16 | 정책 63문항 |

종단 간 값은 허용 정책 63개 전체를 분모로, 조건부 값은 Guardrail 통과 63개를 분모로 산술평균했다. 이번 실행에는 정책 오차단이 없어 두 지표가 같다. Guardrail 네 유형은 `hard_block` 21/21, `semantic_domain_background` 21/21, `semantic_plain` 14/14, `prompt_privacy` 7/7 차단됐다. 정책·Guardrail 결과의 `failure_reasons`는 `out_of_scope=63`, `insufficient_evidence=0`, `generation_validation_failed=0`이다. 여기서 `out_of_scope` 63건은 기대한 차단이며 실패가 아니다.

| 정책 질문 표현 유형 | 문항 | P@5 | R@5 | MRR | MAP |
| --- | ---: | ---: | ---: | ---: | ---: |
| short | 16 | 0.225 | 0.844 | 0.802 | 0.708 |
| standard | 16 | 0.138 | 0.531 | 0.562 | 0.469 |
| long_context | 16 | 0.162 | 0.688 | 0.719 | 0.609 |
| noisy | 15 | 0.133 | 0.500 | 0.567 | 0.467 |
| explicit_profile | 32 | 0.194 | 0.766 | 0.760 | 0.659 |
| implicit_profile | 31 | 0.135 | 0.516 | 0.565 | 0.468 |
| single_relevant | 42 | 0.138 | 0.690 | 0.591 | 0.591 |
| multi_relevant | 21 | 0.219 | 0.548 | 0.810 | 0.512 |

표현·프로필·정답 수는 서로 다른 분할 축이므로 행을 합산하지 않는다.

| DB 사용자 | 정책 문항 | P@5 | R@5 | MRR | MAP |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 21 | 0.181 | 0.714 | 0.786 | 0.643 |
| 2 | 21 | 0.143 | 0.548 | 0.444 | 0.421 |
| 4 | 21 | 0.171 | 0.667 | 0.762 | 0.631 |

전체 250턴의 사용자 배분은 ID 1=84, ID 2=84, ID 4=82이다. 위 사용자 표의 분모는 그중 정책 검색 문항만이다.

## 상세 결과 2 — 세금과 로드맵 대화

| 범위 | 턴 통과 | 시나리오 통과 | route | status | block | grounded | 필수 문구 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 세금 | 41/62 (66.1%) | 18/31 (58.1%) | 62/62 | 41/62 | 62/62 | 48/62 | 1/1 |
| 로드맵 | 57/62 (91.9%) | 27/31 (87.1%) | 62/62 | 57/62 | 57/62 | 62/62 | 16/18 |
| 합계 | 98/124 (79.0%) | 45/62 (72.6%) | 124/124 | 98/124 | 119/124 | 110/124 | 17/19 |

`필수 문구`는 해당 check가 설정된 턴만 분모다. `answer_length`는 설정된 모든 턴에서 통과했다. 그래프 `failure_reasons`는 `out_of_scope=25`, `insufficient_evidence=2`, `generation_validation_failed=0`이며, 차단 사유 수 자체가 실패 수는 아니다.

| 세금 유형 | 턴 통과 | 시나리오 통과 | status | block | grounded |
| --- | ---: | ---: | ---: | ---: | ---: |
| calculation | 16/20 | 8/10 | 16/20 | 20/20 | 20/20 |
| legal_evidence | 4/18 | 1/9 | 4/18 | 18/18 | 4/18 |
| need_more_info | 9/12 | 3/6 | 9/12 | 12/12 | 12/12 |
| unsupported_year | 6/6 | 3/3 | 6/6 | 6/6 | 6/6 |
| out_of_scope | 6/6 | 3/3 | 6/6 | 6/6 | 6/6 |

| 로드맵 단계 | 턴 통과 | 시나리오 통과 | status | block | grounded | 필수 문구 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 10/10 | 5/5 | 10/10 | 10/10 | 10/10 | 2/2 |
| B | 7/8 | 3/4 | 7/8 | 7/8 | 8/8 | 1/2 |
| C | 10/10 | 5/5 | 10/10 | 10/10 | 10/10 | 3/3 |
| D | 7/8 | 3/4 | 7/8 | 7/8 | 8/8 | 2/2 |
| E | 5/8 | 2/4 | 5/8 | 5/8 | 8/8 | 2/3 |
| F | 8/8 | 4/4 | 8/8 | 8/8 | 8/8 | 3/3 |
| Z | 10/10 | 5/5 | 10/10 | 10/10 | 10/10 | 3/3 |

세금 계산 시나리오 10개의 2턴에는 Python 계산기 reference가 있으나 `/rag/chat`가 구조화된 계산 유형·결과를 노출하지 않는다. 따라서 위 통과율은 route/status/차단/grounded/필수 문구 등 evaluator의 *관찰 가능한 자동 check*에 한정되며 계산값 정확도를 뜻하지 않는다. 원문 답변·reference 대조는 별도 수동 감사가 필요하고 이번 자동 지표에는 포함하지 않았다.

## 상세 결과 3 — 실패 ID와 관찰된 현상

정책 검색 완전 누락(R@5=0, 16건): `holdout-policy-online-invest-meetup`, `holdout-policy-seoul-tech-consulting`, `holdout-policy-seoul-success-school`, `holdout-policy-influencer-sales`, `holdout-policy-anyang-interest-support`, `holdout-policy-restart-guarantee`, `holdout-policy-workplace-improvement`, `holdout-policy-management-improvement`, `holdout-policy-gyeonggi-business-card`, `holdout-policy-food-export-expo`, `holdout-policy-restaurant-facility-loan`, `holdout-policy-youth-food-hub`, `holdout-policy-small-export-shipping`, `holdout-policy-regional-sme-award`, `holdout-policy-small-business-fund`, `holdout-policy-social-economy-fund`.

정책 일부 누락(0<R@5<1, 13건): `holdout-policy-cloud-open-innovation`, `holdout-policy-software-project-finance`, `holdout-policy-seoul-tourism-tech`, `holdout-policy-seoul-incubation-space`, `holdout-policy-seoul-center-options`, `holdout-policy-ip-prototype-training`, `holdout-policy-suwon-guarantees`, `holdout-policy-export-translation-shipping`, `holdout-policy-startup-interest-options`, `holdout-policy-consulting-options`, `holdout-policy-stability-funds`, `holdout-policy-japan-market`, `holdout-policy-local-digital-options`.

세금 실패 시나리오 13개: `holdout-tax-startup-seoul`(1·2턴 status), `holdout-tax-startup-jeonnam`(1·2턴 status), `holdout-tax-business-transfer`(1턴 status·grounded), `holdout-tax-bookkeeping-penalty`(1·2턴 status·grounded), `holdout-tax-business-expense`(1·2턴 status·grounded), `holdout-tax-invoice-issue`(1·2턴 status·grounded, 2턴 insufficient_evidence), `holdout-tax-bad-debt-credit`(2턴 status·grounded, insufficient_evidence), `holdout-tax-withholding-deadline`(1·2턴 status·grounded), `holdout-tax-corporate-expense`(1·2턴 status·grounded), `holdout-tax-startup-reduction-law`(1·2턴 status·grounded), `holdout-tax-missing-family`(1턴 status), `holdout-tax-missing-region`(2턴 status), `holdout-tax-missing-input-tax`(1턴 status).

로드맵 실패 시나리오 4개: `holdout-roadmap-registration-policy`(2턴 status·block·필수 문구), `holdout-roadmap-loan-tax`(1턴 status·block, out_of_scope), `holdout-roadmap-reduction-docs`(1·2턴 status·block, out_of_scope), `holdout-roadmap-reduction-rate`(2턴 status·block·필수 문구). 원시 그래프 결과에는 check별 참/거짓과 guardrail 사유만 있고 실제 응답 본문·관찰 status 값은 없다. 따라서 위 내용은 관찰 가능한 실패 유형이며, 검색/응답의 더 깊은 원인을 단정하지 않는다.

## 사전 성공 기준 재확인과 후속 원칙

| 기준 | 관찰 | 판정 |
| --- | ---: | --- |
| Guardrail Precision ≥ 0.80, Recall ≥ 0.90 | 1.000, 1.000 | 통과 |
| 정책 검색 진입률 ≥ 0.90 | 1.000 | 통과 |
| 조건부 R@5 ≥ 0.65 | 0.643 | 미달 |
| 종단 간 R@5 ≥ 0.70 | 0.643 | 미달 |
| 로드맵 턴 통과율 ≥ 0.90 | 0.919 | 통과 |
| 세금 턴 통과율 ≥ 0.60 | 0.661 | 통과 |

이 홀드아웃으로 로직을 조정하거나 재평가하지 않는다. 후속 개선은 `legacy80` 또는 별도 개발셋에서 하고, 다음 검증은 새 홀드아웃으로 수행한다.
