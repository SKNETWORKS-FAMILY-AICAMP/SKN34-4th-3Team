# Nori Hybrid 검색 개선 최종 보고서

## 1. 평가 범위

- 평가셋: 동일한 정책 검색 질문 63개
- 정답: 기존 `relevant_policy_ids` 유지
- 평가 단위: 중복을 제거한 고유 `policy_id`
- 최종 검색 흐름: Dense Top-40 + Nori BM25 Top-40 → policy-level RRF Top-20 → Cohere Rerank → Top-5
- 최종 Nori 설정: `decompound_mode=mixed`, 사용자 사전 없음, `XSV/XSA` 제거, `cross_fields`, `minimum_should_match=25%`

이 결과는 개발 과정에서 반복 사용한 63문항에 대한 결과이며, 새로운 홀드아웃 평가셋의 일반화 성능은 아니다.

## 2. 개선 흐름

### 2.1 최초 Elasticsearch Nori Hybrid

최초에는 PostgreSQL Dense 검색과 Elasticsearch Nori BM25를 RRF로 결합하고 Cohere로 재정렬했다. 초기 결과는 기존 Memory BM25 Hybrid보다 낮았다.

| 단계 | Recall@5 | MRR | MAP@5 | Hit@5 |
|---|---:|---:|---:|---:|
| Rerank 전 Nori Hybrid | 0.5794 | 0.5230 | 0.4667 | 0.6349 |
| Cohere Rerank 후 | 0.7143 | 0.7143 | 0.6349 | 0.7937 |

이 단계에서는 Elasticsearch의 문서와 PostgreSQL의 청크가 후보 수를 서로 다르게 소모할 가능성이 확인됐다. 따라서 이후 평가는 문서 20개가 아니라 고유 정책 20개를 확보하도록 수정했다.

근거: [policy63_retrieval_ab.md](../../../LLM/evaluation/results/policy63_retrieval_ab.md)

### 2.2 후보 공정성 보정과 Nori POS v2 기준선

Dense는 `policy_id`별 최고 점수 청크를 선택하고, Elasticsearch는 `policy_id` collapse를 사용하도록 변경했다. RRF도 동일 정책의 여러 청크를 한 번만 계산하도록 통일했다.

| 단계 | Recall@20 | Hit@20 | Recall@5 | MRR | MAP@5 | Hit@5 |
|---|---:|---:|---:|---:|---:|---:|
| Nori Hybrid | 0.7619 | 0.8254 | 0.6667 | 0.5685 | 0.5036 | 0.7460 |
| Cohere Rerank 후 | - | - | 0.7222 | 0.7169 | 0.6402 | 0.7937 |

이 결과를 이후 개선의 공정한 기준선으로 사용했다.

근거: [nori_v2_no_rerank.md](../../../LLM/evaluation/results/nori_v2_no_rerank.md), [nori_v2_with_rerank.md](../../../LLM/evaluation/results/nori_v2_with_rerank.md)

### 2.3 Query DSL을 `cross_fields`로 변경하고 MSM 탐색

제목과 본문을 분리 경쟁시키던 검색을 `cross_fields`로 변경하고 `minimum_should_match`를 10~50% 범위에서 탐색했다. 10~25%는 동일한 최고 성능이었고 30%부터 주요 지표가 하락했다. 동일 최고 구간 중 불필요한 토큰 매칭을 더 제한하는 25%를 선택했다.

| MSM | Recall@20 | Hit@20 | Recall@5 | MRR | MAP@5 | Hit@5 |
|---:|---:|---:|---:|---:|---:|---:|
| 10~25% | 0.8413 | 0.9206 | 0.7540 | 0.6656 | 0.5915 | 0.8413 |
| 30% | 0.8413 | 0.9206 | 0.7381 | 0.6418 | 0.5717 | 0.8254 |
| 40% | 0.7937 | 0.8730 | 0.6825 | 0.5571 | 0.5033 | 0.7619 |
| 50% | 0.7063 | 0.7619 | 0.5317 | 0.4455 | 0.3889 | 0.6032 |

