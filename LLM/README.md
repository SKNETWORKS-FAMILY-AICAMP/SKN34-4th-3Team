# LLM/RAG Service

사용자 프로필과 질문을 바탕으로 전체 정책 문서에서 관련 정책을 탐색·요약하는
내부 LLM 서비스다. 실제 자격 판정이 필요한 경우에는 Backend의 Rule 기반 결과를
Source of Truth로 사용하며, 이 서비스는 판정값을 변경하지 않는다.

Backend(`Backend/core/llm_client.py`)가 Docker 내부 네트워크에서 호출하며 다음을 제공한다.

- Backend 어댑터: `GET /rag/ready`, `POST /rag/reindex`, `POST /rag/chat`(LangGraph),
  `POST /rag/legal-basis`, `POST /rag/deductibility`, `POST /rag/summarize-announcement`,
  `POST /ocr/receipt`
- 내부 호환 API: `GET /internal/rag/ready`, `POST /internal/rag/index`,
  `POST /internal/rag/answer`(LangGraph), `POST /internal/rag/recommendations`
- `GET /health`, 환경변수 기반 LLM·Embedding 모델 팩터리(실제 자격증명 없이도 기동)
- PostgreSQL 사용자·정책·공고문·세법 조회와 테스트용 Mock 데이터 계층
- DB 원천 문서 Chunking·pgvector 저장, BM25+RRF Hybrid 검색, Cohere Rerank
- 세금 질문 Semantic Cache(`tax_rag_cache`)와 LangSmith tracing

원본 PDF와 DB 원천 테이블은 읽기 전용으로 취급하고 가공 결과를 원본에 덮어쓰지 않는다.
LLM 프로세스는 기동 시 검색기를 스스로 준비하지 않는다. Compose 기동에서는 Backend의
워밍업 스레드가 `/rag/ready`를 확인하고 준비되지 않았으면 `/rag/reindex`를 한 번
호출한다. 변경된 Chunk가 있으면 이때 Embedding 비용이 발생할 수 있다.
그래프 구조와 인수인계는 `LANGGRAPH_ARCHITECTURE.md`, 실행 절차는 `RUN_GUIDE.md`를 참고한다.

## 구조

```text
LLM/
├── data/                  # 원본과 분리한 중간·가공·캐시 데이터
├── evaluation/            # 평가 케이스·실행 스크립트·결과(results/는 Git 제외)
├── models/                # 로컬 모델 자산을 위한 예약 영역
├── main.py
├── src/
│   ├── core/
│   │   ├── config.py       # 환경변수 설정
│   │   ├── database.py     # PostgreSQL 커넥션 풀(psycopg_pool, 1~16)
│   │   └── langsmith.py    # LangSmith tracing 설정
│   ├── data/
│   │   ├── contracts.py       # Backend/DB 및 RAG 데이터 타입 계약
│   │   ├── document_catalog.py # 임시 PDF-policy_id mapping
│   │   ├── mock_repository.py  # 자동 테스트용 Mock 접근 함수
│   │   ├── postgres_repository.py # 실제 사용자·정책·공고문·세법 조회
│   │   └── tax_normalization.py   # `N분의 M` 세법 비율 정규화·추출
│   ├── evaluation/
│   │   ├── evaluator.py       # 평가 schema와 전체 실행 흐름
│   │   ├── graph_evaluator.py # LangGraph 답변·대화 채점
│   │   ├── metrics.py         # 검색·Guardrail 지표 계산
│   │   └── run_evaluation.py  # HTTP adapter와 평가 CLI
│   ├── features/
│   │   ├── document_processing.py # PDF 로드와 Chunking
│   │   ├── index_database.py  # DB 원천 문서를 pgvector에 적재하는 CLI
│   │   ├── indexing.py        # Embedding·인덱스·로컬 캐시
│   │   └── index_documents.py # 명시적으로 실행하는 임시 색인 CLI
│   ├── models/
│   │   └── factory.py      # 교체 가능한 모델 생성 진입점
│   ├── rag/
│   │   ├── graph.py        # LangGraph GraphState·node·edge
│   │   ├── tax.py          # Tax Intent·Evidence·Next Query·계산 계획 schema
│   │   ├── tax_cache.py    # 세금 Semantic Cache
│   │   ├── answer.py       # 공통 Structured Answer와 fallback
│   │   ├── roadmap.py      # 로드맵 코치 단일 호출
│   │   ├── reranker.py     # Cohere Rerank
│   │   ├── history.py      # 대화 이력 정규화·절삭
│   │   ├── backend_tasks.py # legal-basis·deductibility·공고 요약·영수증 추출
│   │   ├── retriever.py    # 검색 및 관련성 필터
│   │   ├── prompts.py      # 근거·판정 보존 PromptTemplate
│   │   ├── chain.py        # 구조화 생성·출력 분량·문자열 변환
│   │   ├── context_builder.py # Prompt 길이·정책별 Chunk 제한
│   │   ├── discovery.py    # 정책 탐색·검색어 패싯·그룹화
│   │   ├── guardrails.py   # 입력·근거 Guardrail
│   │   ├── service.py      # 정책 추천 RAG 사용 사례 조합
│   │   └── contracts.py    # RAG 도메인·구조화 출력 schema
│   ├── vectorstores/
│   │   ├── base.py         # In-memory/pgvector 공통 검색 계약
│   │   ├── hybrid.py       # BM25와 RRF Hybrid Search
│   │   ├── in_memory.py    # 프로세스 내부 테스트 Vector Store
│   │   └── postgres.py     # 실제 PostgreSQL pgvector Search
│   └── serving/
│       ├── app.py          # FastAPI 애플리케이션
│       ├── rag_routes.py   # API endpoint와 프로세스 runtime(그래프·클라이언트 캐시)
│       ├── schemas.py      # API 요청·응답 schema
│       ├── errors.py       # HTTP 오류 코드·응답 형식
│       └── tax_calculators_docstring.py # 세금 계산기 5종
└── tests/
```

