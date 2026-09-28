# RAG 검색 고도화 및 근거 판단 경량화 계획서

## 1. 추진 배경 및 문제 정의

현재 서비스는 사용자의 정책·세금 관련 질문에 대해 RAG 검색을 수행한 뒤, 검색된 근거가 답변에 충분한지 LLM이 판단하도록 구성되어 있다.

현재 흐름은 다음과 같다.

```text
사용자 질문
    ↓
Dense + BM25 검색
    ↓
RRF
    ↓
Rerank
    ↓
LLM 근거 충분성 판단
    ↓
최종 답변 생성 또는 Fallback
```

이 구조에서 확인된 주요 문제는 다음 두 가지이다.

### 1.1 검색 품질 개선 필요

현재 검색 구조는 Dense 검색과 BM25 검색을 함께 사용하고 있으나, 한국어 정책 공고 및 세금 법령 문서는 다음과 같은 특징이 있다.

- 정책명, 지원대상, 업종, 지역, 지원유형 등 명확한 키워드가 중요함
- 조사·어미·복합명사가 많아 일반적인 토큰 단위 검색만으로는 검색 품질이 제한될 수 있음
- 법령명, 조문, 세액감면 명칭 등 정확한 용어 검색이 중요함

따라서 Dense 검색은 유지하되, 기존 BM25 영역을 **Elasticsearch + Nori 형태소 분석 + BM25** 구조로 강화하여 한국어 키워드 검색 성능을 개선할 필요가 있다.

### 1.2 LLM 근거 판단 단계의 응답 지연

현재 전체 챗봇 응답에 약 30초가 소요되는 사례에서, 검색된 근거가 충분한지 판단하는 LLM 단계가 약 20초를 차지하는 경우가 확인되었다.

즉 검색 이후의 근거 판단이 전체 응답속도의 주요 병목 구간이다.

현재 LLM은 검색 문서를 읽고 다음과 같은 결과를 반환한다.

```text
sufficient
insufficient
```

이 판단을 매 요청마다 LLM이 수행하기 때문에 서비스 응답시간과 API 비용이 증가한다.

따라서 기존 LLM Judge의 판단 데이터를 수집한 뒤, 이를 학습한 경량 머신러닝 분류 모델로 대체할 수 있는지 검증한다.

---

# 2. 개선 계획

전체 개선은 다음 두 단계로 진행한다.

```text
1단계
검색 구조 고도화

Dense + 기존 BM25
        ↓
Dense + Elasticsearch(Nori + BM25)

2단계
근거 충분성 판단 경량화

LLM Judge
        ↓
ML Classifier
```

---

## 2.1 1단계 — 검색 구조 고도화

### 기존 구조

```text
Dense Search
      +
기존 BM25
      ↓
RRF
      ↓
Rerank
```

### 개선 후보 구조

```text
Dense Search
      +
Elasticsearch
 ├─ Nori 형태소 분석
 └─ BM25
      ↓
RRF
      ↓
Rerank
```

Dense 검색은 의미적으로 유사한 표현을 찾는 역할을 유지한다.

Elasticsearch 기반 BM25는 다음 역할을 담당한다.

- 한국어 형태소 분석
- 복합명사 분리
- 조사·어미 영향 감소
- 정책명·지원유형·법령명 등 핵심 키워드 검색 강화
- 정확한 용어 중심의 검색 성능 개선

즉 Elasticsearch가 Dense 검색을 대체하는 것이 아니라, 기존 BM25 검색을 강화하는 역할을 한다.

---

## 2.2 검색 방식 A/B 테스트

기존 LangGraph는 유지하고, 검색 구조만 변경한 실험용 그래프를 별도로 구성한다.

### A안 — 기존 검색 구조

```text
Dense
+
기존 BM25
↓
RRF
↓
Rerank
```

### B안 — 개선 검색 구조

```text
Dense
+
Elasticsearch(Nori + BM25)
↓
RRF
↓
Rerank
```

두 방식에 동일한 평가 질문을 입력하여 검색 성능을 비교한다.

이 단계에서는 검색기 자체의 성능만 확인하기 위해 최종 LLM 답변 생성은 수행하지 않는다.

```text
질문
 ↓
검색
 ↓
Top-K 문서
 ↓
검색 성능 평가
```

주요 평가 지표는 다음과 같다.

