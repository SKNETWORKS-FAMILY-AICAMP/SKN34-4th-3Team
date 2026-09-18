# LLM 연동 1~7단계 검수 보고서

- 검수일: `2026-09-09`
- 검수 HEAD: `f19e6db`
- 검수 대상: 현재 작업 트리의 LLM 변경과 신규 V1/인계 문서
- 기준 문서: `Docs/STATUS.md`, `Docs/Design/*`, `LLM/LANGGRAPH_ARCHITECTURE.md`, `LLM/RUN_GUIDE.md`
- 원칙: 기존 문서는 수정하지 않고 검수 결과만 별도 기록한다.

## 1. 최종 판정

현재 변경은 자동 테스트 기준으로 안정적이지만, 최신 문서와의 정합성 및 운영 의미까지
포함하면 아직 최종 완료로 판정할 수 없다.

| 단계 | 판정 | 요약 |
| --- | --- | --- |
| 1. V1 계약 작성 | 보완 필요 | 기존 초안의 미확정 사항을 팀 합의 없이 확정한 항목 존재 |
| 2. 누락 LLM API 구현 | 조건부 통과 | 네 API 구현 및 Fake 테스트 통과, 실제 모델·DB 검증 미실시 |
| 3. Context/Notice 수신 | LLM 측 통과 | LLM 수신·검증 완료, 현재 Backend는 미전송 |
| 4. 응답·오류 통일 | 조건부 통과 | Runtime 응답 통일 완료, OpenAPI 오류 schema 미반영 |
| 5. 계약 테스트 | 통과 | 병합 후 전체 `222 passed` |
| 6. Router·재색인 | 보완 필요 | 최신 구조 문서와 Router 정책 충돌, 부분 재색인 의미 결함 |
| 7. Backend 인계 | 보완 필요 | 최신 Compose 해결 상태와 일부 구현 제약 반영 필요 |

병합 권장 상태는 **보완 후 재검수**다.

## 2. 주요 발견사항

### 높음 — Router 정책이 최신 구조 문서와 충돌

`LLM/LANGGRAPH_ARCHITECTURE.md:54-55`는 `category`를 Router 힌트로 사용하고 코드에서
route를 강제하지 않는다고 명시한다. 현재 변경의 `LLM/src/rag/graph.py:171-185`는 다음과
같이 route를 강제로 제한한다.

- `tax`, `expense` → 항상 `tax`
- `saving` → `tax` 또는 `policy`, 이외 결과는 `tax`
- `policy` → `policy` 또는 `notice`, 이외 결과는 `policy`

이 변경은 테스트에는 통과하지만 최신 구조 문서의 불변 의도와 다르다. 잘못 선택한 화면
카테고리 때문에 질문 의미보다 카테고리가 우선될 수 있다. 팀 결정 전에는 기존 Router
판정을 유지하거나, 문서에서 category를 강제 제약으로 변경하기로 합의해야 한다.

### 높음 — 부분 재색인이 FS-27의 원천 변경 감지를 충족하지 못함

`Docs/Design/FUNCTIONAL_SPEC.md`의 FS-27은 원천 데이터 변경 감지 후 Embedding과
Vector DB를 갱신하는 흐름이다. 현재 부분 재색인은 `rag_documents.id`로 기존 파생 행을
읽은 뒤 같은 행의 기존 `content`를 다시 처리한다.

문제점:

1. `force=false`이면 기존 행의 content를 기존 행과 비교하므로 원칙적으로 변경을 찾을 수 없다.
2. `force=true`도 정책·공고·세법 원천의 최신 내용을 다시 읽지 않고 파생 행의 기존 내용을
   재임베딩한다.
3. `document_count`와 `chunk_count`를 모두 선택한 `rag_documents` 행 수로 반환한다.
   `rag_documents` 한 행은 Chunk이므로 두 값의 의미가 같아진다.
4. 기존 명세의 `documentIds`는 대상 테이블을 확정하지 않았다. V1에서
   `rag_documents.id`로 정한 것은 Backend·DB 담당자 확인이 필요하다.

부분 재색인의 안전한 계약 후보는 다음 중 하나다.

- `{ sourceType, sourceId }[]`로 원천 레코드를 지정하고 원천을 다시 Chunking한다.
- `rag_documents.id[]`는 기존 Chunk의 강제 재임베딩 전용으로 한정하고, 원천 변경 반영은
  전체 또는 별도의 source 재색인 API로 분리한다.

