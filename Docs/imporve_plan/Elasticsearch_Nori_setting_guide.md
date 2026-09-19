# Elasticsearch + Nori 기본 세팅 메뉴얼

## 목적

Docker Compose 환경에서 Elasticsearch를 추가하고, 한국어 형태소 분석기 Nori를 적용한 뒤, Python에서 데이터를 적재하고 BM25 검색까지 수행하는 기본 절차를 정리한다.

최종 구조:

```text
사용자 질문
   ├─ Dense Search → Vector DB
   └─ Elasticsearch → Nori + BM25
                ↓
               RRF
                ↓
             Rerank
```

---

# 1. 서버 준비

## Step 1. Docker Compose에 Elasticsearch 추가

기존 `docker-compose.yml`에 Elasticsearch 서비스를 추가한다.

```yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:<ELASTIC_VERSION>
    environment:
      - discovery.type=single-node
    ports:
      - "9200:9200"
    volumes:
      - es-data:/usr/share/elasticsearch/data

volumes:
  es-data:
```

`<ELASTIC_VERSION>`에는 사용할 Elasticsearch 버전을 입력한다.

> Python `elasticsearch` 클라이언트와 호환되는 버전을 사용하는 것이 좋다.

---

## Step 2. Elasticsearch 실행

```bash
docker compose up -d elasticsearch
```

상태 확인:

```bash
docker compose ps
```

기본 접속 주소:

```text
http://localhost:9200
```

정상 실행되면 Elasticsearch 정보가 JSON 형태로 반환된다.

---

# 2. Nori 형태소 분석기 추가

## Step 3. Elasticsearch용 Dockerfile 생성

예시 폴더 구조:

```text
project/
├─ docker-compose.yml
└─ elasticsearch/
   └─ Dockerfile
```

`elasticsearch/Dockerfile`:

```dockerfile
FROM docker.elastic.co/elasticsearch/elasticsearch:<ELASTIC_VERSION>

RUN bin/elasticsearch-plugin install --batch analysis-nori
```

---

## Step 4. Compose에서 커스텀 이미지 사용

기존:

```yaml
elasticsearch:
  image: docker.elastic.co/elasticsearch/elasticsearch:<ELASTIC_VERSION>
```

변경:

```yaml
elasticsearch:
  build: ./elasticsearch
  environment:
    - discovery.type=single-node
  ports:
    - "9200:9200"
  volumes:
    - es-data:/usr/share/elasticsearch/data
```

---

## Step 5. 다시 빌드하고 실행

```bash
docker compose build elasticsearch
docker compose up -d elasticsearch
```

이제 Elasticsearch 안에 Nori가 설치된 상태가 된다.

---

# 3. Python 클라이언트 준비

## Step 6. Elasticsearch Python 클라이언트 설치

uv:

```bash
uv add elasticsearch
```

pip:

```bash
pip install elasticsearch
```

이 패키지는 Elasticsearch 서버 자체가 아니라 Python에서 Elasticsearch 서버에 요청을 보내기 위한 SDK다.

---

## Step 7. Python에서 연결 확인

로컬 Python에서 접속:

```python
from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")

print(es.info())
```

Python 서비스도 같은 Docker Compose 내부에 있다면:

```python
from elasticsearch import Elasticsearch

es = Elasticsearch("http://elasticsearch:9200")
```

Compose 내부에서는 `localhost` 대신 서비스 이름 `elasticsearch`를 사용한다.

---

# 4. 검색용 Index 생성

## Step 8. Nori Analyzer가 적용된 Index 생성

```python
from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")

index_name = "policies"

index_settings = {
    "settings": {
        "analysis": {
            "tokenizer": {
                "nori_tokenizer_custom": {
                    "type": "nori_tokenizer",
                    "decompound_mode": "mixed"
                }
            },
            "analyzer": {
                "korean_analyzer": {
                    "type": "custom",
                    "tokenizer": "nori_tokenizer_custom"
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "document_id": {
                "type": "keyword"
            },
            "title": {
                "type": "text",
                "analyzer": "korean_analyzer"
            },
            "content": {
                "type": "text",
                "analyzer": "korean_analyzer"
            },
            "category": {
                "type": "keyword"
            }
        }
    }
}

if not es.indices.exists(index=index_name):
    es.indices.create(
        index=index_name,
        body=index_settings
    )
```

---

# 5. Nori 분석 결과 확인

## Step 9. 형태소 분석 테스트

```python
result = es.indices.analyze(
    index="policies",
    analyzer="korean_analyzer",
    text="청년창업지원사업을 신청하고 싶습니다"
)

for token in result["tokens"]:
    print(token["token"])
```

예상 개념:

```text
청년
창업
지원
사업
신청
```

정책명, 법령명, 복합명사가 원하는 형태로 분리되는지 확인한다.

---

# 6. 원본 DB 데이터를 Elasticsearch에 적재

## Step 10. 단일 문서 적재 테스트

```python
doc = {
    "document_id": "policy_001",
    "title": "청년 창업 사업화 지원사업",
    "content": "청년 창업자를 대상으로 사업화 자금을 지원합니다.",
    "category": "policy"
}

es.index(
    index="policies",
    id="policy_001",
    document=doc
)
```

---

## Step 11. 여러 문서 Bulk 적재

