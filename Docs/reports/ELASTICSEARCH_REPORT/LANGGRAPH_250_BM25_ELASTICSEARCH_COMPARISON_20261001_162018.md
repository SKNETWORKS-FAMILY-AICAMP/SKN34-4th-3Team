# LangGraph 신규 250개 평가셋 — 기본 BM25와 Elasticsearch 고도화 방식 비교

기본 BM25 방식으로 신규 평가셋 전체 250개 평가 단위를 격리 환경에서 평가하고, 이미 완료된 Elasticsearch 평가 결과와 비교했습니다. **후보 수가 같은 정책 평가에서 두 방식의 Hit@5는 모두 54/63(85.7%)입니다.** 이번 결과만으로 Elasticsearch 고도화 방식이 기본 BM25보다 정책 적중률을 높였다고 설명할 수는 없습니다.

Elasticsearch 결과는 정책 후보 40개 평가와 기존 전체 평가를 재사용했습니다. 추가로 시작했던 Elasticsearch 재평가는 사용자 요청에 따라 중단했으며 이 보고서의 수치에 사용하지 않았습니다.

## 1. 평가 범위와 결과 출처

| 영역 | 기본 BM25 | Elasticsearch 고도화 방식 | 비교 조건 |
| --- | --- | --- | --- |
| 정책 63문항 | 이번 전체 평가 | 기존 15:39 실행의 정책 63문항 | 양쪽 RRF 후·Cohere 후보 40개 |
| 가드레일 63문항 | 이번 전체 평가 | 기존 14:18 실행의 전체 평가 | 검색 적중률과 별도 평가 |
| 세금 62턴 | 이번 전체 평가 | 기존 14:18 실행의 전체 평가 | 기본 후보 40개 / Elasticsearch 후보 20개 |
| 로드맵 62턴 | 이번 전체 평가 | 기존 14:18 실행의 전체 평가 | 서로 다른 실행 결과의 참고 비교 |
| 합계 | 250개 평가 단위 | 기존 결과에서 250개 평가 단위 구성 | Elasticsearch는 두 실행의 결과를 조합 |

- 기본 BM25: 2026-10-01 16:20:31~16:50:59 KST, 실행 ID `20261001_162018`.
- Elasticsearch 정책: 2026-10-01 15:39:44~15:49:14 KST, 실행 ID `20261001_153944`.
- Elasticsearch 전체: 2026-10-01 14:18:48~14:48:09 KST, 실행 ID `20261001_141848`.

세금·로드맵은 각 31개 시나리오, 시나리오당 2턴입니다. 기본 BM25는 126개 정책·가드레일 문항과 124개 대화 턴을 모두 완료했습니다. 세금의 후보 수가 다르므로 대화 결과 차이를 검색 방식만의 효과로 해석할 수 없습니다.

## 2. 검색 방식과 공통 설정

| 항목 | 기본 BM25 | Elasticsearch 고도화 방식 |
| --- | --- | --- |
| 희소 검색 | 기존 `BM25Search` 구현 | 기존 `ElasticsearchBM25Search` 구현 |
| 분석 방식 | 단어 및 문자 bigram | Nori 형태소 분석 기반 색인 |
| 문서 단위 | Elasticsearch와 맞춘 원본 문서 단위 | 원본 문서 단위 |
| 기본 BM25 파라미터 | k1=1.5, b=0.75 | 기존 Elasticsearch 설정 유지 |
| Dense 검색 | 기존 PostgreSQL 벡터 검색 | 기존 PostgreSQL 벡터 검색 |
| 결합 방식 | 기존 원본 문서 단위 RRF | 기존 원본 문서 단위 RRF |
| RRF 상수 | 60 | 60 |
| 검색 pool 설정 | 40 | 40 |
| Cohere 정책 후보 | 40 | 40 |
| 최종 평가 k | 5 | 5 |
| LLM | gpt-6-luna | gpt-6-luna |
| 임베딩 | text-embedding-3-small | text-embedding-3-small |
| 재정렬 모델 | rerank-v4.0-fast | rerank-v4.0-fast |
| 최소 관련성 점수 | 0.2 | 0.2 |
| 세금 최대 hop | 3 | 3 |
| 세금 캐시 | false | false |