근거: [nori_cross_fields_msm_sweep.md](../../../LLM/evaluation/results/nori_cross_fields_msm_sweep.md)

### 2.4 세금·법령 검색을 고려한 POS 보정

정책 검색뿐 아니라 향후 세금·법령 검색에도 같은 검색기를 사용할 수 있도록 제거 태그를 공격적으로 늘리지 않았다. 의미가 어근에 남는 파생 접미사 `XSV`, `XSA`만 추가 제거하고, 부정·범위·법적 조건에 영향을 줄 수 있는 `VX`, `VCN`, `MAG`, `MM`, `XPN`, `XSN`은 유지했다. 이 변경은 새 `nori-v3-xsv-xsa` 인덱스로 재색인했다.

Pool 20에서 `cross_fields + MSM 25% + XSV/XSA`를 적용한 결과는 다음과 같다.

| 단계 | Recall@20 | Hit@20 | Recall@5 | MRR | MAP@5 | Hit@5 |
|---|---:|---:|---:|---:|---:|---:|
| Rerank 전 | 0.8254 | 0.9048 | 0.7222 | 0.6426 | 0.5679 | 0.8095 |
| Cohere Rerank 후 | - | - | 0.7778 | 0.7751 | 0.6799 | 0.8730 |

POS 변경 전의 `cross_fields + MSM 25%` 결과와 비교하면 retrieval 지표는 소폭 하락했다. 따라서 이 단계의 향상을 `XSV/XSA` 단독 효과로 해석할 수는 없다. 다만 최초 공정 기준선보다 후보 Recall과 최종 Rerank 성능은 높았다.

근거: [nori_v3_xsv_xsa_msm25_with_rerank.md](../../../LLM/evaluation/results/nori_v3_xsv_xsa_msm25_with_rerank.md)

### 2.5 RRF 이전 후보 Pool 확대

최종 Rerank 후보는 Top-20으로 고정하고 Dense와 Nori가 RRF 전에 가져오는 고유 정책 수만 20, 30, 40, 50으로 변경했다. Cohere는 호출하지 않았다.

| Pool K | Recall@20 | Hit@20 | Recall@5 | Hit@5 | MRR | MAP@5 |
|---:|---:|---:|---:|---:|---:|---:|
| 20 | 0.8254 | 0.9048 | 0.7222 | 0.8095 | 0.6426 | 0.5679 |
| 30 | 0.8333 | 0.9206 | 0.7143 | 0.7937 | 0.6492 | 0.5780 |
| 40 | 0.8492 | 0.9365 | 0.7063 | 0.7937 | 0.6513 | 0.5770 |
| 50 | 0.8492 | 0.9365 | 0.6984 | 0.7778 | 0.6481 | 0.5754 |

Pool 20→40에서 Recall@20은 `+0.0238`, Hit@20은 `+0.0317` 증가했다. 40→50에서는 두 지표가 모두 증가하지 않았고 Top-5 지표는 오히려 하락했다. 따라서 포화 지점을 Pool 40으로 판단했다.

근거: [nori_candidate_pool_ab.md](../../../LLM/evaluation/results/nori_candidate_pool_ab.md)

### 2.6 Pool 40 최종 Cohere 검증

최종 구성은 Dense/Nori Top-40을 policy-level RRF로 결합한 Top-20을 Cohere `rerank-v4.0-fast`에 전달하고 Top-5를 반환하도록 확정했다.

| 단계 | Recall@20 | Hit@20 | Recall@5 | MRR | MAP@5 | Hit@5 |
|---|---:|---:|---:|---:|---:|---:|
| Nori Hybrid Rerank 전 | 0.8492 | 0.9365 | 0.7063 | 0.6513 | 0.5770 | 0.7937 |
| Nori Hybrid + Cohere | - | - | 0.8016 | 0.7817 | 0.6786 | 0.9048 |

