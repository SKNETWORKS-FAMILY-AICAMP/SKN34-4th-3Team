# Backend

청년·1인 창업 지원 플랫폼의 REST API 서버입니다.  
프론트(화면)와 LLM(8001) 사이에서 **회원·정책·세무·지출·관리자 API**를 담당합니다.

설계 명세: `Docs/Design/API_SPEC.md`  
기능 명세: `Docs/Design/FUNCTIONAL_SPEC.md` (FS-01~28)

---

## 포트

| 서비스 | 포트 | 주소 |
|--------|------|------|
| **Backend (이 폴더)** | **8000** | `http://127.0.0.1:8000` |
| LLM | 8001 | `http://127.0.0.1:8001` (선택) |
| Frontend | 5173 | `http://127.0.0.1:5173` → `/api`를 8000으로 프록시 |
| Postgres | 5432 | 선택. 없으면 SQLite |

- API 시험 화면: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) (서버를 켠 뒤에만 열림)
- 연결 상태: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 실행

**`TOKEN_SECRET` 환경변수가 없으면 앱이 import 단계에서 `RuntimeError`로 멈춘다.** 루트 `.env`를 받거나 먼저 설정한다.

```bash
cd Backend
uv sync
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

Docker Compose에서는 `Backend/Dockerfile`이 같은 명령(`uv run uvicorn ... --host 0.0.0.0`)으로 뜬다.

켜는 순서: (선택) DB → (선택) LLM 8001 → **Backend 8000** → Frontend 5173

---

## REST API 방식

- **스타일:** REST + JSON (FastAPI)
- **인증:** JWT 스타일 Access Token + `Authorization: Bearer <token>` (stateless)
- **Refresh Token / 세션 쿠키 / OAuth / 소셜 로그인:** 사용하지 않음
- **토큰 형식:** `tok_{payload}.{signature}` (HMAC-SHA256, 표준 JWT 라이브러리 아님)
- payload: `sub`(사용자 ID), `role`(`user` \| `admin`), `exp`
- 만료: `TOKEN_TTL_SECONDS` (기본 7일)
- 로그아웃: 서버에서 토큰을 지우지 않음. 클라이언트가 토큰을 삭제하면 됨

### 인증 헤더

로그인 성공 시 `accessToken`을 받습니다. 보호 API는 매번:

```http
Authorization: Bearer <accessToken>
Content-Type: application/json
```

영수증 업로드만 `multipart/form-data` (프론트는 `FormData` 사용, Content-Type을 직접 넣지 말 것).

토큰 없으면 **401**. 일반 유저가 관리자 API를 부르거나, 관리자 토큰으로 사용자 API를 부르거나, 정지된 계정이면 **403**.

### 데모 계정 (로컬 전용, 실서비스 계정 아님)

| 역할 | 이메일 | 비밀번호 |
|------|--------|----------|
| 유저 | demo@demo.com | demo123 |
| 관리자 | admin@demo.com | admin123 |

---

## 환경변수

`.env`는 **커밋하지 말 것.** `TOKEN_SECRET` 외에는 없으면 아래 기본값으로 동작합니다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATABASE_URL` | `postgresql://admin:admin1234@127.0.0.1:5432/startup_platform` | Postgres. 연결 실패 시 SQLite |
| `SQLITE_PATH` | `Backend/data/app.db` | 폴백 DB 파일 |
| `LLM_API_URL` | `http://127.0.0.1:8001` | LLM 내부 API |
| `LLM_TIMEOUT_SECONDS` | `25` | 개별 제한이 없는 LLM 호출의 기본 제한 시간 |
| `LLM_TIMEOUT_READY` / `_CHAT_POLICY` / `_CHAT_TAX` | `3` / `45` / `120` | `/rag/ready`, `/rag/chat`(policy·roadmap / tax·expense·saving) |
| `LLM_TIMEOUT_LEGAL_BASIS` / `_DEDUCTIBILITY` / `_SUMMARIZE` / `_OCR` / `_REINDEX` | `30` / `30` / `45` / `60` / `180` | 나머지 LLM 엔드포인트별 제한(초) |
| `TOKEN_SECRET` | **없음 (필수)** | 토큰 서명 키. 미설정 시 기동 실패 |
| `TOKEN_TTL_SECONDS` | `604800` (7일) | 토큰 만료 |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | 비어 있음 | 실메일 발송용. `SMTP_HOST`가 없으면 알림함에만 쌓임 |
| `SMTP_PORT` / `SMTP_FROM` | `587` / `noreply@skn34.local` | |

---

## 폴백 (안 붙어 있어도 Backend는 동작)