## 환경 설정

`.env.example`을 `.env`로 복사한 뒤 필요한 값을 입력한다. `.env`는 Git과
Docker build context에서 제외된다.

```dotenv
LLM_MODEL=YOUR_LLM_MODEL
EMBEDDING_MODEL=YOUR_EMBEDDING_MODEL
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
DATABASE_URL=postgresql://YOUR_USER:YOUR_PASSWORD@localhost:5432/YOUR_DATABASE
DATABASE_CONNECT_TIMEOUT=5
VECTOR_STORE_BACKEND=postgres
CORS_ORIGINS=http://localhost:5173
CHUNK_SIZE=1000
CHUNK_OVERLAP=150
DEFAULT_TOP_K=5
MIN_RELEVANCE_SCORE=0.2
RETRIEVAL_MODE=hybrid
HYBRID_DENSE_CANDIDATE_K=20
HYBRID_BM25_CANDIDATE_K=20
HYBRID_RRF_K=60
MAX_QUESTION_LENGTH=1000
MAX_CONTEXT_CHARACTERS=12000
MAX_CHUNKS_PER_POLICY=2
RAG_ALLOWED_KEYWORDS=정책,지원,지원금,보조금,장려금,창업,청년,사업,공고,신청,자격,대상,혜택,세금,세무,세법,세액,감면,절세,경비,사업자,업종,지역,주거,취업,근속,직무,문화,이전비,받을,신고,납부,기간,마감,방법,서류,금액,얼마,언제,조건
RAG_BLOCKED_KEYWORDS=파이썬,python,append,자바,javascript,코딩,프로그래밍,날씨,주식,비트코인,요리,레시피,게임
OUT_OF_SCOPE_ANSWER=그 질문에는 답변할 수 없습니다
INVALID_GENERATION_ANSWER=답변 근거를 정확히 확인하지 못했습니다. 다시 시도해 주세요.
VECTOR_INDEX_CACHE_PATH=data/processed/rag_vector_index.json

LANGSMITH_TRACING=false
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=skn34-3rd-project
LANGSMITH_API_KEY=YOUR_LANGSMITH_API_KEY
LANGSMITH_HIDE_INPUTS=false
LANGSMITH_HIDE_OUTPUTS=false
```

`COHERE_*`, `TAX_MAX_HOPS`, `TAX_CACHE_*`는 아래 "LangGraph와 Tax Multi-hop" 절을 참고한다.
`LLM/.env.example`에는 위 블록의 일부 키(`DATABASE_URL`, `VECTOR_STORE_BACKEND`, `TAX_CACHE_*` 등)가
빠져 있으므로 저장소 루트 `.env.example`과 `src/core/config.py`를 함께 확인한다.

