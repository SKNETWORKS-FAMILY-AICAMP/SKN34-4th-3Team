# LLM 서비스 실행 가이드

현재 LLM 서비스는 FastAPI + LangGraph 기반이며 기본 포트는 `8001`이다.

## 1. 사전 준비

필요한 항목:

- Python 3.13 이상
- `uv`
- PostgreSQL + pgvector (`DB/01_schema.sql`, `DB/app_extras.sql` 적용. 세금 Semantic Cache는 `app_extras.sql`의 `tax_rag_cache` 테이블을 쓴다)
- 실제 질문 테스트 시 OpenAI API 설정
- Cohere Rerank 사용 시 Cohere API 설정

실제 secret은 `.env.example`이 아니라 `.env`에만 작성한다. `.env`는 Git에
커밋하지 않는다.

설정 우선순위:

```text
시스템 환경변수 > LLM/.env > 저장소 루트 .env > 코드 기본값
```

필수 또는 주요 설정:

```dotenv
PORT=8001
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
VECTOR_STORE_BACKEND=postgres
LLM_MODEL=...
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=...
COHERE_API_KEY=...
TAX_CACHE_ENABLED=true
TAX_CACHE_SIMILARITY_THRESHOLD=0.95
TAX_CACHE_DECISION_SIMILARITY_THRESHOLD=0.98
```

`COHERE_API_KEY`가 없으면 Cohere Rerank 대신 RRF 결과를 사용한다. `tax_rag_cache`
테이블이 없으면 세금 캐시 조회가 경고 로그만 남기고 일반 Multi-hop으로 진행한다.

## 2. 의존성 설치

저장소 루트에서:

```powershell
cd LLM
uv sync
```

다른 프로젝트의 가상환경이 활성화돼 다음 경고가 발생하면:

```text
VIRTUAL_ENV=... does not match the project environment path .venv
```

기존 환경을 비활성화한 뒤 실행한다.

```powershell
deactivate
cd LLM
uv sync
```

`deactivate`가 없으면 새 PowerShell 터미널을 연다. DB 프로젝트의 `.venv`로 LLM을
실행하지 않는다.

## 3. LLM 서버 실행

반드시 `LLM/` 디렉터리에서 실행한다.

```powershell
cd LLM
uv run python main.py
```

또는 uvicorn을 직접 실행할 수 있다.

```powershell
cd LLM
uv run uvicorn main:app --host 0.0.0.0 --port 8001
```

정상 시작 로그:

```text
Application startup complete.
Uvicorn running on http://0.0.0.0:8001
```

종료는 실행 터미널에서 `Ctrl+C`를 누른다.

## 4. 상태 확인

브라우저:

```text
http://localhost:8001/health
http://localhost:8001/docs
```

PowerShell:

```powershell
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8001/rag/ready
```

`/health`에서 확인할 항목:

- LLM 모델 설정
- Embedding 모델 설정
- Vector Store 설정

`/rag/ready`의 `index_ready`는 DB에 Embedding이 존재한다는 의미가 아니다. 현재
LLM 프로세스에 pgvector 검색기와 메모리 BM25 검색기가 준비됐다는 의미다.

## 5. 검색기 준비

LLM 프로세스는 기동 시 검색기를 스스로 준비하지 않는다. 저장소 루트에서 Docker Compose나
`setup.sh`로 전체를 띄우면 Backend 워밍업 스레드가 `/rag/ready`를 확인하고 준비되지
않았으면 `/rag/reindex`를 한 번 호출하므로 이 절차가 필요 없다. LLM만 따로 실행했거나
LLM 컨테이너만 재시작했으면 직접 준비한다.

```powershell
$body = @{
    documentIds = @()
    force = $false
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://localhost:8001/rag/reindex `
    -ContentType "application/json" `
    -Body $body
```

응답 예시:

```json
{
  "status": "already_ready",
  "source": "cache",
  "document_count": 9770,
  "chunk_count": 11793,
  "requested_document_ids": []
}
```