### 높음 — Embedding 모델 변경을 자동 감지하지 않음

`LLM/src/vectorstores/postgres.py:300-313`의 `_existing_hashes()`는 `chunk_id`와 `content`
만 조회한다. 함수 설명과 V1 계약은 Embedding 모델 설정도 비교한다고 적었지만 실제 DB
schema에는 `embedding_model` 컬럼이 없고 코드도 모델을 비교하지 않는다.

따라서 Embedding 모델이 바뀌어도 `force=false`이면 기존 Vector를 재사용할 수 있다.
모델 또는 차원이 바뀌는 배포에서는 반드시 `force=true`가 필요하며, 장기적으로 모델명을
파생 metadata에 저장해 비교해야 한다.

### 높음 — V1의 Chat timeout 30초는 최신 실측과 맞지 않음

기존 `LLM_API_SPEC.md`는 timeout·재시도를 팀 미확정으로 남겼다. V1은 `/rag/chat`을
30초로 확정했지만 `Docs/STATUS.md:105`는 Tax Multi-hop에서 Backend 기본 25초가 부족해
`LLM_TIMEOUT_SECONDS=120`으로 검증했다고 기록한다.

30초는 Policy 단일 질의에는 충분할 수 있으나 Tax Multi-hop 운영값으로 검증되지 않았다.
Endpoint별 수치는 실제 P95/P99 측정이나 최소한 Tax 최악 경로 측정 후 확정해야 한다.

### 중간 — 최신 Docker 배선 상태가 인계 문서에 완전히 반영되지 않음

`Docs/STATUS.md:22-60`과 현재 `docker-compose.yml`에 따르면 Backend의
`LLM_API_URL=http://llm:8001`, 포트, 환경변수와 의존성 배선은 이미 해결됐다.
`LLM_API_SPEC_V1.md:420`은 이를 Backend 남은 작업으로 기록한다.

최종 인계 시 Docker 주소는 신규 구현 과제가 아니라 확인 완료 항목으로 분리해야 한다.

### 중간 — 실제 Backend가 전용 API 호출 전에 인덱스를 보장하지 않음

현재 `Backend/core/llm_client.py`의 `rag_answer()`만 `ensure_index()`를 호출한다.
`explain_tax_reduction()`과 `explain_expense()`의 첫 전용 API 호출은 인덱스 준비를
보장하지 않는다.

- `/rag/legal-basis`: 인덱스 미준비 시 409 후 Backend가 `None`으로 처리
- `/rag/deductibility`: 409 후 일반 `/rag/chat` fallback에서 인덱스를 준비

Backend 인계서에는 전용 RAG API 전에 `ensure_index_ready()`를 호출하거나 서버 startup
준비를 보장하도록 명확히 적어야 한다.

### 중간 — 경비 분석 출처가 현재 Backend에서 유실됨

LLM의 `/rag/deductibility`는 `sources`를 반환한다. 그러나
`Backend/core/llm_client.py:105-111`은 응답을 변환하면서 `sources: []`로 고정한다.
FS-17의 RAG 근거와 FS-08 출처 보존을 위해 Backend가 실제 응답 sources를 유지해야 한다.

### 중간 — 오류 Runtime 계약은 통일됐지만 OpenAPI schema는 불완전

전역 예외 handler로 실제 비-2xx 응답은 `{error:{code,message,retryable}}` 형식을 사용한다.
그러나 각 FastAPI route의 `responses` 또는 공통 ErrorResponse model이 OpenAPI에 선언되지
않았다. 실행 테스트는 통과하지만 생성 client와 `/docs`만 보는 담당자는 기본 FastAPI
422 schema를 보게 된다.

### 중간 — 영수증 테스트는 실제 이미지 판독 검증이 아님

현재 테스트는 `Content-Type=image/jpeg`인 임의 byte를 Fake 모델에 전달해 multipart와
응답 schema를 검증한다. 실제 JPEG/PNG 디코딩, 실제 Vision 모델의 인식 정확도,
회전·흐림·한글 영수증은 검증하지 않았다. MIME 헤더만 검사하므로 잘못 표시된 파일도
모델 호출 직전까지 통과한다.

또한 최신 FS-14는 파일 형식·용량 제한을 TBD로 남겼다. V1의 JPEG/PNG/WebP 및 4 MiB
제한은 Backend 업로드 제한과 일치하지만 팀 계약으로 확인해야 한다.

