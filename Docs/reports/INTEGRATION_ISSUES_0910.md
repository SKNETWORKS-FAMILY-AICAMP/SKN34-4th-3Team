# feature/integration 통합 결함 목록

- 작성일: 2026-09-10
- 갱신일: 2026-09-14 (`develop` / `8c0484d` 기준으로 상태 재대조)
- 최초 조사 기준: `feature/integration` / `b56b85d`

## 0. 요약

`feature/integration`에서 Backend 데이터 계층 교체(`a01a503`)와 프론트엔드 첫 병합을 감사한 결과임. 조사 당시 33건이었고 이후 검증·통합 중 발견한 34~42를 더해 42건임. 번호는 `Docs/reports/INTEGRATION_ISSUES_0914.md`의 43번 이후로 이어짐.

| 상태 | 건수 | 결함 |
| --- | ---: | --- |
| 해결됨 | 24 | 1~3, 5~8, 10, 11, 16~20, 23, 32, 34~39, 41, 42 |
| 오탐·조치 불필요 | 3 | 4, 22, 31 |
| 미해결 | 15 | 9, 12~15, 21, 24~30, 33, 40 |

**미해결 15건 중 판단이 필요한 것은 셋임.** 결함 40은 화면 설계 결정이 남았고, 결함 12·13은 재현 조건이 좁아 보류로 정함(`Docs/STATUS.md` 2절). 나머지는 P3 위생 항목임.

---

## 1. 해결·정정된 결함

상세 경위는 조치 커밋에 있음.

| 번호 | 결함 | 상태 | 조치 |
| --- | --- | --- | --- |
| 1 | Vite 프록시가 `/api` 접두사를 벗기지 않음 | 정정·해결. 동반 Backend 유실의 증상이었음 | `384b569` |
| 2 | 프론트엔드가 인증 토큰을 보내지 않음 | 정정·해결. 같은 원인 | `384b569` |
| 3 | 프론트엔드가 없는 엔드포인트 5개를 호출함 | 정정·해결. 경로 재매핑, `/announcements`·`/stats` 신설 | `384b569` |
| 4 | 정책 응답 스키마가 NULL을 허용하지 않아 500 | 오탐. 실제 500은 결함 10 | — |
| 5 | `GET /chat/messages/{id}/sources`에 인증이 없음 | 심각도 정정·해결. 공개 문서 발췌만 담겨 있었음 | `c74013d` |
| 6 | `GET /admin/monitoring`이 DB 비밀번호를 반환함 | 해결 | `c74013d` |
| 7 | 캘린더 필드명 불일치로 화면이 빈 채 성공 처리됨 | 해결 | `384b569` |
| 8 | `legalBasis` 타입 불일치로 렌더 크래시 | 해결. 결함 42로 재발 후 재해결 | `384b569`, `e1abe32` |
| 10 | `policy_service.detail`이 NULL을 흘려 500 | 해결 | `d8242fc` |
| 11 | 페이지네이션 부재 | 정정·해결. 문제는 지연이 아니라 2.5 MB 응답 크기였음 | `c74013d` |
| 16~20 | Backend가 LLM V1 계약 미준수 (fallback·`userContext`·`sources`·타임아웃) | 해결 | `d8242fc` |
| 22 | 세액감면 요청 본문이 버려짐 | 정정. Backend는 DB 프로필로 판정하는 설계임 | — |
| 23 | 챗 응답에 `sources`가 없음 | 해결. 결함 42로 재발 후 재해결 | `384b569`, `e1abe32` |
| 31 | `08_link_policy_calendar.sql`이 compose initdb에 없음 | 조치 불필요. initdb 시점엔 공고가 비어 효과가 없고 `DB/run_all.*`이 수집 뒤 실행함 | 0914 결함 47 |
| 32 | compose에 frontend 서비스·nginx 설정 없음 | 해결. 이미지 반영에는 `--build` 필요 | `a835832` |
| 34 | 관리자 토큰이 같은 번호의 사용자로 통함 | 해결 | `c74013d` |
| 35 | 추천이 전체 목록과 같았음 | 해결. 판정 불가면 `eligible: null` | `c74013d` |
| 36 | 캘린더가 추천 목록으로 일정을 걸렀음 | 해결 | `c74013d` |
| 37 | 생성 주체가 설계와 반대였음 | 해결 | `c4eb000`, `e1abe32` |
| 38 | 비로그인 오류 문구가 엉뚱한 곳을 가리킴 | 해결 | `c4eb000`, `e1abe32` |
| 39 | LLM 인덱스가 기동 시 만들어지지 않음 | 해결. 콜드 스타트는 llm 헬스체크로 보완 | `c4eb000`, `a835832` |
| 41 | Backend 목업이 LLM fallback 답변을 덮어씀 | 해결 | `fd5fbc2` |
| 42 | 병합 충돌을 파일 단위로 덮어 App.jsx 통합 로직이 사라짐 | 해결 | `e1abe32` |

결함 41의 남은 문제: `Backend/core/llm_client.py`가 503·504·429·연결 실패·JSON 파싱 실패를 전부 `None`으로 붕괴시켜 재시도 없이 목업으로 내려감. 반환 계약을 바꿔야 하고 소비자가 6곳이라 별도 이슈로 둠.

