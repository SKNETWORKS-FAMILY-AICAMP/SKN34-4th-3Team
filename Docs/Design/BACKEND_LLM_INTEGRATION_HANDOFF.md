# Backend↔LLM 연동 인계서

- 작성일: `2026-09-09`
- LLM 계약: `Docs/Design/LLM_API_SPEC_V1.md`
- 대상: Backend·인프라 담당자
- 원칙: Backend 코드는 수정하지 않고 LLM API 구현 상태와 Backend 후속 작업을 인계한다.
- 검수 보고서: `Docs/reports/LLM_INTEGRATION_AUDIT_0909.md`

> **상태: 인계 완료 (2026-09-10 갱신).**
>
> 2절 Backend 필수 수정 체크리스트와 7절 통합 완료 기준은 `d8242fc`에서 충족됐다
> (`Docs/STATUS.md` P0-2-1). 아래 본문은 작성 시점의 지침을 그대로 두되, 이후 결정·구현
> 결과를 각 절에 덧붙였다. 남은 것은 실제 OpenAI·Cohere·PostgreSQL을 쓴 통합 검증(6절)뿐이다.
> 계약 정본은 `Docs/Design/LLM_API_SPEC_V1.md`다.

## 1. 현재 상태

LLM은 다음 Backend용 공개 API를 제공한다.

| Method | Endpoint | 용도 |
| --- | --- | --- |
| `GET` | `/health` | LLM 프로세스 상태 |
| `GET` | `/rag/ready` | 모델·RAG 인덱스 준비 상태 |
| `POST` | `/rag/reindex` | 전체 재색인·검색기 준비; 부분 재색인은 합의 전 실험 기능 |
| `POST` | `/rag/chat` | Policy·Notice·Tax·Roadmap 통합 질의 |
| `POST` | `/rag/legal-basis` | Backend 세액감면 판정 근거 설명 |
| `POST` | `/rag/deductibility` | 경비 인정 가능성 분석 |
| `POST` | `/rag/summarize-announcement` | 공고문 구조화 요약 |
| `POST` | `/ocr/receipt` | 영수증 Vision 필드 추출 |

작성 시점 LLM 테스트 결과는 `222 passed`였다. 2026-09-15 기준 테스트는 354건이며 로컬 실행에서
`346 passed, 8 failed`(원본 PDF 등 로컬 데이터 의존 테스트)다. Fake 모델과 임시 인덱스를
사용하며 실제 OpenAI, Cohere, PostgreSQL에는 요청하지 않는다. Backend 측 계약 준수 작업은
`d8242fc`에서 완료됐다(상단 상태 참고).

### PR 전 합의가 필요한 항목

다음 항목은 Backend 담당자가 그대로 구현하면 안 되며 담당자 간 결정을 먼저 내려야 한다.

1. `category`를 Router의 단순 힌트로 유지할지, 허용 route를 강제하는 제약으로 사용할지
   — **강제 쪽으로 확정.** `LLM/src/rag/graph.py`의 `_route_for_category`가 Backend category로
   route를 확정한다(`tax`·`expense` → tax, `saving` → tax\|policy, `policy` → policy\|notice).
2. `/rag/reindex.documentIds`가 원천 문서 ID인지 `rag_documents.id`인지
   — **`rag_documents.id`로 확정.** `Docs/Design/LLM_API_SPEC_V1.md` 8절에 반영됨.
3. ~~Tax Multi-hop을 포함한 `/rag/chat` timeout 운영값~~ — **2026-09-10 결정.**
   Backend가 카테고리별로 적용한다. `policy`·`roadmap`은 45초(대화 문맥 복원 호출 반영, 최초 30초),
   `tax`·`expense`·`saving`은
   실측값 120초다. LLM의 `_route_for_category`가 `tax`·`expense`를 tax 멀티홉으로
   강제하므로 두 값이 갈린다. 구현은 `Backend/core/config.py`의 `LLM_TIMEOUT_*` 상수이며
   각각 동명 환경변수로 덮어쓸 수 있다.
4. 영수증 지원 형식과 4 MiB 제한을 정식 계약으로 확정할지
   — **확정.** 다만 검사 위치가 양쪽이 다르다. 4 MiB 한도(초과 시 413)는 Backend
   (`Backend/api/expenses.py`의 `MAX_RECEIPT_BYTES`)와 LLM(`LLM/src/serving/rag_routes.py`)
   양쪽에 있지만, **MIME 검증(`image/jpeg`·`image/png`·`image/webp`, 그 밖은 415)은 LLM에만
   있다**(`rag_routes.py:780-784`). Backend는 형식을 검사하지 않고 그대로 넘기며, LLM이 415를
   돌려줘도 `_post_multipart`가 `None`으로 삼키고(`Backend/core/llm_client.py:243-246`)
   `expense_service.create_receipt`가 목 값으로 200(`ocrSource=mock`)을 반환한다. 즉 지원하지
   않는 형식이 사용자에게 415로 드러나지 않는다.

