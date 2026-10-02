# 기본 BM25 대비 Elasticsearch Nori BM25 고도화 비교

평가 시작: 2026-10-01T22:40:36.655116+09:00 · 종료: 2026-10-01T23:51:26.417208+09:00 (한국시간).

## 전체 250개 평가 비교표

| 평가 영역 | 기본 BM25 | Elasticsearch Nori BM25 | 변화 |
| --- | ---: | ---: | ---: |
| 정책 최종 인용 Hit@5 | 59/63 (93.7%) | 57/63 (90.5%) | -2건 |
| 가드레일 차단 문항 통과 | 63/63 (100.0%) | 63/63 (100.0%) | +0건 |
| 세금 자동 검사 턴 통과 | 45/62 (72.6%) | 43/62 (69.4%) | -2건 |
| 로드맵 자동 검사 턴 통과 | 57/62 (91.9%) | 56/62 (90.3%) | -1건 |
| 정책 평균 응답 시간 | 7.35초 | 6.83초 | -0.52초 |

서로 다른 검사 기준을 쓰는 네 영역을 합산해 하나의 전체 정확도로 계산하지 않았습니다. 세금·로드맵의 통과는 기존 대화 자동 검사 기준이며 정답 금액·세법 문서의 정확도를 직접 측정한 지표가 아닙니다.

## 평가 범위와 비교 조건

각 방식에서 신규 holdout250 전체 250개 평가 단위를 실행했습니다. 정책 63문항, 가드레일 63문항, 세금 62턴, 로드맵 62턴이며 사용자 ID 1·2·4의 실제 DB 프로필을 사용했습니다.

기본 방식은 저장소의 BM25Search(어절·문자 2-gram, k1=1.5, b=0.75)를 재사용했습니다. 고도화 방식은 현재 Elasticsearch Nori BM25입니다. 두 방식 모두 같은 원본 문서 14,550개와 동일한 PostgreSQL Dense 검색을 사용합니다. 정책/원천 문서 단위 중복 제거·RRF 결합을 유지하며 각 검색 풀 40개, RRF·Cohere 후보 20개, RRF 상수 60, 최종 Top-5를 사용했습니다.

1번 요청 표현 정리와 3번 백엔드별 최상위 순위 RRF를 두 방식 모두 적용했습니다. 같은 백엔드의 원문·개인화 검색 결과에서 동일 정책은 가장 높은 순위의 기여도만 반영합니다. 2번 복합 요구 분리는 적용하지 않았습니다. 세금의 RRF 결합은 기존 방식을 유지했습니다.

현재 운영 LangGraph의 독립 인스턴스를 별도 Docker 프로세스에서 실행했습니다. Django API는 ASGI로 프로세스 내부에서 호출했으며 운영 서버의 설정·프로세스·색인을 변경하지 않았습니다. DB 연결은 읽기 전용이고 세금 캐시는 OFF입니다. 모델·프롬프트·질문·프로필은 동일합니다.

문서 단위를 동일하게 맞춘 검색 백엔드 비교이므로 과거 청크 기반 BM25 파이프라인을 그대로 재현한 실험은 아닙니다. 두 방식의 토큰화·필드 처리·BM25 파라미터 차이를 포함한 키워드 검색 방식의 효과를 비교합니다.

## 정책 검색·가드레일

| 지표 | 기본 BM25 | 고도화 Elasticsearch Nori BM25 | 변화 |
| --- | ---: | ---: | ---: |
| Precision@5 | 21.9% | 21.0% | -1.0%p |
| Recall@5 | 86.5% | 82.5% | -4.0%p |
| Hit@5 | 59/63 (93.7%) | 57/63 (90.5%) | -2문항 |
| MRR | 0.913 | 0.869 | -0.044 |
| MAP@5 | 0.845 | 0.794 | -0.052 |
| 정책 평균 응답 시간 | 7.35초 | 6.83초 | -0.52초 |
| 전체 차단 여부 정확도 | 100.0% | 100.0% | +0.0%p |

최종 Hit@5는 답변 sources[].policy_id에 정답 정책이 하나 이상 포함됐는지 측정합니다. 검색뿐 아니라 답변 생성과 인용 선택까지 포함한 지표입니다.

### 검색 단계별 정답 포함

