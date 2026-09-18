# API 명세서

`Docs/Design/FUNCTIONAL_SPEC.md`의 기능(FS-xx)을 REST API로 제공하는 문서다. 아래 엔드포인트는 `Backend/api/` 아래에 구현돼 있으며(`/health`만 `Backend/main.py`), 이 문서는 설계안이 아니라 현재 구현 기준의 계약이다.

- Base URL: `http://localhost:8000` (로컬 개발 기준)
- 인증 방식: JWT 스타일 Access Token + `Authorization: Bearer <token>` (SPA 방식, stateless). 로그인(`/auth/login`, `/admin/auth/login`) 성공 시 `accessToken` 하나만 발급(Refresh Token 없음), 프론트는 `localStorage`(`changeup.accessToken`)에 저장 후 매 요청 `Authorization: Bearer <token>` 헤더로 전달. 토큰에 `role`(`user`/`admin`) 포함, 관리자 API는 `role=admin` 추가 검증. 만료는 `TOKEN_TTL_SECONDS`(기본 7일). 로그아웃은 클라이언트에서 토큰 삭제만 수행(서버 측 무효화 없음).
  - 토큰 포맷: `tok_{base64url(payload)}.{base64url(HMAC-SHA256 서명)}` — 표준 JWT 라이브러리가 아닌 자체 포맷, payload는 `sub`(사용자ID)/`role`/`exp`. 접두사는 `Backend/core/config.py`의 `TOKEN_PREFIX`
  - 관리자 토큰과 사용자 토큰은 서로의 API에 통하지 않는다. `get_current_user`는 `role=admin`을 403으로 막고, `get_admin`은 `role=user`를 403으로 막는다 (`Docs/STATUS.md` P0-7). 정지(`suspended`)된 사용자도 403이다
  - 구현: `security.py`, `deps.py`, `auth_service.py`(Backend), `api.js`(Frontend)
  - 참고(학습용 수준 트레이드오프): 비밀번호 SHA256 해시(salt·bcrypt 아님), 서버 측 토큰 블랙리스트 없음
  - 서명·만료 검사를 건너뛰던 점(`.`) 없는 레거시 토큰 경로는 제거됐다 (`c247672`, `Docs/STATUS.md` P0-8)

## 화면 연결

이 문서는 **Backend 구현 기준의 계약**이며, 각 엔드포인트를 실제로 부르는 화면이 있는지는 별개다. 기능 단위 현황은 `Docs/Design/FUNCTIONAL_SPEC.md`의 `화면 연결` 열이 정본이고, 여기서는 그룹별로 짧게만 적는다. 아래에서 "화면 없음"이라 한 경로도 Backend·LLM 구현은 살아 있어 화면만 붙이면 동작한다.

## auth — 회원/인증

| Method | Endpoint | 설명 | 인증 | Request | Response | 관련 기능ID |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /auth/signup | 회원가입 | 불필요 | `{ email, password, name? }` (password 4자 이상, name 기본 "사용자") | `{ userId }` | FS-01 |
| POST | /auth/login | 로그인 | 불필요 | `{ email, password }` | `{ accessToken, userId, name, role }` | FS-02 |
| POST | /auth/logout | 로그아웃 | 필요 | - | `{}` | FS-02 |

## users — 사용자 프로필

| Method | Endpoint | 설명 | 인증 | Request | Response | 관련 기능ID |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /users/me | 개인정보 조회 | 필요 | - | `{ age, region, ... }` | FS-03 |
| PUT | /users/me | 개인정보 수정 | 필요 | `{ age, region, ... }` | `{ updated: true }` | FS-03 |
| GET | /users/me/business-profile | 사업자 정보 조회 | 필요 | - | `{ businessType, industry, foundedAt, ... }` | FS-04 |
| PUT | /users/me/business-profile | 사업자 정보 등록/수정 | 필요 | `{ businessType, industry, foundedAt, ... }` | `{ updated: true }` | FS-04 |

## chat — AI 상담(챗봇)