category 정책 충돌은 해소됐다. `LLM/LANGGRAPH_ARCHITECTURE.md`도 category를 허용 route
제약으로 기술하며, Backend의 카테고리별 timeout은 이 강제 동작에 의존한다.

## 2. Backend 필수 수정 체크리스트

### 2.1 `Backend/core/llm_client.py`

- 문서 주석의 기준을 `LLM_API_SPEC_V1.md`로 변경한다.
- 다음 `/internal/*` fallback을 모두 제거한다.
  - `/internal/rag/ready`
  - `/internal/rag/index`
  - `/internal/rag/answer`
  - `/internal/ocr/receipt`
  - `/internal/summarize/announcement`
  - `/internal/explain/tax-reduction`
- `rag_answer()`가 `user_context`, `notice_results`를 선택적으로 받도록 확장한다.
- `sources[].url`을 우선 사용하고 URL이 없을 때만 `sources[].source`를 사용한다.
- `explain_expense()`가 `/rag/deductibility` 성공 응답을 변환할 때 `sources: []`로
  덮어쓰지 말고 LLM이 반환한 `sources`를 그대로 보존한다.
- `urllib.error.HTTPError`를 무조건 `None`으로 삼키지 않는다. 응답 JSON의
  `error.code`, `error.message`, `error.retryable`과 HTTP 상태를 구조화해 로그에 남긴다.
- 연결 실패·timeout·JSON 파싱 실패를 서로 구분한다. API Key, DB URL, 사용자 입력 원문은
  로그에 남기지 않는다.
- `ensure_index()`와 관리자 재색인을 분리한다.
  - 일반 질의 준비: `/rag/ready`가 준비되면 재색인을 생략할 수 있다.
  - 관리자 명시적 재색인: 준비 상태와 관계없이 `/rag/reindex`를 호출해야 한다.
- `/rag/legal-basis`, `/rag/deductibility`도 RAG 인덱스를 사용하므로 호출 전에
  `ensure_index_ready()` 또는 서버 startup 준비를 보장한다.
- `documentIds` 의미가 확정되기 전에는 `documentIds: []`로 전체 재색인만 호출한다.
- 현재 LLM의 비어 있지 않은 `documentIds`는 `rag_documents.id`로 해석하지만 원천 변경을
  다시 읽지 않으므로 Backend 운영 기능으로 사용하지 않는다.
- PostgreSQL이 아닌 in-memory 모드에서는 비어 있지 않은 `documentIds`가 422를 반환한다.

권장 함수 경계:

```python
def ensure_index_ready() -> bool: ...
def reindex_rag(document_ids: list[int] | None, force: bool = False) -> dict: ...
def rag_answer(question: str, *, category: str,
               user_context: dict | None,
               notice_results: list[dict] | None) -> dict: ...
```

### 2.2 `Backend/services/chat_service.py`

현재 사용자 정보를 질문 문자열 앞에 붙이는 `_profile_prefix()`만으로는 나이·창업일 등
개인화 필드가 구조적으로 전달되지 않는다. 인증 사용자와 사업자 프로필을 다음 형태로
조립해 `rag_answer()`에 전달한다.

```json
{
  "userId": 1,
  "age": 29,
  "region": "서울",
  "businessType": "개인사업자",
  "industry": "소프트웨어",
  "businessRegisteredAt": "2026-02-01",
  "foundedAt": "2026-01-15"
}
```

- `userId`는 필수다.
- 없는 값은 `null`로 전달하며 임의로 추정하지 않는다.
- 날짜 객체는 `YYYY-MM-DD` 문자열로 직렬화한다.
- 구조화 Context를 전달한 뒤 중복되는 `_profile_prefix()` 삽입은 제거하는 것을 권장한다.

### 2.3 공고 조회와 `noticeResults`

실제 공고 조회·날짜 필터는 Backend 책임이다. `category=policy` 요청에서는 질문 조건으로
공고를 조회한 뒤 다음 형태로 전달한다.

```json
{
  "announcementId": 10,
  "policyId": 3,
  "title": "서울 청년창업 지원사업 모집",
  "content": "공고 원문 또는 검색용 요약",
  "benefit": "사업화 자금 최대 2천만원",
  "sourceUrl": "https://example.org/announcement/10",
  "applyStartDate": "2026-09-01",
  "applyEndDate": "2026-09-30"
}
```