| 단계 | 기본 BM25 | 고도화 Elasticsearch |
| --- | ---: | ---: |
| Dense 검색 후보 | 51/63 | 51/63 |
| 키워드 검색 후보 | 62/63 | 61/63 |
| RRF 상위 20개 | 60/63 | 59/63 |
| Cohere 재정렬 후 상위 5개 | 59/63 | 57/63 |
| 최종 인용 | 59/63 | 57/63 |

## LangGraph 대화

| 영역 | 기본: 턴 통과 | 고도화: 턴 통과 | 기본/고도화 시나리오 통과 | 기본/고도화 평균 시간 |
| --- | ---: | ---: | --- | --- |
| 세금 | 45/62 (72.6%) | 43/62 (69.4%) | 19/31 · 18/31 | 14.68초 · 15.61초 |
| 로드맵 | 57/62 (91.9%) | 56/62 (90.3%) | 26/31 · 25/31 | 3.22초 · 3.87초 |
| 합계 | 102/124 (82.3%) | 99/124 (79.8%) | 45/62 · 43/62 | 8.95초 · 9.74초 |

대화 통과는 기존 route·status·차단 여부·grounded·필수 문구·답변 길이 자동 검사를 사용합니다. 세금 계산 금액이나 정답 세법 문서 ID를 직접 측정한 정확도가 아닙니다. 로드맵·가드레일은 키워드 검색 고도화의 직접 효과로 해석하지 않습니다.

## 문항별 변화

기본 방식 대비 고도화 방식에서 실패 → 성공 0건, 성공 → 실패 2건입니다.

- 성공 → 실패: holdout-policy-tech-competitiveness
- 성공 → 실패: holdout-policy-onsite-consulting

## 해석과 검증

고도화 방식의 최종 Hit@5 변화는 -3.2%p입니다. 고도화라는 명칭과 별개로 실제 지표가 좋아진 영역과 그렇지 않은 영역을 표에 모두 기재했습니다. 각 방식 1회 실행이므로 모델 응답 변동과 실행 순서의 영향이 포함될 수 있습니다. 구버전 평가셋의 92.1%와는 질문·정답 구성이 달라 직접 전후 비교하지 않습니다.

원본 문서 변경 없음: True · 평가셋 변경 없음: True · Elasticsearch alias 변경 없음: True.

- basic_bm25: 실행 오류 {'tax_intent_invalid_output': 2}, 키워드 검색 호출 0회 (재개 이후 측정값)
- elasticsearch: 실행 오류 {'tax_intent_invalid_output': 2}, 키워드 검색 호출 179회

기본 BM25 세금 41번째 턴에서 LLM의 계산 필요 여부와 계산 종류가 모순되는 출력 오류가 발생했습니다. 이 턴은 성공할 때까지 재시도하지 않았고 실패로 반영했습니다. 중단 전에 관측값이 저장되지 않아 오류 로그와 코드의 고정 오류 응답으로 복원했습니다. 해당 턴의 시간 4.83초는 로그에 남은 세금 노드 처리 시간이며 전체 API 시간은 아닙니다. 완료된 166개 응답은 평가 체크포인트에서 재사용했으며, 응답 캐시를 활성화한 것이 아닙니다. 이후 모델의 같은 의미적 오류는 실패 응답으로 기록하고 평가를 계속합니다. 통신·검색·재정렬 예외가 발생하면 계속 중단합니다.

## 원본 결과

- [basic_bm25 policy](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_224034_basic_bm25_policy.json)
- [basic_bm25 graph](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_224034_basic_bm25_graph.json)
- [basic_bm25 stages](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_224034_basic_bm25_stages.json)
- [elasticsearch policy](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_224034_elasticsearch_policy.json)
- [elasticsearch graph](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_224034_elasticsearch_graph.json)
- [elasticsearch stages](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_224034_elasticsearch_stages.json)
- [실행 검증 JSON](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_224034_validation.json)

세금 분류 모델의 모순된 출력 오류는 기본 BM25 2건, Elasticsearch 2건이며 모두 자동 검사 실패로 반영했습니다. 검색·Cohere 통신 예외는 발생하지 않았습니다.

## 실행 관측 기록

- [기본 BM25 문항별 관측 및 실패 복원 표시](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_224034_basic_bm25_observations.jsonl)
- [Elasticsearch 문항별 관측](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_224034_elasticsearch_observations.jsonl)
- [오류·처리 시간 로그](../../../LLM/evaluation/results/holdout250_bm25_vs_elasticsearch_20261001_224034_server.log)