현재 모델 adapter는 OpenAI를 기본으로 사용한다. 모델 값이 비어 있거나 `YOUR_`
placeholder이면 미설정 상태로 처리하므로 Health API는 자격증명 없이도
정상 실행된다.

## 실제 DB와 테스트용 Mock 데이터

기본 실행은 PostgreSQL의 `users`, `business_profiles`, `policies`,
`announcements`를 사용한다. `LLM/.env`의 `DATABASE_URL`이 실제 값이면 이를
사용하고, placeholder이면 저장소 루트 `.env`의 PostgreSQL 항목을 사용한다.

```env
VECTOR_STORE_BACKEND=postgres
```

Mock repository와 PDF In-memory 인덱스는 외부 DB·모델 호출이 없어야 하는 자동
테스트와 독립 개발에만 사용한다.

```env
VECTOR_STORE_BACKEND=in_memory
```

## PostgreSQL + pgvector Search

운영 경로는 DB의 정책·공고문을 읽고 Chunking한 뒤 `rag_documents`의 pgvector
컬럼에 파생 데이터를 저장한다. 원본 `policies`와 `announcements`는 수정하지
않는다. `rag_documents`에 `chunk_id`, `policy_id`, `content` 컬럼이 없으면 스키마를
변경하지 않고 오류를 반환한다.

서버에서 인덱스를 준비한다.

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8001/internal/rag/index
```

최초 실행에는 실제 DB 원천 문서 전체의 Embedding 비용이 발생한다. 이후에는 기존 행의
`content` SHA-256이 같은 Chunk를 재사용하고 신규·변경 Chunk만 다시 임베딩한다.
Embedding 모델명은 비교하지 않으므로 모델을 바꾸면 `{"force": true}`로 다시 임베딩한다.

테스트용 In-memory 구현도 동일한 `VectorSearch` 계약을 유지한다.

```python
from langchain_core.embeddings import DeterministicFakeEmbedding

from src.features import build_document_vector_index