---

## 2. 미해결 — 기능

### 9. 영수증 추출 응답의 필수/선택이 LLM과 반대

- 위치: `Backend/schemas/expenses.py:15-21`, `Backend/services/expense_service.py:80-87`
- 증상: 추출 행이 없는 영수증에 대해 `GET /expenses/receipts/{id}`가 404가 아니라 500임
- 원인: 서비스가 추출 행이 없으면 빈 dict로 대체한 뒤 `.get()`으로 `None`을 반환하는데 `date`·`vendor`·`amount`가 required임. LLM 쪽 동명 모델(`LLM/src/serving/schemas.py`)은 세 필드가 전부 optional이라 같은 이름의 계약이 정반대임

### 12. `_apply_extras`가 실패를 삼키면서 트랜잭션을 오염시킴 — 보류

- 위치: `Backend/core/db.py` `_apply_extras`
- 증상: `notifications` 테이블이 만들어지지 않은 채로 Postgres가 정상 준비된 것처럼 보고됨. 로그도 남지 않음
- 원인: 문장별로 예외를 잡고 `continue`하는데 `rollback()`이 없음. psycopg는 문장 하나가 실패하면 트랜잭션 전체가 abort 상태가 되므로 이후 문장이 전부 조용히 실패함
- 보류 사유: 스키마 없는 Postgres에서만 재현됨. 모든 문장이 `IF NOT EXISTS`라 기본 테이블이 있으면 실패하지 않음

### 13. Postgres 경로가 기본 테이블을 만들지 않음 — 보류

- 위치: `Backend/core/db.py` `init_db`
- 증상: 스키마가 없는 Postgres에 붙으면 서버가 뜨지 않고, 오류 메시지가 원인을 가리키지 않음
- 원인: Postgres 분기가 `_apply_extras()`만 적용하고 바로 `_seed()`로 감. `DB/01_schema.sql`은 Docker initdb로만 적용됨. SQLite 분기는 `SQLITE_DDL`로 자체 부트스트랩하므로 두 엔진이 비대칭임
- 보류 사유: 결함 12와 같음. compose는 initdb로 `01_schema.sql`을 적용함

### 14. `.env.example`대로 하면 compose가 기동하지 않음

- 위치: `.env.example`, `docker-compose.yml`
- 증상: `db` 컨테이너가 기동을 거부하고 `backend`·`llm`이 `service_healthy`에서 영구 대기함
- 원인: `POSTGRES_USER`·`POSTGRES_PASSWORD`·`POSTGRES_DB`가 빈 값이고 compose에도 기본값이 없음
- 추가 누락: `TOKEN_SECRET`, `COMPOSE_DB_HOST`, `COMPOSE_DB_PORT`, `VITE_API_BASE_URL`
- 완화: 정규 실행 경로인 `setup.sh`가 빌드 전에 빈 값을 잡아 알려 줌. compose를 직접 부를 때만 남음

### 15. `_seed()`가 공용 Postgres에 데모 데이터를 씀

- 위치: `Backend/core/db.py` `_seed`
- 증상: 팀 공용 DB에 데모 계정과 데모 TAX 일정 5건이 섞임
- 원인: 정책은 건수가 0보다 크면 건너뛰지만 사용자·관리자·TAX 캘린더는 조건이 달라 실데이터 DB에서도 삽입이 일어남

### 21. 컨테이너에서 Backend가 `.env`를 하나도 읽지 못함

- 위치: `Backend/core/config.py:19-21`, `docker-compose.yml` backend 서비스
- 증상: compose 환경에서 메일 발송이 영구 불가함
- 원인: 바인드 마운트가 `./Backend:/app`이라 상위 `.env`가 컨테이너에 없음. compose는 `backend`에 `env_file`을 주지 않음(`llm`에는 줌). compose의 `environment`가 Backend 설정의 전부임
- 영향: `SMTP_HOST`가 빈 문자열로 남아 `notify_service.py`가 항상 로컬 대기열로 단락됨. `TOKEN_TTL_SECONDS`·`SQLITE_PATH`·`SMTP_*`도 주입되지 않음
- 비고: OpenAI·Cohere 키가 Backend로 새지 않도록 `env_file`을 일부러 뺀 것(P0-1)임. 격리 의도는 유효하나 Backend가 자기 설정도 못 받음

### 40. 공고문 붙여넣기 요약을 부르는 화면이 없음

- 위치: `Frontend/src/pages/AnnouncementAnalyzer.jsx` `AnnouncementAnalyzer`(당시 `App.jsx`), `Backend/api/policies.py`
- 증상: 공고문 원문을 붙여넣어 분석하는 기능을 화면에서 쓸 수 없음
- 경위: `POST /announcements/summary` 신설과 프론트 연결로 해결했으나(`c4eb000`), 프론트 재설계가 원문 입력 화면을 정적 적합도 카드와 상담 챗으로 교체해 호출자가 사라짐
- 현재: Backend·LLM 경로와 `api.summarizeAnnouncement`는 살아 있고 호출자만 0건임. 공고지원 화면에 원문 입력과 결과 표시를 다시 설계해야 함