값의 의미를 반드시 구분한다.

| 전달값 | 의미 | LLM 결과 |
| --- | --- | --- |
| 필드 누락 또는 `null` | Backend 조회 기능을 사용할 수 없음 | Notice route에서 `integration_unavailable` |
| `[]` | 조회 성공, 조건에 맞는 공고 없음 | Notice route에서 `no_result` |
| 결과 배열 | 조회 성공 | 전달받은 공고만으로 답변 |

LLM은 공고의 모집 상태를 자체 Vector 검색으로 판정하지 않는다.

### 2.4 응답 처리

`/rag/chat`의 주요 응답 필드는 다음과 같다.

```json
{
  "answer": "답변",
  "sources": [],
  "grounded": false,
  "route": "tax",
  "status": "insufficient_evidence",
  "guardrail_reason": "insufficient_evidence"
}
```

- `status=success`이고 `grounded=true`일 때만 근거가 확보된 답변으로 처리한다.
- `need_more_info`는 추가 사용자 입력을 요청한다.
- `integration_unavailable`은 공고 조회 또는 RAG 준비 실패로 안내한다.
- `guardrail_reason=out_of_scope`(이때 `status=no_result`)는 서비스 범위 밖 질문으로 처리하며 검색을 재시도하지 않는다.
- `sources`는 LLM이 실제로 인용한 문서만 저장한다.
- 세액감면 근거, 경비 분석, 공고 요약, OCR 응답의 `llmUsed`를 Backend 외부 응답에 보존한다.
- `explain_expense()`가 `/rag/deductibility` 응답의 `sources`를 빈 배열로 덮어쓰지 않도록
  실제 LLM 응답 sources를 그대로 전달한다.
- LLM의 공통 오류 형식은 Runtime에는 적용됐지만 OpenAPI `responses`에는 아직 완전히
  기술되지 않았다. Backend 구현은 V1 예시와 실제 통합 테스트 응답을 함께 확인한다.

### 2.5 공통 오류 처리

LLM의 모든 비-2xx 응답은 다음 형식이다.

```json
{
  "error": {
    "code": "RAG_INDEX_NOT_READY",
    "message": "RAG index is not ready.",
    "retryable": true
  }
}
```

Backend 처리 권장안:

| HTTP | 대표 코드 | 처리 |
| --- | --- | --- |
| `409` | `RAG_INDEX_NOT_READY` | 준비 상태 확인 후 관리자·운영 절차로 재색인 |
| `413` | `PAYLOAD_TOO_LARGE` | 사용자에게 4 MiB 제한 안내 |
| `415` | `UNSUPPORTED_MEDIA_TYPE` | JPEG·PNG·WebP 안내 |
| `422` | `VALIDATION_ERROR` | 요청 조립 오류 또는 사용자 입력 오류 구분 |
| `429` | `RATE_LIMITED` | 자동 POST 재시도 금지, 잠시 후 재요청 안내 |
| `502` | `UPSTREAM_RESPONSE_ERROR` | LLM 응답 검증 실패로 기록 |
| `503` | `SERVICE_UNAVAILABLE` | 모델·DB·연결 설정 확인 |
| `504` | `UPSTREAM_TIMEOUT` | timeout으로 기록하고 사용자에게 재시도 안내 |

위 표는 **권장안이며 구현 현황이 아니다.** 현재 `Backend/core/llm_client.py`는 비-2xx 응답의 `error.code`·`error.retryable`과 HTTP 상태를 로그에만 남기고(`_log_http_error`) 호출자에게는 `None`을 돌려준다. 따라서 `413`·`415` 같은 코드가 사용자 응답으로 구분돼 나가지 않는다 (영수증 업로드는 대신 목 추출로 200을 반환한다. 1절 4번 참고).

## 3. Endpoint별 Backend 확인사항

### `/rag/legal-basis`

- Backend가 `eligible`, `reasons`, `conditions`를 전달한다.
- LLM은 `eligible` 판정을 변경하지 않고 `legalBasis`만 생성한다.
- 호출 전 RAG 인덱스가 준비되지 않으면 409가 발생한다.
- `legalBasis`와 `sources`가 없으면 Backend의 Rule 판정만 표시하고 최종 판단이 아니라는
  안내를 유지한다.

### `/rag/deductibility`