vector_search = build_document_vector_index(
    embedding=DeterministicFakeEmbedding(size=32),
)
results = vector_search.search("지원 대상", policy_id=101, top_k=2)
```

프로세스 안의 In-memory 인덱스는 종료 시 사라지지만 직렬화된 로컬 캐시는
`data/processed/rag_vector_index.json`과 `rag_vector_index.manifest.json`에 남는다.
다음 서버 실행에서는 PDF, Embedding 모델, Chunk 설정과 catalog가 동일하면 이
캐시를 읽어 문서 재임베딩을 생략한다.

다음 조건 중 하나가 변경되면 인덱스를 다시 생성한다.

- 원본 PDF SHA-256
- Embedding 모델명
- `CHUNK_SIZE` 또는 `CHUNK_OVERLAP`
- PDF-policy_id catalog
- 캐시 schema version

강제로 다시 임베딩하려면 CLI에서는 `--force`, API에서는
`{"force": true}`를 사용한다. 생성된 캐시에는 Chunk 본문과 vector가 포함되므로
Git에 올리지 않으며 `LLM/.gitignore`에서 제외한다.

PostgreSQL과 In-memory 구현은 모두 `src/vectorstores/base.py`의
`add_chunks()`, `search()`, `get_chunks()` 계약을 유지한다.

### Hybrid Retrieval

기본 검색은 동일한 Chunk 집합의 Dense와 BM25 순위를 RRF로 결합한다.
`HYBRID_DENSE_CANDIDATE_K`와 `HYBRID_BM25_CANDIDATE_K`는 각 검색기가 RRF에
제공할 후보 수이고, `HYBRID_RRF_K`는 순위 점수 격차를 조절한다.
최종 후보 수는 API의 `top_k` 또는 `DEFAULT_TOP_K`를 사용한다.

`RETRIEVAL_MODE=dense`로 바꾸면 정책 추천(`/internal/rag/recommendations`)만 Dense
단독으로 동작한다. LangGraph 경로(`/rag/chat`, `/internal/rag/answer`)와 legal-basis·
deductibility는 설정과 무관하게 항상 Hybrid로 감싸 검색한다.

```dotenv
RETRIEVAL_MODE=dense
```

### LangGraph와 Tax Multi-hop

일반 질문 Router는 실제 요청 의도를 `policy`, `notice`, `tax`, `out_of_scope`로
Structured Output 분류한다. Backend category는 허용 route 제약으로 적용된다
(`tax`·`expense`→tax, `saving`→tax·policy, `policy`→policy·notice). 범위 밖 요청은
허용하지 않는다. Policy는 Dense + BM25 + RRF 결과에 Cohere Rerank를 적용하고,
Notice는 Vector 검색 없이 Backend가 요청에 담아 보낸 `noticeResults`(현재
`category=policy`에서 전달)만 사용한다.

Tax는 각 Hop에서 동일한 Hybrid Retrieval과 Cohere Rerank를 실행한 뒤 검색 문서의
`N분의 M` 비율을 별도 `tax_ratio_normalization` node에서 구조화하고, 법령 근거와
사용자 정보의 부족 여부를 분리해 평가한다. 명시적 법령 참조를 다음 Query보다 먼저
사용하며, `TAX_MAX_HOPS` 도달·반복 Query·새 근거 없음이면 근거 부족 상태로 종료한다.
세금 계산은 Tax Intent가 계산 종류를 정하고 Planner가 질문·사용자 프로필에서 입력값만
추출한 뒤, `src/serving/tax_calculators_docstring.py`의 계산기 5종(종합소득세, 근로소득
원천징수, 일반과세 VAT, 간이과세 매출세액, 창업 세액감면)이 Python `Decimal`로 계산한다.
LLM은 산술 결과를 만들지 않는다. 법적 자격이 필요 없는 계산은 입력이 충분하면 RAG를
생략하고, 창업 세액감면은 법령 근거 확인 뒤 계산한다. 기존 비율 계산(기준금액×법령 비율)은
호환 경로로 남아 있으며, 비율이 인용 근거에 없으면 계산하지 않는다. 세액감면 자격 판정
Rule Engine은 계속 Backend 책임이다.

Tax 검색 앞에는 Semantic Cache(`src/rag/tax_cache.py`)가 있다. 질문·사용자 조건이 같거나
질문 Embedding이 충분히 유사하면 `tax_rag_cache`에 저장된 근거(`rag_documents.id`)와 근거
판정을 복원해 검색·판정 LLM 호출을 건너뛴다. 설정은 다음과 같다.

```dotenv
TAX_CACHE_ENABLED=true
TAX_CACHE_SIMILARITY_THRESHOLD=0.95
TAX_CACHE_DECISION_SIMILARITY_THRESHOLD=0.98
```

판정 임계값은 유사도 임계값 이상이어야 한다. `tax_rag_cache` 테이블은
`DB/app_extras.sql`이 만들며 PostgreSQL 백엔드에서만 동작한다. 조회·저장이 실패하면
경고 로그만 남기고 일반 Multi-hop으로 진행한다.

`category=roadmap`은 토큰 절약을 위해 위 흐름을 우회한다. 초기화 직후 전용
`roadmap_coach` node가 범위 판정과 답변을 하나의 Structured Output 호출로 처리하며,
질문 재작성·Router·Embedding·Rerank·공통 Answer를 호출하지 않는다. 7단계와 28개
작업에 직접 관련된 질문만 답하고 세무·공고 질문은 각 전용 화면으로 안내한다.

검색된 세법 문서를 LLM Prompt에 넣을 때만 `분모분의 분자` 원문 옆에 계산한
백분율을 함께 둔다. 예를 들어 `10분의 1(10%)`, `100분의 15(15%)`,
`1000분의 5(0.5%)`로 전달한다. DB 원문과 Embedding용 content는 변경하지 않으므로
이 해석 보조 규칙 때문에 재색인할 필요가 없다.

Evidence 이후 edge는 네 갈래다. 근거가 부족하고 추가 검색 가능하면
`tax_next_query`(재검색은 다시 `tax_cache`부터), 근거가 충분하고 계산이 필요하면
`tax_calculator`, 캐시로 복원한 근거가 부족하다고 판정되면 `tax_cache_fallback`을 거쳐
새 검색, 그 밖의 종료 상태와 계산 불필요 질문은 `answer`로 바로 이동한다. Next Query
생성 실패·중복도 계산으로 보내지 않고 Answer에서 종료한다.

세 branch는 모두 `answer` node에서 합류한다. 성공한 요청은 route에 필요한 실제
검색/조회 결과만 Structured Output 모델에 전달하며, 최종 출처는 모델이 생성하지
않고 실제 결과의 번호를 검증해 선택한다. 무결과, 사용자 정보 부족, 근거 부족,
Backend 미연결과 내부 오류는 서로 다른 `status`로 반환한다.

```text
success | need_more_info | insufficient_evidence | no_result |
integration_unavailable | error
```

`POST /internal/rag/answer`가 실제 LangGraph 실행 진입점이다. 기존 요청 필드
`question`, `policy_id`, `top_k`, `decision`을 유지하고 개인화 Context 조회를 위한
선택적 `user_id`를 받는다. 응답에는 기존 `answer`, `grounded`, `sources`, `decision`,
`guardrail_reason`과 함께 `route`, `status`가 포함된다. 정책 추천과 retrieval 평가
entry point는 기존 흐름을 유지한다.

```dotenv
COHERE_API_KEY=YOUR_COHERE_API_KEY
COHERE_RERANK_MODEL=rerank-v4.0-fast
COHERE_RERANK_CANDIDATE_K=20
TAX_MAX_HOPS=3
```

## RAG API

### Backend 어댑터

Backend의 `core/llm_client.py`가 우선 호출하는 명세 경로를 제공한다.

- `GET /rag/ready`
- `POST /rag/reindex`
- `POST /rag/chat`

`/rag/chat`은 기존 `{ category, question }` 요청을 그대로 허용한다. 개인화, 실제 공고
조회와 사용자별 후속 질문 연결을 위해 Backend가 다음 선택 필드를 전달할 수도 있다.

```json
{
  "category": "policy",
  "question": "서울에서 현재 신청 가능한 사업 있어?",
  "userContext": {
    "userId": 1,
    "age": 29,
    "region": "서울",
    "businessType": "간이과세자",
    "industry": "소프트웨어",
    "businessRegisteredAt": "2024-03-01",
    "foundedAt": "2024-03-01"
  },
  "noticeResults": [],
  "conversationHistory": [
    {"role": "user", "content": "서울에서 창업을 준비 중이야"},
    {"role": "assistant", "content": "업종과 창업 시기를 알려주세요."}
  ]
}
```

`noticeResults`가 없으면 Notice branch는 `integration_unavailable`, Backend가 실제
조회 후 빈 배열을 전달하면 `no_result`로 구분한다. LLM은 공고 조회 SQL, 자격 판정,
과세표준 산출 같은 Backend 비즈니스 로직을 대신 구현하지 않는다. 응답 source는 명세의 `url`과 현재 Backend
호환용 `source`에 같은 URL을 제공한다.

`conversationHistory`는 선택값이며 완료된 user/assistant 대화 최대 10쌍을 받는다. 이력이
있으면 현재 질문의 생략 표현을 독립 질문으로 복원한 뒤 기존 LangGraph를 실행한다. 과거
assistant 답변은 대화 문맥일 뿐 정책·세법 근거나 인용 source로 사용하지 않는다.
API 검증 후 실제 모델 Prompt에는 모든 route에서 최근 5쌍·4,000자만 전달한다.

로드맵 요청은 `category="roadmap"`과 선택적 `roadmapStep`(`A|B|C|D|E|F|Z`)을
사용한다. 모델 Prompt에는 최근 5쌍·4,000자까지만 전달하며 결과는
`route="roadmap"`, `sources=[]`, `grounded=false`다.

검색 인덱스가 준비돼 있어야 실제 답변이 나온다. Compose 기동에서는 Backend 워밍업이
준비하고, LLM만 따로 띄웠거나 재시작했으면 아래처럼 직접 준비한다. 준비 전
`/rag/chat`은 200 + `status=integration_unavailable`로 응답한다.

PostgreSQL 모드에서는 실제 정책·공고문을 조회해 신규·변경 Chunk만 임베딩한다.
In-memory 테스트 모드에서는 유효한 로컬 캐시가 있으면 PDF 재임베딩을 생략한다.

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8001/internal/rag/index
```