목표였던 최종 Recall@5 `0.80` 이상을 `0.8016`으로 달성했다.

근거: [nori_v3_pool40_with_rerank.md](../../../LLM/evaluation/results/nori_v3_pool40_with_rerank.md)

## 3. 기존 검색 vs 최초 Nori vs 개선 Nori

- 기존 검색: Dense + Memory BM25 + policy-level RRF + Cohere
- 최초 Nori: Dense + 초기 Elasticsearch Nori BM25 + policy-level RRF + Cohere
- 개선 Nori: Dense/Nori Top-40 + 개선 Nori BM25 + policy-level RRF Top-20 + Cohere

### 3.1 최종 출력 성능: Cohere Rerank 후

| 지표 | 기존 검색 | 최초 Nori | 개선 Nori | 개선-기존 | 개선-최초 Nori |
|---|---:|---:|---:|---:|---:|
| Precision@5 | 0.1968 | 0.1778 | 0.2032 | +0.0063 | +0.0254 |
| Recall@5 | 0.7778 | 0.7143 | 0.8016 | +0.0238 | +0.0873 |
| MRR | 0.7228 | 0.7143 | 0.7817 | +0.0590 | +0.0675 |
| MAP@5 | 0.6500 | 0.6349 | 0.6786 | +0.0286 | +0.0437 |
| Hit@5 | 0.8571 | 0.7937 | 0.9048 | +0.0476 | +0.1111 |

개선 Nori는 최종 Recall@5 기준으로 기존 검색보다 `+0.0238`, 최초 Nori보다 `+0.0873` 높다. Hit@5는 기존 검색보다 `+0.0476`, 최초 Nori보다 `+0.1111` 높다.

### 3.2 Rerank 전 검색 성능

| 지표 | 기존 검색 | 최초 Nori | 개선 Nori | 개선-기존 | 개선-최초 Nori |
|---|---:|---:|---:|---:|---:|
| Precision@5 | 0.1619 | 0.1429 | 0.1746 | +0.0127 | +0.0317 |
| Recall@5 | 0.6587 | 0.5794 | 0.7063 | +0.0476 | +0.1270 |
| MRR | 0.5389 | 0.5230 | 0.6513 | +0.1124 | +0.1283 |
| MAP@5 | 0.4820 | 0.4667 | 0.5770 | +0.0950 | +0.1103 |
| Hit@5 | 0.7460 | 0.6349 | 0.7937 | +0.0476 | +0.1587 |

최초 실험은 RRF 이전 고유 정책 후보 수가 완전히 통제되지 않았으므로 Recall@20과 Hit@20의 직접 비교에서는 제외했다. 개선 Nori의 고유 정책 후보 성능은 Recall@20 `0.8492`, Hit@20 `0.9365`다.

## 4. 최종 결론

최종 성능 개선에 가장 직접적으로 기여한 변경은 다음 세 가지다.

1. 문서·청크 수가 아닌 고유 `policy_id`를 기준으로 후보를 구성해 실험과 RRF의 공정성을 확보했다.
2. `cross_fields + minimum_should_match=25%`로 제목과 본문을 하나의 검색 문맥으로 결합하고 과도한 Query 토큰 매칭을 제한했다.
3. RRF 이전 Dense/Nori 후보 Pool을 20에서 40으로 확대해 Cohere에 전달되는 Top-20의 Recall@20과 Hit@20을 높였다.

최종 설정은 후보 Recall@20 `0.8492`, 후보 Hit@20 `0.9365`, Cohere 이후 Recall@5 `0.8016`, Hit@5 `0.9048`을 기록했다. Pool 50은 후보 포괄률 개선 없이 Top-5 지표만 낮아졌으므로 Pool 40을 유지하는 것이 적절하다.