| Method | Endpoint | 설명 | 인증 | Request | Response | 관련 기능ID |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /chat/categories/{category}/suggested-questions | 카테고리별 추천 질문 목록(하드코딩) | **불필요** | - | `{ category, questions: [...] }` (알 수 없는 category는 tax 목록) | FS-05 |
| POST | /chat/messages | 챗봇 질의 전송 (category: tax / expense / saving / policy / roadmap) | 필요 | `{ category, question, roadmapStep? }` (`roadmapStep`은 `A`~`F`·`Z`, `roadmap`에서만 허용) | `{ messageId, answer, grounded, llmUsed, needsConfirmation, status, guardrailReason }` | FS-05, FS-06, FS-07 |
| GET | /chat/messages | 내 대화 기록 조회 | 필요 | `?category`(선택) | `{ messages: [...] }` | FS-05 |
| DELETE | /chat/messages | 내 대화 기록 삭제(전체·카테고리·대화방 단위) | 필요 | `?category`(선택), `?ids`(선택, 쉼표 구분 메시지 id. 지정 시 `category`는 무시하고 해당 메시지만 삭제) | `{ deleted: true, count: n }` | FS-05 |
| GET | /chat/messages/{messageId}/sources | 답변 근거 문서 조회 | 필요 | - | `{ sources: [{ title, url, excerpt }] }` | FS-08 |

## calendar — 홈 화면 캘린더

| Method | Endpoint | 설명 | 인증 | Request | Response | 관련 기능ID |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /calendar | 통합 일정 캘린더 조회(세금+지원금+내 일정, 화면은 마이페이지 캘린더) | 필요 | `?year&month&type`(tax,policy,user 선택) | `{ events: [...] }` | FS-11 |
| POST | /calendar | 내 일정 등록(`eventType=USER`) | 필요 | `{ title, dueDate, description, remind, notifyAt }` | `{ event }` | FS-11 |
| DELETE | /calendar/{eventId} | 내 일정 삭제 | 필요 | - | `{ deleted: true }` | FS-11 |

## tax — 세무 관리

| Method | Endpoint | 설명 | 인증 | Request | Response | 관련 기능ID |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /tax/business-type/diagnosis | 사업자 유형 진단 실행 | 필요 | `{ conditions }` | `{ recommendedType, comparison }` | FS-09 |
| GET | /tax/info | 세금 정보 조회 | 필요 | - | `{ taxInfo }` | FS-10 |
| PUT | /tax/info | 세금 정보 수정 | 필요 | `{ taxInfo }` | `{ updated: true }` | FS-10 |
| GET | /tax/calendar | 세금 캘린더 조회(세금 전용, 홈 화면 통합 조회는 GET /calendar 참고) | 필요 | `?year&month` | `{ events: [...] }` | FS-11 |
| GET | /tax/reminders | 세금/지원금 일정 리마인더 목록 조회 | 필요 | - | `{ reminders: [...] }` | FS-12 |
| POST | /tax/reminders | 세금/지원금 일정 리마인더 등록 | 필요 | `{ eventId, notifyAt }` | `{ reminderId }` | FS-12 |
| DELETE | /tax/reminders/{reminderId} | 리마인더 삭제 | 필요 | - | `{ deleted: true }` | FS-12 |
| POST | /tax/tax-reduction/check | 청년창업 세액감면 판정 실행 | 필요 | - (사용자·사업자 정보 기반). 나이·창업일이 없으면 400 | `{ eligible, reasons, legalBasis, llmUsed }` | FS-13 |
| GET | /tax/tax-reduction/result | 최근 판정 결과 조회 | 필요 | - | `{ eligible, reasons, legalBasis, llmUsed }` (결과 없으면 404) | FS-13 |

`tax` 그룹에서 현재 살아 있는 화면이 부르는 경로는 없다. `/tax/business-type/diagnosis`(FS-09)·`/tax/info`(FS-10)·`/tax/calendar`·`/tax/reminders`(FS-12)는 호출자가 없고, `/tax/tax-reduction/check`(FS-13)의 유일한 호출자 `Frontend/src/pages/TaxTool.jsx`는 어느 화면에서도 렌더되지 않는 죽은 코드다(파일 2행 주석). 홈·마이페이지 캘린더는 `tax` 그룹이 아니라 `GET /calendar`를 쓴다.

## expenses — 지출 분석 (추가 기능)

> **추가 기능(추후 개발)이다.** 아래 엔드포인트는 Backend에 구현돼 있으나 이를 부르는 화면이 없다(`Frontend/src/api.js`에 호출 함수 없음). `Docs/README.md` 8절 참고.