기본 BM25는 기존 코드의 검색 점수 계산을 사용하되, 비교를 위해 Elasticsearch와 같은 원본 문서 단위로 구성했습니다. 따라서 과거 청크 단위 BM25 파이프라인 전체를 복원한 결과는 아닙니다. Dense 검색, RRF, 재정렬, 생성 및 평가 로직은 기존 구현을 재사용했습니다.

격리 평가 시작 시 DB 원본 14,550개와 Elasticsearch 색인의 문서 ID·내용 전체가 일치함을 확인했습니다. 기존 벡터 청크 18,481개를 재사용했고 재색인·임베딩 생성은 수행하지 않았습니다. 평가셋 SHA256과 사용자 프로필·정책 fingerprint가 기존 Elasticsearch 실행의 검증 기록과 일치합니다.

평가셋 SHA256: `c18685be25eee88e0593070cdc726ce04361bbd230b689b09af073c2da9bbdd0`.

## 3. 정책 검색 성능 — 동일 후보 40개

| 지표 | 기본 BM25 | Elasticsearch 고도화 방식 | Elasticsearch − 기본 |
| --- | ---: | ---: | ---: |
| Hit@5 | 54/63 (85.7%) | 54/63 (85.7%) | 0문항 / 0.0%p |
| Precision@5 | 19.7% | 19.7% | 0.0%p |
| Recall@5 | 78.6% | 77.8% | −0.8%p |
| MRR | 0.812 | 0.787 | −0.025 |
| MAP@5 | 0.743 | 0.713 | −0.030 |
| 정책 평균 응답 시간 | 7.23초 | 9.03초 | +1.81초 |
| insufficient_evidence | 1문항 | 1문항 | 0문항 |
| generation_validation_failed | 0문항 | 0문항 | 0문항 |

정책 지표는 **최종 API 응답의 `sources[].policy_id` 상위 5개**를 정답 정책 ID와 비교합니다. Hit@5는 정답 정책을 하나 이상 인용한 문항 비율입니다. Recall@5는 문항별 정답 정책 중 인용한 비율의 평균이며, Precision@5는 k=5를 분모로 사용하므로 Hit@5와 값이 다릅니다. 검색·재정렬·LLM 인용 선택이 함께 반영되는 지표입니다.

양쪽 적중 문항 수는 같지만 맞춘 질문은 일부 다릅니다. 양쪽 모두 적중 51문항, 기본 BM25만 적중 3문항, Elasticsearch만 적중 3문항, 양쪽 모두 미적중 6문항입니다. 각 방식의 미적중은 9문항입니다.

| 질문 case ID | 정답 정책 ID | 기본 BM25 최종 인용 | Elasticsearch 최종 인용 | 적중 방식 |
| --- | --- | --- | --- | --- |
| holdout-policy-ai-commercialization-investment | 571, 916 | 3026, 3307, 881 | 571 | Elasticsearch |
| holdout-policy-seoul-incubation-options | 757, 16 | 2981, 3385, 757 | 2981, 3313, 94 | 기본 BM25 |
| holdout-policy-food-facility-loan | 2264 | 622, 2322, 2387, 2302, 1376 | 622, 2264 | Elasticsearch |
| holdout-policy-onsite-consulting | 1638 | 1638, 549 | 549 | 기본 BM25 |
| holdout-policy-youth-culture | 271 | 271 | 297, 2604 | 기본 BM25 |
| holdout-policy-hiring-fund-package | 3097, 1742 | 1636 | 2734, 3097, 1636 | Elasticsearch |

평균 응답 시간은 정책 63문항만 대상으로 계산했습니다. 기본 평가의 정책·가드레일 합산 평균 4.05초를 정책 검색 시간으로 사용하지 않았습니다. 기본 평가에는 프로세스 내부 ASGI 호출, 기존 Elasticsearch 평가에는 HTTP 호출을 사용했고 실행 시각도 다릅니다. 응답 시간은 참고 수치이며 검색 엔진 자체의 속도 차이를 입증하지 않습니다.

## 4. 기본 BM25의 정책 단계별 정답 포함 여부

