# 기본 BM25 대비 Elasticsearch Nori BM25 고도화 비교

평가 시작: 2026-10-02T09:06:24.032395+09:00 · 종료: 2026-10-02T10:04:16.265389+09:00 (한국시간).

## 전체 250개 평가 비교표

| 평가 영역 | 기본 BM25 | Elasticsearch 품사 가중 BM25 | 변화 |
| --- | ---: | ---: | ---: |
| 정책 최종 인용 Hit@5 | 53/63 (84.1%) | 50/63 (79.4%) | -3건 |
| 가드레일 차단 문항 통과 | 63/63 | 63/63 | +0건 |
| 세금 자동 검사 턴 통과 | 44/62 | 44/62 | +0건 |
| 로드맵 자동 검사 턴 통과 | 54/62 | 56/62 | +2건 |

서로 다른 자동 검사 기준의 영역을 합산해 하나의 전체 정확도로 계산하지 않았습니다.

## 평가 범위와 비교 조건

각 방식에서 신규 holdout250 전체 250개 평가 단위를 실행했습니다. 정책 63문항, 가드레일 63문항, 세금 62턴, 로드맵 62턴이며 사용자 ID 1·2·4의 실제 DB 프로필을 사용했습니다.

기본 방식은 저장소의 BM25Search(어절·문자 2-gram, k1=1.5, b=0.75)를 재사용했습니다. 고도화 방식은 현재 Elasticsearch Nori BM25이며 핵심 품사 토큰에 2.5배, 보조 품사 토큰에 0.5배 점수를 반영합니다. 두 방식 모두 같은 원본 문서 14,550개와 동일한 PostgreSQL Dense 검색을 사용합니다. 정책/원천 문서 단위 중복 제거·RRF 결합을 유지하며 각 검색 풀 40개, RRF·Cohere 후보 20개, RRF 상수 60, 최종 Top-5를 사용했습니다.

기존 요청 표현 정규화와 3번 백엔드별 최상위 순위 RRF를 두 방식 모두 적용했습니다. 같은 백엔드의 원문·개인화 검색 결과에서 동일 정책은 가장 높은 순위의 기여도만 반영합니다. 2번 복합 요구 분리는 적용하지 않았습니다. 세금의 RRF 결합은 기존 방식을 유지했습니다.

현재 운영 LangGraph의 독립 인스턴스를 별도 Docker 프로세스에서 실행했습니다. Django API는 ASGI로 프로세스 내부에서 호출했으며 운영 서버의 설정·프로세스·색인을 변경하지 않았습니다. DB 연결은 읽기 전용이고 세금 캐시는 OFF입니다. 모델·프롬프트·질문·프로필은 동일합니다.

품사 그룹은 Elasticsearch search analyzer가 반환한 Nori 토큰을 사용합니다. 현재 코드에서 추가된 NNB stoptag는 live index에는 아직 적용되지 않은 상태입니다. 문서 단위를 동일하게 맞춘 검색 백엔드 비교이므로 과거 청크 기반 BM25 파이프라인을 그대로 재현한 실험은 아닙니다. 두 방식의 토큰화·필드 처리·BM25 파라미터 차이를 포함한 키워드 검색 방식의 효과를 비교합니다.

## 정책 검색·가드레일

| 지표 | 기본 BM25 | 고도화 Elasticsearch Nori BM25 | 변화 |
| --- | ---: | ---: | ---: |
| Precision@5 | 19.0% | 18.1% | -1.0%p |
| Recall@5 | 76.2% | 72.2% | -4.0%p |
| Hit@5 | 53/63 (84.1%) | 50/63 (79.4%) | -3문항 |
| MRR | 0.788 | 0.743 | -0.045 |
| MAP@5 | 0.710 | 0.669 | -0.041 |
| 정책 평균 응답 시간 | 6.76초 | 5.98초 | -0.78초 |
| 전체 차단 여부 정확도 | 100.0% | 100.0% | +0.0%p |

최종 Hit@5는 답변 sources[].policy_id에 정답 정책이 하나 이상 포함됐는지 측정합니다. 검색뿐 아니라 답변 생성과 인용 선택까지 포함한 지표입니다.

### 검색 단계별 정답 포함

| 단계 | 기본 BM25 | 고도화 Elasticsearch |
| --- | ---: | ---: |
| Dense 검색 후보 | 47/63 | 47/63 |
| 키워드 검색 후보 | 62/63 | 55/63 |
| RRF 상위 20개 | 57/63 | 54/63 |
| Cohere 재정렬 후 상위 5개 | 55/63 | 52/63 |
| 최종 인용 | 53/63 | 50/63 |

## LangGraph 대화

| 영역 | 기본: 턴 통과 | 고도화: 턴 통과 | 기본/고도화 시나리오 통과 | 기본/고도화 평균 시간 |
| --- | ---: | ---: | --- | --- |
| 세금 | 44/62 (71.0%) | 44/62 (71.0%) | 18/31 · 19/31 | 14.18초 · 13.29초 |
| 로드맵 | 54/62 (87.1%) | 56/62 (90.3%) | 25/31 · 26/31 | 3.12초 · 3.11초 |
| 합계 | 98/124 (79.0%) | 100/124 (80.6%) | 43/62 · 45/62 | 8.65초 · 8.20초 |

대화 통과는 기존 route·status·차단 여부·grounded·필수 문구·답변 길이 자동 검사를 사용합니다. 세금 계산 금액이나 정답 세법 문서 ID를 직접 측정한 정확도가 아닙니다. 로드맵·가드레일은 키워드 검색 고도화의 직접 효과로 해석하지 않습니다.

## 문항별 변화

기본 방식 대비 고도화 방식에서 실패 → 성공 1건, 성공 → 실패 4건입니다.

- 실패 → 성공: holdout-policy-mokpo-interest
- 성공 → 실패: holdout-policy-prototype-equipment
- 성공 → 실패: holdout-policy-anyang-distribution
- 성공 → 실패: holdout-policy-stability-interest
- 성공 → 실패: holdout-policy-youth-founder-package

## 해석과 검증

고도화 방식의 최종 Hit@5 변화는 -4.8%p입니다. 고도화라는 명칭과 별개로 실제 지표가 좋아진 영역과 그렇지 않은 영역을 표에 모두 기재했습니다. 각 방식 1회 실행이므로 모델 응답 변동과 실행 순서의 영향이 포함될 수 있습니다. 구버전 평가셋의 92.1%와는 질문·정답 구성이 달라 직접 전후 비교하지 않습니다.

원본 문서 변경 없음: True · 평가셋 변경 없음: True · Elasticsearch alias 변경 없음: True.

- basic_bm25: 실행 오류 {'tax_intent_invalid_output': 1}, 키워드 검색 호출 187회
- elasticsearch: 실행 오류 {'tax_intent_invalid_output': 3}, 키워드 검색 호출 184회

## 원본 결과

- [basic_bm25 policy](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261002_090619_basic_bm25_policy.json)
- [basic_bm25 graph](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261002_090619_basic_bm25_graph.json)
- [basic_bm25 stages](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261002_090619_basic_bm25_stages.json)
- [elasticsearch policy](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261002_090619_elasticsearch_policy.json)
- [elasticsearch graph](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261002_090619_elasticsearch_graph.json)
- [elasticsearch stages](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261002_090619_elasticsearch_stages.json)
- [실행 검증 JSON](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261002_090619_validation.json)