응답의 `source`가 `cache`이면 문서 임베딩을 재사용했고, `embedding`이면 새로
임베딩했다는 의미다.

준비 상태를 확인한다.

```powershell
Invoke-RestMethod -Uri http://localhost:8001/internal/rag/ready
```

### 사용자 기반 정책 탐색

기본 서비스 흐름은 사용자가 정책 번호를 고르는 방식이 아니다. `user_id`로 실제
PostgreSQL 사용자·사업자 정보를 가져온 뒤 질문과 프로필을 결합해 전체 정책
문서를 검색한다. 실제 사용자와 사업자 프로필이 없으면 404를 반환한다.

```powershell
$body = @{
    user_id = 1
    question = "내 조건과 관련된 지원정책을 알려줘"
    top_k = 5
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://localhost:8001/internal/rag/recommendations `
    -ContentType "application/json" `
    -Body $body
```

이 흐름에서 `policy_id`는 사용자 입력이 아니라 검색된 정책을 구분하는 결과값이다.
프로필은 관련성 검색에만 사용하며 지원 자격을 확정하지 않는다.

### 관련 없는 질문 Guardrail

원문 질문에 `RAG_BLOCKED_KEYWORDS`가 포함되면 모델 호출 전에 차단한다. 그 밖의
범위 판정은 대화 이력을 복원한 뒤 Router가 실제 요청 의도를 기준으로 수행한다.
도메인 단어가 배경에만 등장하는 외부 요청과 시스템 지침 공개 요청은
`out_of_scope`로 종료한다. 로드맵 경로는 전용 Guardrail을 유지한다.