| 상황 | 동작 |
|------|------|
| Postgres 없음 | 1.5초 간격 8회 재시도 후 `Backend/data/app.db` (SQLite)에 저장 |
| Postgres 연결됨 | 기동 시 `DB/app_extras.sql`을 파일이 있으면 best-effort로 적용(실패 문장은 무시)하고 데모 데이터 시드 |
| LLM 꺼짐 / OpenAI 키 없음 | 챗봇은 **목업 문구**, 세액감면 근거는 고정 문구. 공고 요약은 캐시가 없으면 404, 붙여넣기 요약은 503. RAG 재색인은 **502** |
| SMTP 없음 | 메일 실발송 없이 알림함 API만 동작 |

`GET /health`의 `postgres`, `llm`, `ragReady`로 실제 연결 여부를 구분하면 됩니다.  
폴백이어도 **API가 없는 것이 아닙니다.**

---

## 구현 기능 (FS-01~28)

| FS | 기능 | API |
|----|------|-----|
| 01 | 회원가입 | `POST /auth/signup` |
| 02 | 로그인/로그아웃 | `POST /auth/login`, `POST /auth/logout` |
| 03 | 개인정보 | `GET/PUT /users/me` |
| 04 | 사업자 정보 | `GET/PUT /users/me/business-profile` |
| 05~07 | AI 챗봇 (세금/경비/절세/정책) | `POST /chat/messages` |
| 08 | 답변 근거 | `GET /chat/messages/{id}/sources` |
| 09 | 사업자 유형 진단 | `POST /tax/business-type/diagnosis` |
| 10 | 세금 정보 | `GET/PUT /tax/info` |
| 11 | 통합 캘린더 / 세금 캘린더 | `GET /calendar`, `GET /tax/calendar` |
| 12 | 리마인더 | `GET/POST /tax/reminders`, `DELETE /tax/reminders/{id}` |
| 13 | 세액감면 판정 (Rule은 Backend, 설명은 LLM) | `POST /tax/tax-reduction/check`, `GET /tax/tax-reduction/result` |
| 14 | 영수증 등록 | `POST /expenses/receipts` |
| 15 | OCR 결과 조회 | `GET /expenses/receipts/{id}` |
| 16 | 지출 목록 | `GET /expenses?from&to&category` |
| 17 | 경비 가능성 | `GET /expenses/{id}/deductibility` |
| 18 | 정책 검색 | `GET /policies` |
| 19 | 정책 추천 | `GET /policies/recommendations` |
| 20 | 자격 확인 | `GET /policies/{id}/eligibility` |
| 21 | 정책 상세(기간·방법) | `GET /policies/{id}` |
| 22 | 공고 목록·요약 | `GET /announcements`, `GET /announcements/{id}/summary`, `POST /announcements/summary` |
| 23 | 관심 정책 | `POST /policies/{id}/save`, `DELETE /policies/{id}/save`, `GET /policies/saved` |
| 24 | 관리자 로그인 | `POST /admin/auth/login` |
| 25 | 사용자 관리 | `GET /admin/users`, `GET /admin/users/{id}` |
| 26 | 세법·정책·공고 등록 | `GET/POST /admin/tax-documents`, `/admin/policies`, `/admin/announcements` |
| 27 | RAG 재색인 | `POST /admin/rag-documents/reindex` |
| 28 | 모니터링 | `GET /admin/monitoring` |

명세에 없는 **추가 API:** 추천 질문, 대화 기록 조회/삭제, 개인 캘린더 등록/삭제, 지출 분류 수정/삭제, 회원 정지(`PATCH /admin/users/{id}`), 알림함 `/notifications`, 홈 통계 `/stats`.

---

## API 목록 (통합용)

### 인증

| Method | Path | 인증 | 비고 |
|--------|------|------|------|
| POST | `/auth/signup` | 불필요 | body: `{ email, password, name? }` → `{ userId }` |
| POST | `/auth/login` | 불필요 | → `{ accessToken, userId, name, role }` |
| POST | `/auth/logout` | Bearer | `{}` |

### 사용자

| Method | Path | 인증 |
|--------|------|------|
| GET, PUT | `/users/me` | Bearer |
| GET, PUT | `/users/me/business-profile` | Bearer |

### 상담

| Method | Path | 인증 | 비고 |
|--------|------|------|------|
| GET | `/chat/categories/{category}/suggested-questions` | 불필요 | `{ category, questions }` |
| POST | `/chat/messages` | Bearer | `{ category, question, roadmapStep? }` — `tax` \| `expense` \| `saving` \| `policy` \| `roadmap` |
| GET | `/chat/messages?category` | Bearer | 내 대화 기록 |
| DELETE | `/chat/messages?category` \| `?ids` | Bearer | `ids`(쉼표 구분 메시지 id)를 주면 그 메시지만(대화방 하나), 없으면 카테고리 또는 전체 삭제 |
| GET | `/chat/messages/{messageId}/sources` | Bearer | |