| 단계 | 정답 정책이 하나 이상 포함된 문항 |
| --- | ---: |
| Dense 후보 | 47/63 (74.6%) |
| 기본 BM25 후보 | 62/63 (98.4%) |
| RRF 후 후보 40개 | 57/63 (90.5%) |
| Cohere 정렬 후보 40개 | 57/63 (90.5%) |
| 최종 컨텍스트 Top-5 | 55/63 (87.3%) |
| 최종 답변 인용 | 54/63 (85.7%) |

각 행은 해당 단계 전체 후보 중 정답 포함 여부입니다. 원시 후보 단계는 최종 Hit@5와 후보 수가 다르므로 같은 지표로 비교하면 안 됩니다. 일부 정답은 RRF 및 Top-5 선택에서 제외되고, 마지막에는 LLM의 인용 선택까지 영향을 줍니다.

재사용한 Elasticsearch 후보 40개 실행에는 같은 단계별 추적 파일이 없으므로 단계별 검색 우열은 판정하지 않았습니다. 기존 후보 20개 추적이나 중단한 재평가의 추적을 후보 40개 결과에 섞지 않았습니다.

## 5. 가드레일

| 지표 | 기본 BM25 | 기존 Elasticsearch 전체 평가 |
| --- | ---: | ---: |
| 차단 대상 차단 | 63/63 | 63/63 |
| 정상 정책 질문 비차단 | 63/63 | 63/63 |
| 정확도 | 100.0% | 100.0% |
| Precision / Recall / F1 | 100.0% / 100.0% / 100.0% | 100.0% / 100.0% / 100.0% |

가드레일은 차단 여부 기준입니다. 정책 질문에 대한 근거 부족 응답과 요청 자체의 가드레일 차단은 별도로 평가합니다. 후보 40개 정책 전용 실행에는 차단 대상 63문항이 없으므로 가드레일 수치는 기존 전체 평가에서 가져왔습니다.

## 6. LangGraph 대화 — 기존 전체 결과와 참고 비교

**세금은 기본 BM25 후보 40개와 기존 Elasticsearch 후보 20개의 비교입니다. 아래 차이는 후보 수와 실행별 답변 변동을 포함하며 Elasticsearch 검색 방식만의 효과가 아닙니다.**

| 영역 | 기본 BM25 답변 통과 | 기존 Elasticsearch 답변 통과 | 통과 문항 차이 |
| --- | ---: | ---: | ---: |
| 세금 | 41/62 (66.1%) | 43/62 (69.4%) | +2턴 / +3.2%p |
| 로드맵 | 55/62 (88.7%) | 58/62 (93.5%) | +3턴 / +4.8%p |
| 합계 | 96/124 (77.4%) | 101/124 (81.5%) | +5턴 / +4.0%p |

| 영역 | 기본 BM25 시나리오 통과 | 기존 Elasticsearch 시나리오 통과 | 기본 평균 시간 | Elasticsearch 평균 시간 |
| --- | ---: | ---: | ---: | ---: |
| 세금 | 17/31 (54.8%) | 18/31 (58.1%) | 14.71초 | 13.65초 |
| 로드맵 | 25/31 (80.6%) | 27/31 (87.1%) | 3.28초 | 4.08초 |
| 합계 | 42/62 (67.7%) | 45/62 (72.6%) | 9.00초 | 8.87초 |

시나리오 통과는 두 턴을 모두 통과해야 인정합니다. 대화 통과는 route, status, 차단 여부, 근거 표시, 필수 문구, 답변 길이 등의 기존 자동 검사 기준입니다. 세금 계산 금액의 정확도나 정답 세무 문서 ID의 직접 적중률을 의미하지 않습니다.

| 자동 검사 | 기본 세금 | Elasticsearch 세금 | 기본 로드맵 | Elasticsearch 로드맵 |
| --- | ---: | ---: | ---: | ---: |
| route | 62/62 | 62/62 | 62/62 | 62/62 |
| status | 42/62 | 43/62 | 55/62 | 58/62 |
| block | 62/62 | 62/62 | 55/62 | 58/62 |
| grounded | 58/62 | 61/62 | 62/62 | 62/62 |
| required_phrases | 1/1 | 1/1 | 18/18 | 18/18 |
| answer_length | 해당 없음 | 해당 없음 | 62/62 | 62/62 |