```json
{
  "user_id": 1,
  "answer": "그 질문에는 답변할 수 없습니다",
  "grounded": false,
  "policies": []
}
```

차단 키워드는 명백한 금지 요청의 조기 차단용이므로 목록을 넓힐 때 정상 정책 질문의
표현과 충돌하지 않는지 평가셋으로 확인해야 한다. 응답 문구는 `.env`의
`OUT_OF_SCOPE_ANSWER`만 변경하면 코드 수정 없이 바꿀 수 있다.

### 구조화 출력과 생성 결과 검증

LLM은 자유 문자열 대신 Pydantic schema로 답변·정책 요약·출처 번호를 반환한다.
실제 policy_id, 문서 제목, 페이지와 score는 LLM 출력을 신뢰하지 않고 Retriever
결과에서만 가져온다.

Prompt에 전달하기 전 다음 Context 제한을 적용한다.

- 중복 chunk_id 제거
- 정책별 최대 `MAX_CHUNKS_PER_POLICY`개 유지
- 전체 `MAX_CONTEXT_CHARACTERS` 제한
- Chunk를 중간에서 자르지 않음
- Prompt에 포함된 Chunk만 API sources로 반환

Prompt는 `<user_profile>`, `<backend_decision>`, `<retrieved_documents>`,
`<user_question>` 경계를 사용한다. LLM이 존재하지 않는 출처 번호나 검색되지 않은
policy_id를 생성하거나 빈 답변을 반환하면 `grounded=false`,
`guardrail_reason=generation_validation_failed`와 `INVALID_GENERATION_ANSWER` 문구를
반환한다.

Prompt 버전은 `prompts.py`의 `POLICY_DISCOVERY_PROMPT_VERSION`과
`DECISION_EXPLANATION_PROMPT_VERSION`에서 관리하며 LangSmith metadata에 기록한다.

현재 간결성 규칙을 반영한 Prompt 버전은 `policy-discovery-v3`와
`decision-explanation-v2`다. 특정 정책 답변은 결론부터 3~5문장으로 작성하고,
정책 탐색 답변은 관련성 높은 정책 최대 3개만 보여준다. 정책별 관련 이유와 추가
확인사항은 각각 최대 2개, 전체 제한사항은 1개로 제한한다. LLM이 이 개수를
초과해도 `chain.py`가 최종 응답에서 다시 제한한다.