---

## 3. 미해결 — 정합성·위생 (P3)

### 24. `Backend/core/database.py`가 완전한 죽은 코드

- 저장소 어디서도 `core.database`를 import하지 않음. `main.py`는 `core.db`에서 직접 가져옴
- `persist()`는 호출부가 0곳임

### 25. 응답 다수에 `response_model`이 없음

- 위치: `Backend/api/chat.py` `GET /chat/messages`, `Backend/api/admin.py`
- `GET /chat/messages`와 `GET /admin/policies`가 DB 행을 snake_case 그대로 반환함. 같은 `policies` 테이블이 경로에 따라 camelCase와 snake_case 두 모양으로 나감
- camelCase 변환이 `_to_item`·`_serialize_user` 등에 수작업으로 흩어져 있음

### 26. SQLite 모드에서 `/health`의 `policies`가 항상 0

- 위치: `Backend/main.py` `health`
- 시드가 정책 5건을 넣지만 저장 모드가 postgres일 때만 셈

### 27. 다중 문장 작업에 원자성이 없음

- 위치: `Backend/core/db.py`, `Backend/core/repo.py`
- `fetchall`·`execute`·`insert`가 각각 커넥션을 새로 열고 닫음. `delete_chats`·`delete_chats_by_ids`·`delete_event`·`delete_expense`·`insert_chat`과 모든 `upsert_*`가 별도 트랜잭션으로 쪼개짐
- 중단 시 `answer_sources`·`receipt_extractions` 고아 행이 남고, 동시 요청에서 `upsert_*`가 중복 삽입될 수 있음

### 28. `repo.count(table)`이 테이블명을 SQL에 문자열로 끼워 넣음

- 위치: `Backend/core/repo.py` `count`
- 현재는 `api/admin.py`에서 하드코딩 리터럴만 전달하므로 실제 위험은 없으나 인젝션 형태의 API임

### 29. `repo.py`가 비공개 `db._iso`를 21회 직접 호출함

- 계층 경계가 새는 형태임. `_iso`를 공개하거나 변환을 `db.insert` 안으로 옮기는 편이 맞음

### 30. `ocrSource` 값이 문서화된 열거값 밖이고 조회 시 값이 달라짐

- 위치: `Backend/services/expense_service.py`, `Backend/schemas/expenses.py:12`
- 스키마는 `llm / heuristic / mock`으로 문서화했는데 LLM은 `vision`을 반환하고 그대로 나감
- `get_extraction`은 실제 출처와 무관하게 `heuristic`을 하드코딩함
- 근본 원인은 `receipt_extractions`에 출처 컬럼이 없다는 점임

### 33. 기타

| 항목 | 위치 |
| --- | --- |
| LLM 컨테이너에서 `HOST`·`PORT`·`RELOAD`가 무효. Dockerfile CMD가 포트를 하드코딩함 | `LLM/Dockerfile`, `LLM/main.py` |
| `/health`의 `ports`가 리터럴이라 compose 포트를 바꾸면 거짓 보고함 | `Backend/main.py` |
| `/internal/rag/recommendations`가 구현돼 있으나 Backend가 호출하지 않음 | `LLM/src/serving/rag_routes.py` |
| `auth.py`의 태그가 영문 `auth`라 `OPENAPI_TAGS`에 없고 Swagger에 미문서화 그룹으로 뜸 | `Backend/api/auth.py:7` |
| `LLM_TIMEOUT_SECONDS` 기본값이 compose·`config.py`는 25, 실제 `.env`는 120으로 엇갈림 | `docker-compose.yml:8`, `Backend/core/config.py:64` |

---

## 4. 확인 결과 문제가 아닌 것

오탐을 남겨 두면 다음 사람이 다시 조사하게 되므로 걸러낸 항목도 함께 기록함.

- **병합 잔재 없음.** `store` 참조·누락 심볼·시그니처 불일치·충돌 마커·중복 정의 전부 0건임
- **`Backend/data/app.db`는 최신 스키마임.** SQLite 폴백이 깨지지 않음
- **Backend가 부르는 V1 경로는 LLM에 전부 존재함.** 요청·응답 필드명과 멀티파트 파트 이름도 일치함
- **`core/db.py`의 `SQLITE_DDL` 컬럼이 `01_schema.sql` + `app_extras.sql`과 일치함**
- **`api/policies.py`의 라우트 순서가 올바름.** `/policies/recommendations`·`/policies/saved`가 `/policies/{policy_id}`보다 먼저 선언돼 있음
- **`core/config.py`에 설정 드리프트가 없음**

## 5. 관련 문서

- 진행 현황: `Docs/STATUS.md`
- 시연 결함 목록(43~): `Docs/reports/INTEGRATION_ISSUES_0914.md`
- Backend↔LLM 계약: `Docs/Design/LLM_API_SPEC_V1.md`
- API 명세: `Docs/Design/API_SPEC.md`
- 이전 보고서: `Docs/reports/LLM_INTEGRATION_AUDIT_0909.md`
