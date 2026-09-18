# 진행 현황

- 갱신일: 2026-09-15
- 기준 브랜치/커밋: `develop` / `e48c609`

`Docs/TODO.md`가 전체 작업 흐름과 체크리스트라면, 이 문서는 현재 코드 기준의 실제 상태를 정리한 것이다.
해결된 이슈는 3절에 한 줄로만 남긴다. 상세 경위는 커밋에 있다.

**미해결 1건, 보류 2건이다.** 결함 번호는 `Docs/reports/INTEGRATION_ISSUES_0910.md`(1~42)와 `Docs/reports/INTEGRATION_ISSUES_0914.md`(43~)를 따른다. 0914 리포트의 시연 결함(43~55)은 이 문서가 추적하지 않으며 그 리포트에서 상태를 관리한다.

## 1. 병합 현황

| 브랜치 | 병합 커밋 | 비고 |
| --- | --- | --- |
| `feature/data-collection` | `7286a9d` (PR #9) | 세법·정책 수집 스크립트 |
| `feature/backend` | `c921867` (PR #10) | Backend API 서버 |
| `feature/LLM-connect-test` | `21c79f9` (PR #11) | LLM RAG(LangGraph) 구현 |
| `feature/data-collection` | `2bbbf3b` (PR #12) | `app_extras.sql`, HNSW 인덱스, API 키 로그 노출 수정 |
| `feature/intergration` | `8b3f0ef` (PR #13) | 서비스 간 배선, Backend 덤프 제거, 설계 문서 동기화 |
| `feature/data-collection` | `720e16f` (PR #14) | `09_add_rag_columns.sql` 삭제 및 `run_all` 호출 제거 |
| `feature/LLM-connect-test` | `763f265` (PR #17) | LLM V1 엔드포인트 4개 구현, Backend 연동 보완 |
| `feat/frontend` | `72c4b0e` (PR #19) | 창업ON 프론트엔드(React 18 + Vite) |
| `feature/backend` | `a01a503` | P1-1 DB 직접 조회 전환. `feature/integration`으로 직접 병합 |
| `feature/integration` | `abcb308` (PR #20) | 통합 이슈 일괄 해결, LLM OpenAI 연결, setup 스크립트. `develop`으로 병합 |
| `feature/deploy` | `45f9b14` | 프론트 도커화, nginx 프록시, 컨테이너 `restart` 정책. `feat/frontend`가 흡수 |
| `feat/frontend` | `9c8e075` | 프론트 재설계(레이아웃·스타일). 배포 구성까지 함께 `develop`으로 병합 |
| `feature/LLM-tax_advence` | `6bcff0c` (PR #22) | 세금 계산 함수 반영 |
| `feature/LLM_session` | `828c6b9` (PR #25) | 사용자별 대화 문맥 전달 |
| `feature/data-collection` | `8f1e58f` (PR #27) | 지역명 정규화 |
| `feature/LLM-memory` | `84adaf8` (PR #28) | 대화 저장, 로드맵 코치 프롬프트 분기 |
| `feat/frontend` | `15a8744` (PR #29) | 회의 반영 프론트 수정 |
| `feature/LLM-evaludation` | `971d367` (PR #32), `32818e7` (PR #33) | LLM 성능·속도 개선, 평가 리포트 |
| `feature/LLM-evaludation` | `4bfb859` (PR #34) | LLM 답변 품질 향상 |
| `feature/integration` | `0c9714a` (PR #35) | 계정별 채팅방·로드맵 구분 |
| `feat/frontend` | `59f12a1` (PR #36), `c48f4b6` (PR #37) | 마이페이지·상담기록·홈 개선, 응답 대기 중 다른 대화방 보기 |
| `feat/frontend` | `fbe0335` (PR #38) | 대화방 삭제, 서버 메시지 삭제 API |
| `feat/frontend` | `bc34e37` (PR #39) | `App.jsx`·`styles.css`를 기능 단위 파일로 분리, 홈 AI 대화창을 데모로 복귀 |
| `feature/LLM-inhence` | `4461a51` (PR #40) | 세금 질문 Semantic Cache(`LLM/src/rag/tax_cache.py`), DB 커넥션 풀·그래프 재사용 |
| `develop` 직접 커밋 | `17a42bc`, `e48c609` | `TaxTool.jsx` 누락 import, `tax_rag_cache` 테이블(`DB/app_extras.sql`) |

## 2. 미해결·보류 항목

| 항목 | 상태 | 내용 |
| --- | --- | --- |
| 결함 40. 공고문 붙여넣기 요약을 부르는 화면이 없음 | 미해결 | `POST /announcements/summary`와 `api.summarizeAnnouncement`는 살아 있으나 프론트 재설계(`9c8e075`)가 원문 입력 화면을 없애 호출자가 0건이다. 화면 설계 결정이 필요하다 |
| P1-3. 부트스트랩 결함 2건(결함 12·13) | 보류 | `Backend/core/db.py`의 `_apply_extras`가 `rollback()` 없이 실패를 삼키고, Postgres 경로가 기본 테이블을 만들지 않는다. 둘 다 스키마 없는 Postgres에서만 재현되고 compose는 initdb로 `01_schema.sql`을 적용하므로 고치지 않기로 했다 |
| 지출 분석(FS-14~17) | 보류 | 추가 기능(추후 개발)으로 돌렸다(`Docs/README.md` 8절). Backend `/expenses/*`, LLM `/ocr/receipt`·`/rag/deductibility`, DB 테이블은 유지하나 부르는 화면이 없고, `Frontend/src/pages/MyPage.jsx`의 `ExpenseTracker`는 미사용이다. 경비처리 질의응답은 AI 상담(`category=expense`)으로 제공한다 |

## 3. 해결된 이슈

| 이슈 | 내용 | 조치 |
| --- | --- | --- |
| P0-1. 서비스 간 통신 미배선 | compose에 포트·환경변수·`depends_on`·헬스체크가 없었음 | PR #13 `8b3f0ef` |
| P0-2. LLM 엔드포인트 미구현 | 세액감면 근거·영수증 OCR·경비 판단·공고 요약 4개 부재 | PR #17 `763f265` |
| P0-2-1. Backend가 LLM V1 계약 미준수 | fallback 잔존, 타임아웃·`userContext`·`noticeResults` 미적용, `sources` 유실 등 9건(결함 16~20) | `d8242fc` |
| P0-3. Backend 쓰기가 벡터 인덱스를 삭제 | `TRUNCATE ... CASCADE`가 `rag_documents`까지 비움. 덤프 경로 제거 | `71f24a9` |
| P0-4. 정책 상세 API가 실데이터에서 500 | `apply_method` NULL을 필수 필드로 받았음(결함 10) | `d8242fc` |
| P0-5. 프론트엔드가 Backend를 호출하지 못함 | 동반 Backend 유실. 프록시·인증·경로 정합, `/announcements`·`/stats` 신설(결함 1~3) | `384b569` |
| P0-6. 보안 2건 | 근거 문서 조회에 인증·소유자 확인 없음, `/admin/monitoring`이 DB 자격증명 노출(결함 5·6) | `c74013d` |
| P0-7. 관리자 토큰이 사용자로 통함 | `users.id`와 `admin_users.id`가 겹쳐 소유자 검사가 무력했음. 관리자 토큰으로 사용자 API 호출 시 403(결함 34) | `c74013d` |
| P0-8. 서명 없는 레거시 토큰이 통함 | 점 없는 토큰이 HMAC·만료 검사를 건너뜀 | `c247672` |
| P0-9. Backend 목업이 LLM fallback을 덮어씀 | `status`가 `error`면 LLM 답변을 버리고 목업을 반환했음(결함 41) | `fd5fbc2` |
| P0-10. 병합에서 App.jsx 통합 로직이 사라짐 | `a900489`의 파일 단위 충돌 해결이 결함 8·23·37·38·40 조치를 되돌림(결함 42) | `e1abe32` |
| P1-1. Backend가 실제 DB를 조회하지 않음 | 전역 dict의 데모 5건만 응답. `db.py`·`repo.py`로 전환 | `a01a503` |
| P1-2. 스키마-코드 컬럼 불일치 | `DB/app_extras.sql`로 누락 테이블·컬럼 보충 | `3f0d234` |
| P1-3(조회량). 응답 2.5 MB와 무의미한 추천 | 페이지네이션 추가, 판정 불가 요건은 `eligible: null`, 캘린더를 추천에서 분리(결함 11·35·36) | `c74013d` |
| P2-1. Frontend 미병합 | 창업ON 프론트엔드 병합 | PR #19 `72c4b0e` |
| P2-2(일부). Backend 이미지 빌드가 락파일 무시 | `uv sync --frozen` 적용 | `c74013d` |
| AI 상담·공고문 분석 | 생성 주체 순서, 비로그인 401 안내, LLM 인덱스 기동 워밍업(결함 37~39). 콜드 스타트 경합은 llm 헬스체크 + `service_healthy`로 보완 | `c4eb000`, `a835832` |
| 실행 절차 부재 | `setup.sh`가 0바이트였음 | `1781790` |
| 프론트 챗 타임아웃이 서버 예산보다 짧음 | `apiPost` 기본 30초가 tax 예산 120초보다 짧았음. `api.chat`이 tax 계열 135초·그 외 60초를 씀 | `e619d23` |

**교훈 두 가지.**

- P0-4·P0-5는 살아 있는 코드만 보고 원인을 단정해 틀렸다. 결함을 단정하기 전에 실데이터로 재현하거나 해당 파일의 커밋 이력을 대조한다
- 큰 병합 충돌은 파일 단위로 넘기지 않는다. `git checkout --conflict=diff3 <파일>`로 base를 함께 보고, 병합 직후 `git diff HEAD^2 HEAD -- <파일>`로 버린 것을 확인한다

**인증이 없는 라우트 6개는 의도된 공개다.** `POST /auth/signup` · `POST /auth/login` · `POST /admin/auth/login` · `GET /chat/categories/{category}/suggested-questions` · `GET /announcements` · `GET /stats`.

## 4. 운영 절차

### 로컬 실행 (`setup.sh` / `setup.bat`)

`setup.bat`은 cmd.exe용이다. 본론에 앞서 `.env`를 검사한다. 파일이 없거나 `POSTGRES_USER`·`POSTGRES_PASSWORD`·`POSTGRES_DB` 중 하나라도 비어 있으면 그 자리에서 멈춘다. 어느 키가 비었는지는 `setup.sh`만 알려 주고 `setup.bat`은 세 키를 함께 안내한다. `OPENAI_API_KEY`가 없으면 "AI 답변이 목업이 된다"고 경고만 하고 계속한다.

1. `compose build`
2. `db` 기동 후 `DB/app_extras.sql`을 `psql`로 다시 적용 — initdb는 볼륨이 비어 있을 때만 돌기 때문이다. 전 문장이 `IF NOT EXISTS`라 재실행에 안전하고 기존 행을 지우지 않는다. 기존 볼륨에 LLM 세금 캐시 테이블 `tax_rag_cache`를 추가하는 것도 이 단계다
3. `backend`·`llm` 기동
4. 헬스체크. `/health`의 `storage`가 `postgres`인지, `ragReady`가 참인지 확인해 각각 폴백·목업 상태를 경고. 응답이 없으면 해당 컨테이너 로그 30줄을 찍고 멈춘다

이후 `Frontend`에서 필요할 때만 `npm ci`를 돌리고 Vite 개발 서버를 실행한다. `--no-frontend`를 주면 4단계까지만 하고 끝난다.

**스크립트는 `.env`를 만들지 않는다.** 비밀키가 들어 있어 git으로 공유되지 않으므로 팀에서 파일로 받아 저장소 루트에 두어야 한다.

기동 대기는 `docker compose up --wait`와 `curl --retry`에 맡긴다. 그래서 **Docker Compose v2.1.1 이상**이 필요하다. `setup.bat`의 메시지는 전부 ASCII 영문이다. cmd.exe가 배치 파일을 OEM 코드페이지로 읽어 비ASCII 문자가 출력과 파싱을 함께 깨뜨리기 때문이다.

빈 `POSTGRES_*`로 `docker compose up`을 직접 부르면 무한 대기한다(결함 14). `setup.sh`가 먼저 잡아 주므로 compose를 직접 부를 때만 남는 문제다.

### 지역명 정규화 제약을 기존 DB에 적용 (PR #27 후속)

`users.region`의 `chk_users_region` 제약은 `DB/app_extras.sql`에만 정의돼 있고, 이 파일은 빈 볼륨으로 컨테이너를 처음 띄울 때만 자동 실행된다. 이미 `db_data` 볼륨이 있는 DB에는 직접 실행해야 한다. 제약 추가 구문은 `pg_constraint` 확인으로 감싸 두었으니 몇 번 다시 돌려도 안전하다.

1. 기존 값 확인. `SELECT region, COUNT(*) FROM users GROUP BY region;` 로 17개 시·도 밖의 값을 찾는다
2. 해당 값을 짧은 이름으로 고치거나 NULL로 비운다
3. `docker exec -i startup_db psql -U <user> -d <db> < DB/app_extras.sql` 실행
4. 기존 행까지 검사하려면 `ALTER TABLE users VALIDATE CONSTRAINT chk_users_region;` 을 덧붙인다. 제약은 `NOT VALID`로 추가되므로 이 단계 전에는 신규 INSERT·UPDATE만 검사된다

## 5. 관련 문서

- 통합 결함 목록(1~42): `Docs/reports/INTEGRATION_ISSUES_0910.md`
- 시연 결함 목록(43~): `Docs/reports/INTEGRATION_ISSUES_0914.md`
- 작업 체크리스트: `Docs/TODO.md`
- 데이터 구조와 스키마 적용 경로: `Docs/Design/ERD.md`
- Backend↔LLM 계약: `Docs/Design/LLM_API_SPEC_V1.md` (구 초안 `LLM_API_SPEC.md`는 기록용 보존)
- Backend 연동 인계 지침: `Docs/Design/BACKEND_LLM_INTEGRATION_HANDOFF.md`
- 시스템 구성: `Docs/Design/ARCHITECTURE.md`
- 세금 Semantic Cache 효과: `Docs/reports/05_TAX_SEMANTIC_CACHE_IMPROVEMENT.md`
- 화면 변경 기록: `Frontend/CHANGES.md`
- LLM 서비스 실행 절차: `LLM/RUN_GUIDE.md`
- 전체 로컬 실행: `setup.sh` · `setup.bat` (각 파일 상단 주석)