정책 추천의 사용자 출력은 `chain.py` formatter가 `정책명 → 자격 → 지원 내용 →
신청기간 → 출처` 순서로 조합한다. 제한 조건, 관련 이유, 확인사항과 전체 안내는
Structured Output 내부에는 유지하지만 기본 `answer` 문자열에서는 중복과 길이를
줄이기 위해 표시하지 않는다. 기존 `summary`도 내부 호환성을 위해 유지하되 최종
문자열 형식에는 사용하지 않는다. `overview`는 LLM 문장 대신 compact된 실제 정책
수를 기준으로 `회원님과 관련이 높은 정책 N개를 찾았습니다.`로 만든다. 문서에서
찾지 못한 항목은 임의 생성하지 않고 `확인 필요`로 표시한다.

### 특정 정책 상세 질의와 Backend 판정 설명

검색 결과에서 정책 하나를 선택한 뒤 상세 질문하거나 Backend 판정 결과를 설명할
때에는 `/internal/rag/answer`를 사용한다. 이 요청에서는 질문 Embedding과 검색
근거 기반 LLM 호출이 발생한다.

```powershell
$body = @{
    question = "청년창업 지원사업의 지원 대상은 누구야?"
    policy_id = 101
    top_k = 3
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://localhost:8001/internal/rag/answer `
    -ContentType "application/json" `
    -Body $body
```

Backend가 확정한 판정 결과를 선택적으로 함께 보낼 수도 있다. `eligible`과
`reasons`는 LLM이 재계산하지 않고 응답에도 동일하게 반환한다.

```json
{
  "question": "나는 이 정책 대상이야?",
  "policy_id": 101,
  "top_k": 3,
  "decision": {
    "eligible": true,
    "reasons": ["연령 조건 충족", "지역 조건 충족"]
  }
}
```

## LangSmith

`.env`에서 `LANGSMITH_TRACING=true`와 실제 `LANGSMITH_API_KEY`를 설정하면
`skn34-3rd-project` 프로젝트에 `policy_discovery`, `build_personalized_query`,
`retrieve_documents`, `build_prompt_context`, `generate_policy_summary` trace가
기록된다(정책 추천). 채팅·상세 답변은 LangGraph 실행으로 `langgraph_contextualize_question`,
`langgraph_question_router`, `langgraph_unified_answer`, `langgraph_roadmap_coach`,
`tax_intent_classifier`, `tax_calculation_input_planner`, `tax_evidence_evaluator`,
`tax_next_query_generator` 등이, 단일 작업은 `backend_legal_basis`·`backend_deductibility`·
`backend_announcement_summary`·`backend_receipt_ocr`가 기록된다.

개발 중 trace 확인을 위해 `LANGSMITH_HIDE_INPUTS=false`,
`LANGSMITH_HIDE_OUTPUTS=false`를 사용한다. 이 설정에서는 사용자 질문, 프로필,
검색 문서와 모델 답변이 LangSmith에 기록될 수 있으므로 실제 개인정보나 비공개
문서를 사용하기 전에는 두 값을 `true`로 변경한다.

LangSmith가 비활성화돼 있으면 tracing Client를 생성하거나 네트워크 요청을 보내지
않는다. API Key는 코드 또는 로그에 출력하지 않는다.

## 검색·Guardrail 평가

`src/evaluation/`은 정책 검색 순위를 P@k, R@k, MRR, AP@k로 평가하고 Guardrail을
이진 분류 지표로 평가한다. 검색 지표의 평가 단위는 Chunk가 아니라 사용자에게
반환된 `policy_id` 순위다.

- P@k: 상위 k개 중 관련 정책 비율
- R@k: 전체 관련 정책 중 상위 k개에서 찾은 비율
- MRR: 첫 관련 정책 순위의 역수 평균
- AP@k: 관련 정책을 만날 때의 Precision 합을 `min(관련 정책 수, k)`로 나눈 값
- Guardrail: Accuracy, Precision, Recall, F1, TP, FP, TN, FN

AP@k는 검색된 정답만 평균내지 않고 놓친 관련 정책도 감점하는 표준 분모를 사용한다.
Guardrail에서는 `out_of_scope`만 입력 차단으로 계산한다. `insufficient_evidence`와
`generation_validation_failed`는 검색·생성 실패 사유로 별도 집계한다. 정책 검색은
전체 정상 문항을 분모로 삼은 종단 간 P@k·R@k·MRR·MAP과 Guardrail을 통과해 검색을
시도한 문항의 조건부 지표를 함께 출력한다.