| Method | Endpoint | 설명 | 인증 | Request | Response | 관련 기능ID |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /expenses/receipts | 영수증 등록(업로드, OCR 트리거) | 필요 | `multipart/form-data (image)` | `{ receiptId, status, ocrSource }` (`llm` \| `heuristic` \| `mock`) | FS-14 |
| GET | /expenses/receipts/{receiptId} | 영수증 OCR 추출 결과 조회 | 필요 | - | `{ date, vendor, amount, items }` | FS-15 |
| GET | /expenses | 지출 내역(분류 포함) 조회 | 필요 | `?from&to&category` | `{ expenses: [...] }` | FS-16 |
| PATCH | /expenses/{expenseId} | 지출 분류 수정 | 필요 | `{ category }` (지원하지 않는 분류는 400) | `{ deductible, confidence, basis, llmUsed, sources }` | FS-16 |
| DELETE | /expenses/{expenseId} | 지출 삭제 | 필요 | - | `{ deleted: true }` | FS-16 |
| GET | /expenses/{expenseId}/deductibility | 경비처리 가능성 분석 결과 조회 | 필요 | - | `{ deductible, confidence, basis, llmUsed, sources }` | FS-17 |

`POST /expenses/receipts`의 업로드 한도는 **4 MiB**이며 초과 시 `413`이다(`Backend/api/expenses.py`의 `MAX_RECEIPT_BYTES`).
LLM 쪽도 같은 한도이고 `image/jpeg`·`image/png`·`image/webp`만 받는다(그 밖의 형식은 `415`).

## policies — 지원정책 탐색

| Method | Endpoint | 설명 | 인증 | Request | Response | 관련 기능ID |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /policies | 지원정책 검색 | 필요 | `?keyword&region&industry&page&size` (size 1~100, 기본 20) | `{ policies: [...] }` | FS-18 |
| GET | /policies/recommendations | 맞춤 정책 추천 | 필요 | `?limit` (1~50, 기본 20) | `{ policies: [...] }` | FS-19 |
| GET | /policies/{policyId} | 정책 상세(신청기간·방법 포함) 조회 | 필요 | - | `{ policy, applyPeriod, applyMethod, announcementId }` | FS-21 |
| GET | /policies/{policyId}/eligibility | 지원 자격 확인 | 필요 | - | `{ eligible, reasons }` | FS-20 |
| GET | /announcements | 모집 중 공고 목록(마감 임박순) | **불필요** | `?limit` (1~100, 기본 20) | `{ announcements: [{ id, policyId, title, dday, region, industry, target, benefit, sourceUrl }] }` | FS-18 |
| GET | /announcements/{announcementId}/summary | 공고문 AI 요약 조회(캐시 우선, 없으면 LLM 요약 후 저장) | 필요 | - | `{ target, benefit, period, documents, notes, source, llmUsed }`. 공고 없음·요약 실패 404, 원문 없음 422 | FS-22 |
| POST | /announcements/summary | 붙여넣은 공고문 AI 요약 | 필요 | `{ rawContent, source? }` (rawContent 1~20000자) | `{ target, benefit, period, documents, notes, source, llmUsed }`. 원문 공백 422, LLM 실패 503 | FS-22 |
| POST | /policies/{policyId}/save | 관심 정책 저장 | 필요 | - | `{ saved: true }` | FS-23 |
| DELETE | /policies/{policyId}/save | 관심 정책 저장 해제 | 필요 | - | `{ saved: false }` | FS-23 |
| GET | /policies/saved | 저장한 정책 목록 조회 | 필요 | - | `{ policies: [...] }` | FS-23 |

`POST /announcements/summary`는 DB에 없는 임의 공고문 원문을 LLM 서비스로 구조화한다.
저장된 공고가 아니므로 요약을 캐시하지 않는다.
응답에 `method`(신청 방법) 필드는 없다. LLM 요약 계약에 그 항목이 없어 신청 방법은 `notes`에 섞여 온다.

> **현재 이 엔드포인트를 부르는 화면이 없다(2026-09-11).** 프론트 재설계(`9c8e075`)가 공고문 원문 입력 화면을 교체하면서 `api.summarizeAnnouncement` 호출자가 0건이 됐다. Backend·LLM 경로와 `Frontend/src/api.js`의 함수는 그대로 살아 있어 화면만 붙이면 동작한다. 결함 40·42 참고.