- Precision@K
- Recall@K
- MRR
- MAP
- Hit@K
- 평균 검색 지연시간
- Rerank 전·후 성능 변화

특히 정책 및 법령 검색에서는 정답 문서를 놓치지 않는 것이 중요하므로 Recall@K와 MRR을 중점적으로 확인한다.

검색 성능과 지연시간을 종합하여 더 우수한 검색 구조를 최종 구조로 선택한다.

---

## 2.3 2단계 — ML 학습용 데이터 생성

검색 구조를 확정한 뒤 약 1,000건의 단일 질문을 준비한다.

질문 범위는 다음과 같다.

- 정책 검색 질문
- 세금 법령 질문

질문은 다음과 같은 다양한 검색 상황을 포함하도록 구성한다.

- 충분한 근거가 검색되는 질문
- 일부 관련 문서는 있으나 핵심 근거가 부족한 질문
- 관련성이 낮은 문서가 검색되는 질문
- 높은 검색 점수를 가지지만 실제 답변에 필요한 내용이 부족한 Hard Negative
- 유사 정책 및 유사 법령으로 혼동하기 쉬운 질문

---

## 2.4 LLM Judge를 이용한 정답 라벨 생성

1,000건의 질문을 최종 선택된 검색 구조에 입력한다.

```text
질문
 ↓
검색
 ↓
RRF
 ↓
Rerank
 ↓
Top-K 근거
 ↓
검색 Feature 저장
 ↓
기존 LLM Judge
 ↓
sufficient / insufficient
```

이 단계에서도 최종 자연어 답변은 생성하지 않는다.

LLM은 오직 검색된 근거가 충분한지 판단하는 Teacher 역할만 수행한다.

생성되는 데이터의 예시는 다음과 같다.

```text
질문
Dense Score
BM25 Score
Rerank Score
Top-K 평균 Score
Top1 - Top2 Score Gap
검색 결과 수
...
LLM Judge 결과
```

Label은 다음과 같이 구성한다.

```text
1 = sufficient
0 = insufficient
```

LLM Judge가 생성한 결과를 기본 학습 Label로 사용하되, 일부 데이터는 사람이 직접 검수한다.

특히 최종 Test Set은 가능한 한 수동 검수를 수행하여 LLM의 오판을 그대로 정답으로 사용하는 문제를 줄인다.

---

## 2.5 머신러닝 학습

검색 과정에서 생성되는 수치형 Feature를 이용해 분류 모델을 학습한다.

주요 Feature 후보:

- Dense Top-1 Score
- Dense Top-K 평균 Score
- BM25 Top-1 Score
- BM25 Top-K 평균 Score
- Rerank Top-1 Score
- Rerank Top-K 평균 Score
- Top1 - Top2 Score Gap
- Score 분산
- 일정 Threshold 이상 문서 수
- 검색 결과 수
- RRF Score

실서비스에서 정답 문서를 알 수 없으므로, 정답 문서 포함 여부와 같이 실제 서비스에서 계산할 수 없는 값은 학습 Feature로 사용하지 않는다.

모델 후보는 다음과 같다.

```text
Logistic Regression
Random Forest
XGBoost
LightGBM
```

먼저 단순 모델을 Baseline으로 사용하고, XGBoost 또는 LightGBM과 성능을 비교한다.

---

## 2.6 ML 모델 평가

데이터는 Train / Validation / Test로 분리한다.

예시:

```text
Train       70%
Validation  15%
Test        15%
```

주요 평가 지표:

- Accuracy
- Precision
- Recall
- F1 Score
- Confusion Matrix
- ROC-AUC
- 평균 추론시간

특히 다음 오류를 중요하게 확인한다.

```text
실제 insufficient
        ↓
ML이 sufficient로 판단
```

근거가 부족한 상황을 충분하다고 오판할 경우 잘못된 답변 생성으로 이어질 수 있기 때문에 False Positive를 중점적으로 관리한다.

---

## 2.7 최종 적용

ML 모델이 기존 LLM Judge의 판단을 충분히 재현할 경우 LangGraph의 근거 판단 단계를 ML Classifier로 교체한다.

### 기존 구조

```text
사용자 질문
 ↓
RAG 검색
 ↓
근거 수집
 ↓
LLM Judge
 ↓
sufficient / insufficient
 ↓
최종 답변 또는 Fallback
```