기본 `legacy80` 평가셋은 [evaluation_cases.py](evaluation/evaluation_cases.py)다. 정책 20건,
가드레일 20건과 세금·로드맵 각각 10개의 2턴 시나리오를 담고 있다. 평가 전에는
기본 실행은 Mock 사용자 프로필을 사용하며 평가셋의 ID 1·2·4가 준비되어 있다.
정답 정책 ID와 질문 조건이 대상 DB의 실제 정책과 일치하는지는 별도로 확인해야 한다.
실제 DB 사용자로 전환할 때는 `--user-source db`를 지정한다.
기존 `sample_cases.json`은 기본 입력에서 제외했으며, 필요할 때 `--dataset`으로
명시해 사용할 수 있다.

```json
{
  "case_id": "startup-support-001",
  "user_id": 1,
  "question": "초기 창업자를 위한 지원정책을 알려줘",
  "relevant_policy_ids": [101],
  "should_block": false
}
```

FastAPI 서버를 실행한 상태에서 평가한다. 평가기는 정책 추천 전용 서비스를 우회하지
않고 `POST /internal/rag/answer`를 호출하므로 Router부터 Answer까지 실제 LangGraph
실행 결과를 대상으로 검색, Guardrail, 지연시간 지표를 계산한다. 검색 순위는 응답의
`sources[].policy_id` 순서를 사용한다.

```powershell
cd LLM
uv run python -m src.evaluation.run_evaluation --mode policy --k 5
uv run python -m src.evaluation.run_evaluation --mode graph --output evaluation/results/graph_report.json
```

독립 `holdout250`은 최신 DB snapshot을 기준으로 정책·Guardrail 126문항과 세금·로드맵
124턴을 담는다. 실제 평가 전에 다음 명령으로 수량, 계약, 사용자·정책 fingerprint와
정답 정책 Chunk를 API 호출 없이 검증한다. 홀드아웃은 DB 사용자만 허용한다.

```powershell
uv run --no-sync python -m src.evaluation.run_evaluation --suite holdout250 --user-source db --validate-only
```

평가 결과 해석은 `Docs/reports/01_EVAL_BASELINE.md`~`05_TAX_SEMANTIC_CACHE_IMPROVEMENT.md`를 참고한다.

`--prepare-index`는 평가 전에 서버의 `POST /internal/rag/index`를 호출한다. PostgreSQL
모드에서는 DB와 동기화하며 변경된 Chunk가 있으면 Embedding 비용이 발생한다. 평가 결과는
`evaluation/results/latest_report.json`에 저장되며 Git에서 제외된다. 관련 질문은
Query Embedding과 LLM 호출이 발생하므로 실제 평가셋을 반복 실행할 때 API 비용에
주의한다. 무관 질문이 사전 Guardrail에서 차단되면 외부 모델을 호출하지 않는다.

## 로컬 실행

```bash
cd LLM
uv sync
uv run uvicorn main:app --reload --port 8001
```

- Health Check: `http://localhost:8001/health`
- OpenAPI 문서: `http://localhost:8001/docs`

또는 다음 명령으로 `HOST`, `PORT`, `RELOAD` 설정을 사용해 실행할 수 있다.

```bash
uv run python main.py
```

## 테스트

```bash
cd LLM
uv run pytest
```

테스트는 Fake Embedding과 Fake Chat Model을 사용하며 OpenAI, LangSmith 또는
실제 DB에 접속하지 않는다. 다만 원본 PDF(`src/data/RAG_data`)가 필요한 일부 테스트는
파일이 없으면 실패한다(2026-09-15 로컬 실행: 354건 중 346 passed, 8 failed).

## Docker

저장소 루트 `docker-compose.yml`의 `llm` 서비스가 이 폴더를 빌드한다. `8001:8001` 포트,
루트 `.env`(`env_file`), `DATABASE_URL`(compose의 `db` 서비스), `VECTOR_STORE_BACKEND=postgres`,
`PORT=8001`을 주입하고 `./LLM`을 `/app`에 마운트한다. `/health` 헬스체크가 통과해야
Backend가 기동하며, Backend 워밍업이 검색 인덱스를 준비한다. 전체 실행 절차는
`Docs/README.md` 10절과 `setup.sh`를 따른다.