자동 검사를 전부 통과한 턴만 답변 통과로 집계하므로 기본 세금의 status 통과 42턴과 최종 통과 41턴은 다를 수 있습니다. 로드맵의 답변 통과 차이 역시 검색 방식의 성능 향상 근거로 단정할 수 없습니다.

## 7. 실행 검증 및 운영 영향

기본 BM25는 별도 일회성 Docker 컨테이너에서 기존 Django·LangGraph를 호출했습니다. DB 연결은 `default_transaction_read_only=on`을 확인했고 운영 `.env`, 검색 기본값, LangGraph 코드를 변경하지 않았습니다. 운영 LLM 컨테이너의 ID와 시작 시각도 유지됨을 확인했습니다. 평가용 컨테이너는 중단·제거됐습니다.

기본 BM25 완료 기록의 검색·Cohere fallback·429·답변 생성 예외 카운터는 0건입니다. 재사용한 Elasticsearch 두 실행의 검증 기록도 같은 오류가 0건입니다. 모델 응답에 대한 자동 검증 실패는 정상 평가 결과에 포함했으며 오답을 제외하거나 점수 산정에서 숨기지 않았습니다.

기본 BM25의 전체 평가는 완료됐습니다. 중단한 Elasticsearch 추가 평가 결과는 사용하지 않았고, 기존 완료 결과의 파일과 실행 ID를 명시해 재사용했습니다.

## 8. 고도화 설명에 사용할 결론

Elasticsearch는 기존 BM25 희소 검색을 Nori 기반 색인·검색으로 고도화한 구현입니다. 구현상의 고도화와 해당 평가셋에서의 적중률 향상은 별도로 설명해야 합니다.

이번 신규 평가셋의 동일 후보 40개 정책 평가에서는 두 방식 모두 Hit@5 85.7%이며, Recall·MRR·MAP에서는 기본 BM25가 소폭 높았습니다. 따라서 이번 결과에 근거해 Elasticsearch가 정책 성능을 개선했다고 주장할 수 없습니다. 기존 Elasticsearch 대화 결과가 더 높지만 세금 후보 수와 실행 조건이 달라 검색 방식의 효과를 분리할 수 없습니다.

과거 평가셋의 약 92%와 이번 평가셋의 85.7%는 질문·정답 문서 구성이 다른 결과입니다. 이를 Elasticsearch 도입 효과나 문서 추가에 따른 성능 하락의 크기로 직접 환산할 수 없습니다. 이번 보고서는 새 평가셋에서 기본 BM25 기준선을 확보했고, Elasticsearch 고도화 방식이 최종 정책 적중률에서 동률임을 확인한 비교로 사용하는 것이 타당합니다.

## 9. 원본 결과 및 검증 기록

- [기본 BM25 정책·가드레일 JSON](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_162018_basic_bm25_policy.json)
- [기본 BM25 세금·로드맵 JSON](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_162018_basic_bm25_graph.json)
- [기본 BM25 정책 단계별 추적 JSON](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_162018_basic_bm25_stages.json)
- [비교 출처·DB·설정 검증 JSON](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_162018_comparison_validation.json)
- [기존 Elasticsearch 후보 40개 정책 JSON](../../../LLM/evaluation/results/holdout250_policy_candidates40_20261001_153944_policy.json)
- [기존 Elasticsearch 후보 40개 검증 JSON](../../../LLM/evaluation/results/holdout250_policy_candidates40_20261001_153944_validation_docs_record.json)
- [기존 Elasticsearch 전체 정책·가드레일 JSON](../../../LLM/evaluation/results/holdout250_newkey_20261001_141848_policy.json)
- [기존 Elasticsearch 전체 대화 JSON](../../../LLM/evaluation/results/holdout250_newkey_20261001_141848_graph.json)
- [기존 Elasticsearch 전체 검증 JSON](../../../LLM/evaluation/results/holdout250_newkey_20261001_141848_validation_docs_record.json)