### 캘린더·세무

| Method | Path | 인증 |
|--------|------|------|
| GET | `/calendar?year&month&type` | Bearer |
| POST | `/calendar` | Bearer |
| DELETE | `/calendar/{eventId}` | Bearer |
| GET | `/tax/calendar?year&month` | Bearer |
| GET, PUT | `/tax/info` | Bearer |
| POST | `/tax/business-type/diagnosis` | Bearer |
| GET, POST | `/tax/reminders` | Bearer |
| DELETE | `/tax/reminders/{reminderId}` | Bearer |
| POST | `/tax/tax-reduction/check` | Bearer |
| GET | `/tax/tax-reduction/result` | Bearer |

### 지출

| Method | Path | 인증 | 비고 |
|--------|------|------|------|
| POST | `/expenses/receipts` | Bearer | `multipart` 필드명 `image` |
| GET | `/expenses/receipts/{receiptId}` | Bearer | |
| GET | `/expenses?from&to&category` | Bearer | |
| PATCH | `/expenses/{expenseId}` | Bearer | 분류 수정 |
| DELETE | `/expenses/{expenseId}` | Bearer | 지출·영수증 삭제 |
| GET | `/expenses/{expenseId}/deductibility` | Bearer | |

### 정책

| Method | Path | 인증 |
|--------|------|------|
| GET | `/policies?keyword&region&industry&page&size` | Bearer |
| GET | `/policies/recommendations` | Bearer |
| GET | `/policies/saved` | Bearer |
| GET | `/policies/{policyId}` | Bearer |
| GET | `/policies/{policyId}/eligibility` | Bearer |
| POST | `/policies/{policyId}/save` | Bearer |
| DELETE | `/policies/{policyId}/save` | Bearer |
| GET | `/announcements?limit` | 불필요 |
| GET | `/announcements/{announcementId}/summary` | Bearer |
| POST | `/announcements/summary` | Bearer |

### 관리자 (`role=admin`)

| Method | Path | 인증 | 비고 |
|--------|------|------|------|
| POST | `/admin/auth/login` | 불필요 | |
| GET | `/admin/users`, `/admin/users/{userId}` | 관리자 | |
| PATCH | `/admin/users/{userId}` | 관리자 | 상태 변경(정지 등) |
| GET, POST | `/admin/tax-documents` | 관리자 | |
| GET, POST | `/admin/policies` | 관리자 | |
| GET, POST | `/admin/announcements` | 관리자 | |
| POST | `/admin/rag-documents/reindex` | 관리자 | 본문은 무시하고 전체 재색인. `{ status, llm }`, 실패 시 502 |
| GET | `/admin/monitoring` | 관리자 | |

### 알림

| Method | Path | 인증 |
|--------|------|------|
| GET | `/notifications` | Bearer |
| POST | `/notifications/{notificationId}/read` | Bearer |
| POST | `/notifications/read-all` | Bearer |
| POST | `/notifications/push` | Bearer |

### 상태

| Method | Path | 인증 | 비고 |
|--------|------|------|------|
| GET | `/health` | 불필요 | `storage`, `postgres`, `pgvector`, `ragChunks`, `policies`, `llm`, `ragReady` 등 |
| GET | `/stats` | 불필요 | 홈 화면 지표 |
| GET | `/docs` | 불필요 | Swagger UI |

---

## 폴더 구조

```
Backend/
  main.py          # FastAPI 앱, CORS, 라우터 등록
  api/             # REST 라우트
  services/        # 비즈니스 로직 (세액감면·정책 자격 Rule은 여기)
  schemas/         # 요청/응답
  core/            # 설정, 토큰, SQLite/Postgres(db.py), raw SQL 데이터 접근(repo.py), LLM 클라이언트
  data/            # SQLite 폴백 파일 (gitignore 대상일 수 있음)
  tests/           # 표준 unittest 5개 파일
  pyproject.toml   # Python >= 3.13, uv로 관리 (uv.lock)
  Dockerfile       # uv sync --frozen 후 uvicorn 실행
```

테스트: `cd Backend && uv run python -m unittest discover tests` (`TOKEN_SECRET` 필요)

LLM 구현 코드는 이 폴더에 없습니다. `core/llm_client.py`가 `LLM_API_URL`로 HTTP 호출만 합니다.

---

## 프론트 연동 시 주의

1. 로그인 후 `accessToken` + `userRole` 저장
2. 보호 API마다 `Authorization: Bearer ...`
3. `role === "admin"` 이면 `/admin` 화면
4. 401 → 로그인으로
5. OpenAI 키·`.env` 실값은 GitHub에 올리지 말 것