### 낮음 — 최신 설명 문서가 현재 작업을 반영하지 않음

- `Docs/STATUS.md`는 아직 누락 Endpoint 문제를 미해결로 기록한다.
- `LLM/LANGGRAPH_ARCHITECTURE.md`는 Backend 어댑터를 세 개만 기록한다.
- 같은 문서의 테스트 기준은 `190 passed`이며 현재 기준은 `222 passed`다.

이는 코드 결함은 아니며 현재 변경이 아직 커밋되지 않았기 때문에 자연스럽다. 기존 문서를
수정하지 않는 원칙을 유지한다면 이 감사 보고서와 V1 문서를 함께 인계해야 한다.

## 3. 단계별 세부 검수

### 1단계 — V1 계약

잘된 점:

- 원본 초안을 보존했다.
- 공개 Endpoint, 성공 응답, 오류 envelope와 역할 경계를 구체화했다.
- `noticeResults=null`과 `[]`의 의미를 분리했다.

보완점:

- timeout 수치, `documentIds` 의미, category 강제 route는 팀 합의가 확인되지 않았다.
- V1을 “확정”으로 부르기 전에 Backend·DB 담당자 승인이 필요하다.

### 2단계 — 누락 API

구현 확인:

- `POST /rag/legal-basis`
- `POST /rag/deductibility`
- `POST /rag/summarize-announcement`
- `POST /ocr/receipt`

모든 경로가 OpenAPI와 Fake API 테스트에 존재한다. 실제 모델·DB 품질 검증은 별도다.

### 3단계 — Context와 Notice

LLM의 Pydantic 수신, Context 변환, Notice의 null/빈 배열/결과 구분은 테스트됐다.
현재 Backend가 해당 필드를 보내지 않는 것은 계획대로 Backend 인계 범위다.

주의: `BackendNoticeResult`는 `extra=forbid`이며 camelCase 계약을 강제하므로 Backend의
현재 snake_case 저장 객체를 그대로 전달하면 422가 발생한다. 명시적 변환이 필요하다.

### 4단계 — 응답과 오류

공통 오류 envelope, 409/413/415/422/429/502/503/504 구분과
`guardrail_reason` 반환은 구현됐다. Backend는 아직 모든 HTTP 오류를 `None`으로 삼킨다.

### 5단계 — 테스트

병합 후 재실행 결과:

```text
222 passed in 38.93s
```

실제 OpenAI, Cohere, PostgreSQL 쓰기는 발생하지 않았다. 부분 재색인의 PostgreSQL route는
Fake 객체로 검증했기 때문에 실제 SQL 통합 검증은 남아 있다.

### 6단계 — Router와 재색인

범위 밖 질문을 검색·LLM 호출 전에 차단하는 동작은 기존 Guardrail 방향과 일치한다.
category 강제 route와 부분 재색인은 위 높은 우선순위 문제를 해결한 뒤 통과 판정해야 한다.

### 7단계 — 인계

`BACKEND_LLM_INTEGRATION_HANDOFF.md`는 파일별 Backend 변경, 오류 처리, Context·Notice,
통합 테스트 절차를 제공한다. 다만 Docker 해결 상태, 실제 timeout 실측, 부분 재색인 계약,
경비 sources 유실을 반영한 정정본이 필요하다.

## 4. 권장 보완 순서

1. Backend·LLM 담당자가 category가 힌트인지 강제 제약인지 결정한다.
2. `documentIds`가 파생 Chunk ID인지 원천 문서 ID인지 확정한다.
3. 결정에 따라 부분 재색인을 원천 재조회 방식으로 재설계하거나 강제 재임베딩 전용으로
   명시한다.
4. Embedding 모델 변경 감지 전략을 정한다.
5. Tax Multi-hop timeout을 실측해 V1 수치를 확정한다.
6. OpenAPI에 공통 오류 schema를 노출한다.
7. 실제 이미지·실제 모델·로컬 검증 DB로 승인된 통합 테스트를 수행한다.
8. 최종 Backend 인계 정정본을 새 파일로 작성한다.

## 5. 변경 금지 확인

이번 검수에서는 기존 문서, Backend 코드, DB schema와 실제 DB를 변경하지 않았다.
생성한 것은 이 감사 보고서 한 파일뿐이다.