- `status=already_ready` + `source=cache`: 새로 임베딩한 Chunk 없이 기존 Embedding을 재사용
- `status=ready` + `source=embedding`: 신규 또는 변경 Chunk를 임베딩
- 수치는 예시다. 실제 값은 `GET /api/health`의 `ragChunks`와 대조한다

`force=true`는 전체 문서를 다시 임베딩하므로 API 비용과 외부 데이터 전송이
발생한다. 명확한 필요와 승인이 없으면 사용하지 않는다.

준비 전 `/rag/chat`은 오류가 아니라 200 + `status=integration_unavailable`로 응답한다.

## 6. RAG 질문 테스트

Backend 어댑터 계약을 직접 시험한다.

```powershell
$body = @{
    category = "tax"
    question = "청년창업 세액감면이 뭐야?"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://localhost:8001/rag/chat `
    -ContentType "application/json" `
    -Body $body
```

실제 질문은 다음 외부 호출을 발생시킬 수 있다.

- Query Embedding(검색어별, 세금 캐시 조회용 질문 Embedding 포함)
- OpenAI 호출: 대화 문맥 복원, Router, Tax Intent, 계산 입력 Planner, Evidence 판정,
  Next Query, Answer(경로에 따라 일부만)
- Cohere Rerank 호출
- PostgreSQL 조회와 `tax_rag_cache` 저장

비공개 문서나 개인정보를 사용하기 전에 외부 전송 정책을 확인한다.

## 7. 화면에서 확인

Frontend는 LLM을 직접 호출하지 않고 Backend `/api`만 호출한다. 화면으로 확인하려면
Backend 8000까지 실행한 뒤 Frontend를 띄운다.

```powershell
cd Frontend
npm.cmd ci
npm.cmd run dev
```

접속 주소:

```text
http://localhost:5173
```

전체 기동은 저장소 루트 `setup.sh`·`setup.bat`(`Docs/README.md` 10절)이 가장 간단하다.

## 8. 테스트 실행

실제 OpenAI, Cohere 또는 DB 쓰기 없이 자동 테스트를 실행한다.

```powershell
cd LLM
uv run pytest -q
```

일부 PDF 테스트는 로컬 `src/data/RAG_data`에 원본 PDF가 있어야 한다. PDF는 Git에
포함되지 않는다. 2026-09-15 로컬 실행 결과는 354건 중 `346 passed, 8 failed`였으며
실패는 이런 로컬 데이터 의존 테스트다.

## 9. 자주 발생하는 문제

### `No module named 'src.features'`

대부분 `DB/` 또는 저장소 루트에서 잘못 실행한 경우다.

```powershell
cd LLM
uv run python main.py
```

### `http://localhost:8001` 연결 실패

- LLM 프로세스가 실행 중인지 확인한다.
- 실행 로그의 실제 포트를 확인한다.
- `.env`의 `PORT`가 `8001`인지 확인한다.

### 모든 질문이 `integration_unavailable`

검색기가 준비되지 않은 상태다. `/rag/ready`의 `index_ready`를 확인하고 5절대로 준비한다.

### 모든 질문이 `no_result` 또는 `error`

1. `/rag/ready`에서 `index_ready=true`인지 확인한다.
2. 서버 로그의 `termination_reason`을 확인한다.
3. DB 연결과 `rag_documents`의 ready Embedding을 확인한다.
4. pgvector Query 타입 오류, OpenAI Structured Output 오류 여부를 확인한다.

### Cohere 오류

`COHERE_API_KEY`가 없으면 RRF fallback이 동작한다. 검색은 계속 가능하지만 로그에
Cohere 설정 경고가 남을 수 있다.

## 10. 관련 문서

- `LANGGRAPH_ARCHITECTURE.md`: 현재 GraphState, node, edge 및 Tax Multi-hop 구조
- `README.md`: 전체 LLM/RAG 기능 설명
- `.env.example`: 환경변수 예시
- `../Docs/Design/LLM_API_SPEC_V1.md`: Backend↔LLM API 정본