`GET /policies`·`/policies/recommendations`·`/policies/saved`의 `eligible`은 3값이다.
`true`는 공고 요건을 실제로 충족, `false`는 미충족, **`null`은 판정 불가**다.
수집된 정책은 요건이 비어 있거나(2,178건) 자유 서술이라(356건) 자동 판정이 되지 않아
대부분 `null`이다. 이때 추천 순위는 `matchScore`(지역·업종·마감 임박도)로만 매긴다.
`GET /policies/{policyId}/eligibility`의 `eligible`도 같은 3값이며 사유는 `reasons`에 담긴다.

`policies` 그룹에서 화면이 부르는 것은 `GET /policies/{policyId}`·`/policies/recommendations`·`/policies/saved`·`POST`·`DELETE /policies/{policyId}/save`·`GET /announcements`·`GET /announcements/{announcementId}/summary`다. **`GET /policies`(FS-18)와 `GET /policies/{policyId}/eligibility`(FS-20)는 부르는 화면이 없다.** 목록 화면은 `GET /policies` 대신 `GET /announcements`를 쓴다. 죽은 코드인 `Frontend/src/pages/GovExplorer.jsx`(어디서도 렌더되지 않음)도 `GET /announcements`를 쓰므로, `GET /policies`는 살아 있는 화면에도 죽은 코드에도 호출자가 없다.

`GET /announcements`는 로그인 전 홈 화면(마감 임박 공고 패널)이 쓰므로 인증을 요구하지 않는다.
공고는 공개 정보다. `dday`는 마감까지 남은 일수(정수)이며 마감일이 없으면 `null`이다.
`region`·`industry`·`target`·`benefit`·`sourceUrl`은 원천 공고에 값이 없으면 `null`이다.

## stats — 서비스 지표

| Method | Endpoint | 설명 | 인증 | Request | Response | 관련 기능ID |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /stats | 수집 현황 지표 | **불필요** | - | `{ openAnnouncements, policies, taxDocuments, maxReductionRate }` | - |

홈 화면 상단(Hero)이 쓰는 공개 엔드포인트다. 설계 초안에는 없었고 프론트엔드 연동(P0-5) 과정에서 추가했다.

- `openAnnouncements`·`policies`·`taxDocuments`는 DB 집계다
- `maxReductionRate`는 **DB 집계가 아니라 법령 기반 고정 상수**다. 조세특례제한법 제6조
  창업중소기업 등에 대한 세액감면의 최고 감면율 100(%)이며 `Backend/core/config.py`의
  `MAX_REDUCTION_RATE`에 있다. 감면율은 업종·지역·연차에 따라 달라지므로 이 값은
  "제도상 최대치" 안내용이고 개별 판정값이 아니다. 개별 판정은 `/tax/tax-reduction/check`를 쓴다

## system — 서비스 상태

설계 초안에는 없던 그룹이다. `Backend/main.py`가 직접 정의한다.

| Method | Endpoint | 설명 | 인증 | Request | Response | 관련 기능ID |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /health | 연결 상태 조회 | **불필요** | - | 아래 참고 | FS-28 |
| GET | /docs | Swagger UI | **불필요** | - | HTML | - |

`GET /health` 응답 필드는 `status`, `storage`(`postgres` \| `sqlite`), `dbPath`, `postgres`, `pgvector`, `ragChunks`, `policies`, `llm`, `ragReady`, `ports`, `llmUrl`이다.
`setup.sh`가 기동 확인에 `storage`와 `ragReady`를 쓴다.

## notifications — 알림

설계 초안에는 없던 그룹이다. 구현(`Backend/api/notifications.py`)을 정식 수용해 기록한다. **네 엔드포인트 모두 부르는 화면이 없다.** 마이페이지의 "알림 설정"(`Frontend/src/pages/MyPage.jsx:628-638`)은 서버를 부르지 않는 로컬 토글이다. 다만 `POST /calendar`가 `remind` 기본값으로 리마인더를 만들고, `GET /notifications`·리마인더 등록 시점에 밀린 리마인더가 발송 처리되므로 데이터 경로 자체는 돈다.