- 요청: `category`, `amount`, `vendor`, `items`
- 응답: `deductible`, `confidence`, `basis`, `sources`, `grounded`, `status`, `llmUsed`
- 경비 인정 여부는 참고 가능성이므로 사용자 화면에서 확정 판정처럼 표현하지 않는다.

### `/rag/summarize-announcement`

- Backend가 원문과 출처를 전달한다.
- `source`는 LLM이 새로 만들지 않고 요청값을 보존한다.
- `announcement_summaries` 캐시 조회·저장은 계속 Backend가 담당한다.

### `/ocr/receipt`

- `multipart/form-data`의 파일 필드명은 `image`다.
- 허용 형식: JPEG, PNG, WebP
- 최대 크기: 4 MiB
- 인식하지 못한 필드는 `null` 또는 빈 배열이므로 Backend가 샘플 값으로 오인하지 않아야 한다.
- 실제 영수증 인식 품질은 아직 검증하지 않았다.

### `/rag/reindex`

- `documentIds` 누락 또는 `[]`: 전체 원천 문서 동기화
- **현재 Backend 연동에서는 전체 재색인만 사용한다.**
- 비어 있지 않은 `documentIds`의 정식 의미는 Backend·LLM·DB 담당자 합의 전이다.
- 현재 LLM 실험 구현은 값을 PostgreSQL `rag_documents.id`로 해석한다.
- 이 실험 구현은 파생 행의 기존 content를 다시 사용하므로 정책·공고·세법 원천 변경을
  부분 반영하지 못한다. FS-27의 원천 변경 감지 구현으로 간주하면 안 된다.
- `force=false`: 전체 재색인에서는 동일 본문을 재사용한다. 현재 PostgreSQL 구현은
  Embedding 모델 변경을 자동 비교하지 않으므로 모델 변경 배포에서는 사용할 수 없다.
- `force=true`: 전체 대상 또는 실험적 부분 대상을 다시 Embedding한다.
- 명시적 관리자 요청은 현재 인덱스가 준비돼 있어도 LLM에 전달한다.
- 부분 재색인은 대상 외 `rag_documents`를 삭제하지 않는다.
- `policies`, `announcements`, `tax_documents` 원본은 LLM이 수정하지 않는다.

부분 재색인 계약 후보:

1. `{ sourceType, sourceId }[]`로 원천을 지정하고 최신 원천을 다시 Chunking한다.
2. `rag_documents.id[]`는 기존 Chunk 강제 재임베딩으로만 제한하고 원천 변경 반영 API를
   별도로 둔다.

## 4. Timeout과 재시도

**확정됨.** 단일 25초 timeout이 Tax Multi-hop 실데이터 검증에서 부족했던 문제는
endpoint·category별 값으로 해소됐다. 확정값 표는 `Docs/Design/LLM_API_SPEC_V1.md` 9절에 있고,
구현은 `Backend/core/config.py`의 `LLM_TIMEOUT_*` 상수다. 각 상수는 동명 환경변수로 덮어쓸 수 있다.

핵심만 옮기면 `/rag/chat`은 `category=policy`·`roadmap` 45초, `tax`·`expense`·`saving` 120초로 갈린다.
LLM의 `_route_for_category`가 뒤 셋을 tax 멀티홉으로 보내기 때문이다. 실측 최대는 11.7초였다.

- **자동 재시도는 GET·POST 어디에도 없다.** `Backend/core/llm_client.py`의 `_request`·`_post_multipart`가 단일 시도로 끝나고 실패는 `None`이다. 상태 조회 실패는 `llm_status()`의 `reachable=false`로 드러난다.
- POST는 비용·중복 작업 방지를 위해 자동 재시도하지 않는다.
- 프론트 `api.chat`은 tax 계열 135초, 그 외 60초로 서버 예산보다 길게 기다린다(`e619d23`).

## 5. Docker·환경 설정 — 배선 완료

- 최신 `docker-compose.yml`과 `Docs/STATUS.md` 기준 P0-1 서비스 배선은 해결됐다.
- 로컬 실행: `LLM_API_URL=http://127.0.0.1:8001`
- Docker Compose: `LLM_API_URL=http://llm:8001`
- 컨테이너의 `127.0.0.1`은 Backend 자신이므로 LLM 연결 주소로 사용할 수 없다.
- Backend 컨테이너에는 OpenAI·Cohere Key를 전달하지 않는다.
- LLM 컨테이너에만 모델·Embedding·Cohere·DB 환경변수를 전달한다.
- Backend 담당자는 신규 배선 작업 대신 현재 주입값이 유지되는지만 회귀 확인한다.

## 6. 담당자 통합 테스트 순서