### 개선 구조

```text
사용자 질문
 ↓
Dense + Elasticsearch(Nori + BM25)
 ↓
RRF
 ↓
Rerank
 ↓
ML Classifier
 ↓
sufficient / insufficient
 ↓
최종 답변 또는 Fallback
```

기존의 `sufficient / insufficient` 출력 계약은 유지하여 이후 노드와의 연결 변경을 최소화한다.

---

# 3. 기대 효과

## 3.1 한국어 정책·법령 검색 성능 향상

Elasticsearch와 Nori 형태소 분석을 BM25 검색에 적용함으로써 다음과 같은 효과를 기대할 수 있다.

- 한국어 조사·어미 영향 감소
- 복합명사 검색 성능 향상
- 정책명 및 법령명 검색 정확도 향상
- 세금·지원사업 관련 핵심 키워드 탐색 강화
- Dense 검색과 키워드 검색의 상호 보완

Dense 검색이 의미적 유사성을 담당하고 Elasticsearch 기반 BM25가 정확한 키워드 검색을 담당함으로써 Hybrid Search의 품질 향상을 기대한다.

---

## 3.2 검색 구조를 실험적으로 검증

단순히 Elasticsearch를 도입하는 것이 아니라 동일 평가셋으로 기존 검색 방식과 개선 검색 방식을 비교한다.

이를 통해 다음을 객관적으로 확인할 수 있다.

- Elasticsearch 도입이 실제 Recall 개선으로 이어지는지
- 정답 문서 순위가 개선되는지
- 검색 지연시간 증가가 허용 가능한 수준인지
- Rerank와 결합했을 때 최종 검색 품질이 개선되는지

따라서 기술 변경의 효과를 정량적으로 설명할 수 있다.

---

## 3.3 LLM 판단 단계의 응답속도 개선

현재 근거 충분성 판단에 많은 시간이 소요되는 LLM 호출을 경량 머신러닝 모델로 대체할 경우, 판단 시간을 초 단위에서 ms 단위 수준으로 크게 줄일 수 있을 것으로 기대한다.

현재 확인된 사례:

```text
전체 응답시간 약 30초
└─ 근거 충분성 LLM 판단 약 20초
```

개선 목표:

```text
검색
 ↓
ML 근거 판단
 ↓
최종 답변 LLM
```

즉 불필요한 LLM 호출을 하나 제거하여 전체 서비스 체감 응답속도를 개선한다.

---

## 3.4 API 비용 절감

현재 구조에서는 사용자 질문마다 근거 충분성 판단을 위해 별도의 LLM 호출이 발생한다.

ML Classifier로 교체하면 해당 단계에서 발생하는 지속적인 LLM API 비용을 제거할 수 있다.

LLM은 초기 학습 데이터 생성 시 Teacher 역할로만 사용하고, 실제 서비스에서는 ML 모델이 판단을 수행한다.

---

## 3.5 프로젝트 기술적 완성도 향상

본 개선은 단순히 모델 하나를 교체하는 작업이 아니라 다음 과정을 포함한다.

```text
검색 구조 분석
        ↓
검색 알고리즘 A/B 테스트
        ↓
평가 데이터 구축
        ↓
LLM Teacher Label 생성
        ↓
ML 모델 학습
        ↓
서비스 Latency 비교
        ↓
LangGraph 적용
```

따라서 검색 품질 개선과 서비스 성능 최적화를 모두 다룰 수 있으며, 프로젝트 발표 및 포트폴리오에서도 다음과 같은 개선 과정을 명확하게 설명할 수 있다.

> 기존 RAG 구조의 검색 성능과 Latency 병목을 분석한 뒤, 한국어 형태소 분석 기반 Elasticsearch BM25를 도입하여 검색 성능을 비교하고, LLM이 담당하던 근거 충분성 판단을 학습한 경량 머신러닝 모델로 전환하여 응답속도와 운영 비용을 개선한다.

---

## 최종 목표

```text
검색 품질 개선
+
근거 판단 속도 개선
+
LLM 호출 감소
```

최종적으로는 **정책·세금 법령 검색 정확도를 유지 또는 개선하면서, 전체 챗봇 응답시간을 단축하고 서비스 구조를 경량화하는 것**을 목표로 한다.