| Method | Endpoint | 설명 | 인증 | Request | Response | 관련 기능ID |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /notifications | 알림·메일함 조회 | 필요 | - | `{ notifications: [...], unread }` | FS-12 |
| POST | /notifications/{notificationId}/read | 알림 하나 읽음 처리 | 필요 | - | `{ read: true }` | FS-12 |
| POST | /notifications/read-all | 모든 알림 읽음 처리 | 필요 | - | `{ read: true }` | FS-12 |
| POST | /notifications/push | 브라우저·메일 알림 즉시 발송 | 필요 | `{ eventId }` (일정 없음 404) | `{ notificationId, emailStatus }` | FS-12 |

## admin — 관리자

**관리자 화면은 없다.** 아래 엔드포인트를 부르는 프론트엔드 코드가 `Frontend/src`에 없으며, 관리자 기능은 `GET /docs`(Swagger UI)나 직접 호출로만 쓸 수 있다.

| Method | Endpoint | 설명 | 인증 | Request | Response | 관련 기능ID |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /admin/auth/login | 관리자 로그인 | 불필요 | `{ email, password }` | `{ accessToken, userId, name, role }` | FS-24 |
| GET | /admin/users | 사용자 목록 조회 | 필요 (관리자 role) | `?page` | `{ users: [...] }` | FS-25 |
| GET | /admin/users/{userId} | 사용자 상세 조회 | 필요 (관리자 role) | - | `{ user, usage }` | FS-25 |
| PATCH | /admin/users/{userId} | 회원 상태 변경(정지·해제) | 필요 (관리자 role) | `{ status }` (`active` \| `suspended`, 그 외 400) | `{ user }` | FS-25 |
| GET | /admin/tax-documents | 세법 자료 목록 조회 | 필요 (관리자 role) | - | `{ documents: [...] }` | FS-26 |
| POST | /admin/tax-documents | 세법 자료 등록 | 필요 (관리자 role) | `{ title, content, source, lawName? }` | `{ documentId }` | FS-26 |
| GET | /admin/policies | 정책 데이터 목록 조회 | 필요 (관리자 role) | `?page&size` (size 1~100, 기본 20) | `{ policies: [...] }` | FS-26 |
| POST | /admin/policies | 정책 데이터 등록 | 필요 (관리자 role) | `{ title, content, applyStartDate?, applyEndDate?, ... }` | `{ policyId, announcementId }` (공고 1건 함께 생성, 마감일이 있으면 POLICY 일정도 생성) | FS-26 |
| GET | /admin/announcements | 공고문 데이터 목록 조회 | 필요 (관리자 role) | `?page&size` (size 1~100, 기본 20) | `{ announcements: [...] }` | FS-26 |
| POST | /admin/announcements | 공고문 데이터 등록 | 필요 (관리자 role) | `{ title, content, ... }` | `{ announcementId }` | FS-26 |
| POST | /admin/rag-documents/reindex | RAG 문서 재색인 | 필요 (관리자 role) | 본문 무시(항상 전체 재색인) | `{ status, llm }` (LLM 호출 실패 502) | FS-27 |
| GET | /admin/monitoring | 시스템 모니터링 대시보드 데이터 조회 | 필요 (관리자 role) | - | `{ metrics }` (회원·정책·공고·세법·대화·지출·리마인더 건수, `ragReady`, `llm`, `postgres`) | FS-28 |

## 부록 — Backend에 없는 프론트엔드 호출 함수

`Frontend/src/api.js`의 아래 세 함수는 **Backend에 존재하지 않는 경로**를 가리킨다. 현재 호출자도 없어 동작에는 영향이 없으나, 그대로 두면 구현된 엔드포인트로 오인하기 쉽다.

| 함수 | 가리키는 경로 | 상태 |
| --- | --- | --- |
| `api.calendarUpcoming` (`api.js:196`) | `GET /calendar/upcoming` | Backend 미구현. 호출자 없음 |
| `api.taxSchedule` (`api.js:197`) | `GET /tax/schedule` | Backend 미구현. 호출자 없음 |
| `api.taxDocuments` (`api.js:198`) | `GET /tax/documents` | Backend 미구현. 호출자 없음 |

`api.summarizeAnnouncement`(`api.js:220`)는 경로(`POST /announcements/summary`)가 Backend에 있으나 호출자가 없는 경우로, 위 세 개와 성격이 다르다(`policies` 절 참고).