실제 모델 호출과 재색인은 외부 전송·비용·DB 파생 데이터 변경이 발생하므로 팀 승인 후
실행한다.

1. `GET http://llm:8001/health`가 200인지 확인한다.
2. `GET http://llm:8001/rag/ready`에서 모델 설정과 인덱스 상태를 확인한다.
3. 인덱스 준비 여부를 확인한다. Backend 기동 시 워밍업 스레드가 미준비면 `/rag/reindex`를 자동으로 한 번 호출하므로(변경 Chunk가 있으면 Embedding 비용 발생) 수동 실행은 LLM만 재시작한 경우에 한다.
4. Backend `/chat/messages`에서 일반 Policy 질문을 확인한다.
5. 인증 프로필이 포함된 개인화 Policy·Tax 질문을 확인한다.
6. `noticeResults=null`, `[]`, 결과 존재 세 경우를 확인한다.
7. 세액감면 판정 결과가 LLM 설명에 의해 뒤집히지 않는지 확인한다.
8. 영수증 이미지를 한 장씩 JPEG·PNG로 확인한다.
9. 공고 요약의 날짜·금액이 원문에 없는 값으로 생성되지 않는지 확인한다.
10. 422·409·429·503·504 응답이 Backend 로그와 사용자 안내로 구분되는지 확인한다.
11. 경비 분석의 `sources`가 `answer_sources`까지 보존되는지 확인한다.
12. category와 질문 의미가 충돌하는 사례로 합의한 Router 정책이 적용되는지 확인한다.
13. 부분 재색인은 계약 확정과 별도 DB 백업 전에는 실행하지 않는다.

## 7. 통합 완료 기준

아래 기준은 마지막 항목(실모델 통합 테스트)을 제외하고 모두 충족됐다.

- Backend에서 `/internal/*` LLM 경로 호출이 없다.
- 필요한 모든 요청이 404 없이 LLM에 도달한다.
- 개인화 질문에 구조화된 `userContext`가 전달된다.
- Notice 질문에 Backend 조회 결과가 전달된다.
- `status`, `guardrail_reason`, `sources`, `llmUsed`가 유실되지 않는다.
- 관리자 재색인이 준비 상태와 관계없이 실행된다.
- HTTP 오류가 단순 `None`으로 사라지지 않고 코드별로 기록된다.
- 이미 완료된 Docker 배선(`http://llm:8001`)이 회귀하지 않는다.
- 승인된 실제 OpenAI·Cohere·PostgreSQL 통합 테스트가 통과한다.
- category Router 정책, 부분 재색인 ID 의미와 timeout 운영값에 담당자 합의 기록이 있다.

## 8. 알려진 제한사항

- 실제 모델과 실제 영수증 이미지 품질은 아직 검증하지 않았다.
- PostgreSQL 부분 재색인은 아직 운영 사용 승인이 없다. 현재 구현은 기존
  `rag_documents.id` 행의 저장 content만 재사용하며 원천 변경을 다시 읽지 않는다.
- 신규 원천 문서는 전체 재색인으로 최초 Chunk를 생성해야 한다.
- in-memory 모드는 DB 행 ID가 없으므로 부분 재색인을 지원하지 않는다.
- PostgreSQL의 기존 Embedding 재사용 판단은 현재 content만 비교하며 Embedding 모델명은
  비교하지 않는다. 모델 변경 시 승인 후 `force=true` 전체 재색인이 필요하다.
- LLM 단독 테스트 통과는 현재 Backend 코드의 계약 준수를 증명하지 않는다.
- 원본 설계 문서 `Docs/Design/LLM_API_SPEC.md`와 일부 아키텍처 문서에는 과거 포트·응답
  예시가 남아 있으므로 V1과 이 인계서를 연동 기준으로 사용한다.

## 9. PR 전 LLM 측 보완 상태

Backend 담당 작업과 별개로 다음은 LLM PR에서 먼저 결정하거나 수정해야 한다.

- ~~`category` 강제 route와 최신 LangGraph 구조 문서의 힌트 정책 중 하나로 통일~~ — 강제 route로 통일됨
- 부분 재색인을 원천 재조회 방식으로 수정하거나 실험 기능으로 명시해 비활성화
- Embedding 모델 변경 감지 또는 모델 변경 시 강제 전체 재색인 운영 규칙 확정
- 공통 오류 envelope schema를 OpenAPI 응답에 명시
- 실제 영수증 파일과 Vision 모델로 OCR 품질 확인

세부 근거와 우선순위는 `Docs/reports/LLM_INTEGRATION_AUDIT_0909.md`를 참고한다.