```python
from elasticsearch import helpers

documents = [
    {
        "_index": "policies",
        "_id": "policy_001",
        "_source": {
            "document_id": "policy_001",
            "title": "청년 창업 사업화 지원사업",
            "content": "청년 창업자에게 사업화 자금을 지원합니다.",
            "category": "policy"
        }
    },
    {
        "_index": "policies",
        "_id": "policy_002",
        "_source": {
            "document_id": "policy_002",
            "title": "청년 사업장 임차료 지원",
            "content": "청년 사업자의 사업장 임차료 일부를 지원합니다.",
            "category": "policy"
        }
    }
]

helpers.bulk(es, documents)
```

---

# 7. 원본 DB → Elasticsearch 동기화

## Step 12. 동기화 Python 파일 작성

예시:

```text
sync_to_elasticsearch.py
```

역할:

```text
1. 원본 DB 조회
2. 검색에 필요한 컬럼 추출
3. Elasticsearch 문서 형태로 변환
4. 신규 데이터 Index
5. 수정 데이터 Update
6. 삭제 또는 만료 데이터 Delete / 비활성화
```

구조:

```text
PostgreSQL
    ↓
sync_to_elasticsearch.py
    ↓
Elasticsearch
```

### 초기 구현

MVP 단계에서는 전체 재색인 방식으로 시작할 수 있다.

```text
원본 DB 전체 조회
        ↓
Elasticsearch Index 초기화
        ↓
전체 문서 다시 적재
```

### 이후 개선

`updated_at` 등을 이용해 변경된 데이터만 반영하는 증분 동기화로 발전시킬 수 있다.

```text
마지막 동기화 이후 변경 데이터 조회
        ↓
신규 / 수정 데이터만 Elasticsearch 반영
```

---

# 8. Elasticsearch BM25 검색

## Step 13. 기본 검색 함수 작성

```python
def elastic_bm25_search(
    es,
    query: str,
    index_name: str = "policies",
    top_k: int = 10
):
    response = es.search(
        index=index_name,
        size=top_k,
        query={
            "multi_match": {
                "query": query,
                "fields": [
                    "title^2",
                    "content"
                ]
            }
        }
    )

    results = []

    for hit in response["hits"]["hits"]:
        results.append({
            "document_id": hit["_source"]["document_id"],
            "score": hit["_score"],
            "title": hit["_source"]["title"],
            "content": hit["_source"]["content"],
        })

    return results
```

사용 예시:

```python
results = elastic_bm25_search(
    es,
    "청년 창업 지원금"
)

for result in results:
    print(result["score"], result["title"])
```

Elasticsearch의 일반적인 text 검색은 BM25 기반 관련도 점수를 사용한다.

---

# 9. 기존 Dense 검색과 결합

## Step 14. 기존 BM25 Retriever 교체

기존:

```text
사용자 질문
   ├─ Dense Search
   └─ 기존 BM25 Search
```

변경:

```text
사용자 질문
   ├─ Dense Search
   │    └─ Vector DB
   │
   └─ Elasticsearch BM25
        └─ Nori Analyzer
```

코드 흐름:

```python
dense_results = dense_search(query)

bm25_results = elastic_bm25_search(
    es,
    query,
    top_k=20
)

merged_results = rrf(
    dense_results,
    bm25_results
)

final_results = rerank(
    query,
    merged_results
)
```

---

# 10. 최종 검색 구조

```text
                        사용자 질문
                             │
               ┌─────────────┴─────────────┐
               │                           │
               ↓                           ↓
          Dense Search              Elasticsearch
               │                     Nori + BM25
               ↓                           ↓
          Vector DB                 Search Index
               │                           │
               └─────────────┬─────────────┘
                             ↓
                            RRF
                             ↓
                          Rerank
                             ↓
                       최종 검색 결과
```

---

# 11. 작업 순서 요약

## A. 서버 준비

```text
1. Docker Compose에 Elasticsearch 추가
2. Elasticsearch 실행
3. Nori 플러그인 추가
4. Elasticsearch 이미지 재빌드
```

## B. 검색 준비

```text
5. Python elasticsearch client 설치
6. 서버 연결 테스트
7. Nori Analyzer Index 생성
8. 형태소 분석 테스트
9. 원본 DB 데이터 Elasticsearch 적재
10. 동기화 로직 작성
11. BM25 검색 테스트
```

## C. RAG 연결

```text
12. 기존 BM25 Retriever를 Elasticsearch Retriever로 교체
13. Dense 검색과 병렬 실행
14. RRF 결합
15. Rerank
16. 검색 성능 평가
```

---

# 12. 체크리스트

- [ ] Elasticsearch 컨테이너 정상 실행
- [ ] `localhost:9200` 응답 확인
- [ ] Nori 플러그인 설치 확인
- [ ] Python Client 연결 확인
- [ ] 검색용 Index 생성
- [ ] Nori 형태소 분석 결과 확인
- [ ] 원본 DB 데이터 적재
- [ ] Elasticsearch BM25 검색 성공
- [ ] DB → Elasticsearch 동기화 로직 구현
- [ ] Dense + Elasticsearch 검색 결합
- [ ] RRF 정상 작동
- [ ] Rerank 정상 작동
- [ ] 기존 BM25 방식과 검색 성능 비교

---

## 핵심 정리

```text
Docker로 Elasticsearch 실행
        ↓
Nori 설치
        ↓
Python Client 연결
        ↓
Index 생성
        ↓
원본 DB 데이터 적재
        ↓
Nori + BM25 검색
        ↓
Dense 결과와 결합
        ↓
RRF
        ↓
Rerank
```

Elasticsearch는 Dense 검색을 대체하는 것이 아니라, 현재 구조에서는 **기존 BM25 Retriever를 한국어 형태소 분석이 가능한 검색엔진 기반 BM25로 강화하는 역할**을 한다.
