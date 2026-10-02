# 정책 63문항: Elasticsearch RRF 가중치 1.0과 1.3 비교

정책 검색에서 Dense의 RRF 기여도는 1.0으로 두고 Elasticsearch BM25의 기여도만 1.0에서 1.3으로 바꿔 평가했다. 기존과 동일하게 라우팅, 개인화, Dense/Elasticsearch 검색, RRF, Cohere를 실행하고 최종 답변 생성 직전에 중단했다. 양쪽 모두 RRF·Cohere 후보 20개, 검색 pool 40개, 캐시 비활성화다.

| 지표 | 기존 1.0 | 실험 1.3 | 변화 |
| --- | ---: | ---: | ---: |
| Top-5 Hit | 52/63 (82.5%) | 50/63 (79.4%) | -2문항 (-3.2%p) |
| Precision@5 | 19.0% | 18.4% | -0.6%p |
| Recall@5 | 75.4% | 72.2% | -3.2%p |
| MRR | 0.724 | 0.684 | -0.040 |
| MAP@5 | 0.666 | 0.625 | -0.040 |
| Dense 후보 정답 포함 | 46/63 | 46/63 | 0 |
| Elasticsearch 후보 정답 포함 | 56/63 | 56/63 | 0 |
| RRF 20개 정답 포함 | 53/63 | 51/63 | -2문항 |
| 평균 답변 생성 전 처리 시간 | 2.39초 | 2.66초 | +0.27초 |

처리 시간은 각각 한 번 측정한 값으로 네트워크 및 모델 응답 변동이 포함된다. 후보 수는 동일하므로 이 차이를 가중치의 지연 효과로 단정하지 않는다.

## 적중 상태가 바뀐 네 문항

| 문항 | 정답 정책 ID | 1.0 RRF → Cohere 순위 | 1.3 RRF → Cohere 순위 | 결과 |
| --- | ---: | --- | --- | --- |
| `holdout-policy-jeonnam-sme-funds` | 1904 | 후보 밖 | 19위 → 4위 | 새로 적중 |
| `holdout-policy-prototype-equipment` | 3136 | 18위 → 1위 | 후보 밖 | 적중 상실 |
| `holdout-policy-seoul-startup-education` | 784 | 8위 → 5위 | 후보 밖 | 적중 상실 |
| `holdout-policy-anyang-distribution` | 1417 | 19위 → 1위 | 후보 밖 | 적중 상실 |

새로 적중한 정책 1904는 Elasticsearch 후보에만 있었다. 적중을 잃은 세 정책은 Dense 후보에만 있었다. 세 문항에서 정답이 빠진 지점은 Cohere 이전의 RRF 20개 절단이다.

두 실행 모두 63문항을 완료했고 데이터셋 SHA-256 및 DB 검증 결과가 같았다. 질문·개인화 검색어와 Elasticsearch 후보 목록은 모든 문항에서 동일했다. Dense 후보의 순서 또는 목록은 6문항에서 조금 달랐지만, 위 네 문항에서는 동일했다. 최종 답변 생성 호출과 오류·fallback은 양쪽 모두 0건이었다.

**판단:** 이 평가셋에서 1.3은 개선되지 않았다. 운영 기본 가중치 1.0을 유지한다. 이 평가셋의 실패 사례를 보고 선택한 값이므로, 다른 값의 성능 주장에도 별도의 미사용 평가 문항이 필요하다.

- [기존 1.0 평가 보고서](../../../LLM/evaluation/results/policy63_pre_answer_20261001_200558.md) · [원본 JSON](../../../LLM/evaluation/results/policy63_pre_answer_20261001_200558.json)
- [실험 1.3 평가 보고서](../../../LLM/evaluation/results/policy63_pre_answer_20261001_204940.md) · [원본 JSON](../../../LLM/evaluation/results/policy63_pre_answer_20261001_204940.json)
