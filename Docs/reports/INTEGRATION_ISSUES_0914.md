# develop 시연 결함 목록

- 작성일: 2026-09-14
- 갱신일: 2026-09-16 (`develop` / `80e4a5a`. `Docs/Design` 문서-코드 대조 중 결함 54·55를 발견해 추가함)
- 이전 갱신: 2026-09-15 (`develop` / `e48c609` 기준으로 상태·코드 위치 재대조. `ff3540f`에서 `App.jsx`가 파일 단위로 분리됨)
- 최초 조사 기준: `develop` / `0f2d1de`

## 0. 요약

`develop` 시연 중 사용자가 보고한 사용성 결함과 그 조사 중 발견한 결함을 모음. `Docs/reports/INTEGRATION_ISSUES_0910.md`(1~42)와 성격이 달라 파일을 나누고 **번호는 43부터 이어 씀.**

| 번호 | 결함 | 심각도 | 상태 |
| --- | --- | --- | --- |
| 43 | 채팅 말풍선이 마크다운을 평문으로 출력함 | P1 | 해결 `5635664` |
| 44 | 세액감면 계산이 사용자 입력 6개를 한꺼번에 요구함 | P1 | 일부 해결 `c1eae08`·`97df684` |
| 45 | AI 답변이 느림 | P1 | 일부 해결 `97df684` |
| 46 | 상담 기록이 전 카테고리를 평면 나열함 | P2 | 해결 `5635664` |
| 47 | 저장한 공고 마감일이 캘린더에 뜨지 않음 | P1 | 해결 `8c0484d` |
| 48 | 저장한 공고 목록이 페이지 이동 시 초기화됨 | P0 | 해결 `4b88fec` |
| 49 | 캘린더 일정이 늘면 로드맵 진행률도 증가 | 미확정 | 해결 `5635664` |
| 50 | 채팅방 경계가 계정별로 나뉘지 않음 | P2 | 해결 `0068383` |
| 51 | 로드맵 진행률이 로그아웃 후 다음 계정에 남음 | P2 | 해결 `0068383` |
| 52 | 대화방 삭제 API에 빈 ids가 가면 사용자 전체 기록이 삭제됨 | P1 | 해결 `01a57ee` |
| 53 | frontend가 backend 준비 전에 기동됨 | P2 | 해결 `01a57ee` |
| 54 | `GET /tax/tax-reduction/result`가 500 | P1 | 미해결 |
| 55 | 같은 응답의 `llmUsed`가 항상 false | P2 | 미해결 |

**미해결 작업 영역**

| 번호 | 프론트엔드 | 백엔드 | DB | LLM |
| --- | :-: | :-: | :-: | :-: |
| 44 | | | | ● |
| 45 | | ● | | ● |
| 54 | | ● | | |
| 55 | | ● | ● | |

**해결된 결함 요약.** 48은 저장 목록을 `App` 상태로 올리고 `POST`/`DELETE /policies/{id}/save`·`GET /policies/saved`로 서버와 동기화함. 47은 48로 첫째 원인이 풀렸고, 마이페이지 캘린더가 내 일정·세금 신고일·저장한 정책 마감일을 함께 보여주도록 필터를 고침. 테스트 `Backend/tests/test_saved_policies.py`. 어디서도 렌더되지 않는 `GovExplorer`는 죽은 코드라 손대지 않음. 43은 의존성 없는 `Markdown` 렌더러(`Frontend/src/components/Markdown.jsx:23`)를 `AiConsult` 완료·스트리밍 말풍선(`Frontend/src/components/AiConsult.jsx:542`·`:563`)에 적용함. 로드맵 코치·세무 Assistant·공고지원 AI가 같은 경로를 씀(홈 대화창은 `ff3540f`에서 연출 데모로 되돌림). 코드 펜스·링크는 미지원이나 답변 프롬프트가 기계적 제목을 금지해 영향이 적음. 46은 `ChatLog`(`Frontend/src/pages/MyPage.jsx:430`)를 카테고리별 탭으로 나눈 뒤 마이페이지 메뉴에서 제거함. 49는 로드맵 진행률을 `localStorage`에 저장하고 대시보드 그리드 행 높이를 분리함(사용자 확인). 50·51은 대화방 경계 키(`Frontend/src/utils.js:41` `ROOMS_KEY`)와 로드맵 진행률 키(`utils.js:214` `ROADMAP_KEY`)에 사용자 id를 넣음. 계정이 바뀌면 그 계정 값으로 교체하고 로그아웃하면 진행률을 비움(`Frontend/src/App.jsx:60-73`). 52는 `api.deleteMessages`(`Frontend/src/api.js:210`)가 빈 ids면 요청 없이 reject함. `qs()`가 빈 값을 빼 `DELETE /chat/messages`가 전체 삭제로 바뀌던 경로이며, 호출부 `deleteRoom`의 기존 실패 경로(브라우저 숨김+안내)로 처리됨. 53은 `docker-compose.yml`의 backend에 `/health` healthcheck(python urllib)를 추가하고 frontend `depends_on`을 `service_healthy`로 바꿈. 검증: 전체 재기동에서 db → llm → backend 순으로 기동하고 `docker events`상 backend `health_status: healthy` 직후 frontend가 시작됨. 실행 중 backend의 `DELETE /chat/messages` 파라미터는 `category`·`ids`(둘 다 선택), 토큰 없이 호출하면 401, nginx 경유 `/api/health`는 200임.

---

## 1. P1 — 응답 품질

### 44. 세액감면 계산이 사용자 입력 6개를 한꺼번에 요구함 — 일부 해결

- 증상: 세액감면을 물으면 답변 대신 확인할 정보 목록만 길게 나옴

**해결된 것 (`c1eae08`)** — 대상·자격 질문(계산 불필요) 경로

- `_is_individual_tax_judgment`를 삭제해 "내가 감면 대상이야?"도 일반 설명 경로를 탐(`c1eae08`)
- `TAX_ANSWER_PROMPT`(`LLM/src/rag/answer.py`)가 조건부 예시를 먼저 쓰고 추가 정보는 최대 2개만 요청하게 함. `_answer_context`(`graph.py:2329`)가 `missing_user_context`를 2개로 자름
- 근거가 부족해도 인용 가능한 출처가 있으면 고정 문자열 대신 LLM 답변을 생성함(`partial_evidence_answer`, `graph.py:1560`)
- 테스트 `LLM/tests/test_tax_graph.py`(`test_tax_partial_evidence_explains_known_facts_and_keeps_status` 등)

**진행된 것 (`97df684`)** — 감면액 계산 요청(`calculation_type=startup_tax_reduction`) 경로

- `tax_calculation_plan_node`(`LLM/src/rag/graph.py:925`)가 `user_context`의 `age`·`region`(→사업장 위치)·`business.industry`·`business.founded_at`(→창업연도)을 결정적으로 선채움하고 출처를 `calculation_assumptions`에 남김. 지역은 "잠정 사용" 문구를 붙임
- 사용자에게 요청하는 항목을 우선순위(감면 적용 전 세액 → 최초 창업 여부 → 창업연도 → 나이 → 사업장 위치 → 업종)로 최대 2개만 `missing_user_context`에 담음. `answer_node`의 `fallback_answer` 호출도 2개로 자르고(`graph.py:1572`), `need_more_info`면 가정 문구를 답변 앞에 붙임
- 테스트 `test_startup_calculation_prefills_profile_and_asks_only_unresolved_eligibility`(`LLM/tests/test_tax_graph.py:1371`)

**남은 것**

- `REQUIRED_USER_INPUTS`(`graph.py:203`)는 여전히 6개이고 `DEFAULT_CALCULATION_INPUTS`(`graph.py:232`)에 startup 항목이 없음. 질문에 없으면 `eligible_tax_krw`·`first_startup`은 프로필과 무관하게 항상 물음. 이 경로는 여전히 LLM을 건너뛴 고정 fallback 답변임
- `first_startup`은 자격에 영향을 주므로 기본값을 사실처럼 채우지 않는 편이 맞다는 의견이 있음(`Docs/reports/LLM_IMPROVEMENT_OPTIONS_COMPARISON_0914.md`). 기본값 도입 여부는 미결정
- 헛짚기 쉬운 곳: `POLICY_DISCOVERY_PROMPT`와 `RAG_PROMPT`(`LLM/src/rag/prompts.py`)는 챗 경로 밖임

### 45. AI 답변이 느림 — 일부 해결

- 요청 경로: `AiConsult.ask` → `api.chat` → `Backend/api/chat.py` → `Backend/core/llm_client.py` → `LLM/src/serving/rag_routes.py` → `graph.ainvoke`
- 해결된 것
  - 분류성 호출에 `reasoning_effort="low"` 적용(`0a262be`·`5bda8bf`)
  - 프론트 챗 타임아웃을 서버 예산에 맞추고 진행 상황 문구를 표시함(`e619d23`)
  - 대화 이력이 있어도 지시어가 없고 주제어가 있는 독립 질문은 문맥 복원 LLM 호출을 건너뜀(`_tax_question_needs_contextualization` 등, `graph.py:410`, `c1eae08`)
  - 요청마다 만들던 객체를 재사용함(`97df684`). `RagRuntime.require_graph`(`LLM/src/serving/rag_routes.py:176`)가 컴파일된 그래프·`ChatOpenAI`·`HybridSearch`를 캐시, `cohere.ClientV2`는 `lru_cache`(`LLM/src/rag/reranker.py:15`), DB는 `psycopg_pool` 풀(`LLM/src/core/database.py`, 1~16). 원래 원인 2번
  - 세금 질문 Semantic Cache(`LLM/src/rag/tax_cache.py`, `97df684`). 유사 질문의 검색 근거·근거 판정을 `tax_rag_cache`에서 재사용해 62턴 평가 평균 17.69초 → 12.46초(`Docs/reports/05_TAX_SEMANTIC_CACHE_IMPROVEMENT.md`). 첫 질문은 그대로 느림

**남은 원인**

1. **결과가 버려지는 호출이 있음.** `_route_for_category`(`graph.py:487`)가 `tax`·`expense`를 무조건 `tax`로 확정하는데 그 앞의 라우터 LLM 호출(`router_node`, `graph.py:751`)은 그대로 돎
2. **스트리밍이 없음.** LLM은 `chain.ainvoke` + `with_structured_output`, Backend는 응답 본문을 통째로 읽고(`llm_client.py:264`), 프론트는 `res.json()`임. 세 계층의 응답 방식을 모두 바꾸고 구조화 출력 검증과 충돌하므로 범위 밖으로 둠
3. `.env`의 `LANGSMITH_TRACING=true`가 프로세스 환경에 닿으면 모든 체인 단계가 추적을 전송함
4. **첫 검색 fan-out이 늘어남(`c1eae08`, 미측정).** 정책 질문에 정책·지원금 등 키워드가 있으면 첫 검색어가 1개에서 최대 7개(패싯 5 + 개인화 1)로 늘어남(`build_policy_initial_search_queries`, `LLM/src/rag/discovery.py:318`). 창업 감면 세금 질문은 첫 Hop 검색어 5개(`build_tax_initial_search_queries`, `tax.py:289`). 검색어마다 임베딩 API 1회와 DB 조회 1회(`LLM/src/vectorstores/postgres.py:207`)가 발생함(DB 연결은 이제 풀에서 가져옴). 근거 부족 응답도 LLM 답변 생성 1회를 추가로 씀

- 조치 방향: 버려지는 라우터 호출을 건너뜀, fan-out 구간 지연을 `TAX_LATENCY` 로그와 정책 경로 계측으로 측정한 뒤 검색어 수를 조정함

---

## 1-2. 세액감면 판정 결과 조회 (문서 대조 중 발견)

두 결함 모두 `GET /tax/tax-reduction/result` 한 경로에 있음. `Docs/Design` 문서를 코드와 대조하다 발견했고 사용자 보고는 없음. **화면이 이 경로를 부르지 않기 때문임.** 유일한 호출자였을 `Frontend/src/pages/TaxTool.jsx`가 어디서도 import·렌더되지 않는 죽은 코드라(`Docs/Design/FUNCTIONAL_SPEC.md`의 FS-13 `화면 연결` = △) 시연에는 드러나지 않음. 판정을 실행하는 `POST /tax/tax-reduction/check` 경로는 정상임.

### 54. `GET /tax/tax-reduction/result`가 500 — 미해결

- 증상: 최근 판정 결과를 조회하면 응답 검증에서 500이 남
- 원인: `repo.insert_tax_reduction`(`Backend/core/repo.py:120-124`)이 `reasons`를 `db.dumps()`로 **JSON 문자열**로 저장하는데, `tax_service.latest_tax_reduction`(`Backend/services/tax_service.py:111-120`)이 역직렬화 없이 `result["reasons"] or []`로 그대로 돌려줌. 응답 모델은 `reasons: list[str]`(`Backend/schemas/tax.py:28`)이라 문자열이 통과하지 못함
- `POST .../check`는 메모리의 `list`를 그대로 응답에 담으므로 영향이 없음
- 조치 방향: `latest_tax_reduction`에서 `json.loads`로 되돌림. `repo`의 다른 `dumps` 저장 경로(`answer_sources` 등)를 어떻게 되읽는지 함께 확인할 것

### 55. `GET /tax/tax-reduction/result`의 `llmUsed`가 항상 false — 미해결

- 증상: 판정 실행 때 `llmUsed=true`였어도 결과 조회에서는 늘 `false`임
- 원인: `tax_reduction_results`에 `llm_used` 컬럼이 없음(`DB/01_schema.sql:89-96`, `DB/app_extras.sql`도 추가하지 않음). `tax_service.py:119`의 `result.get("llmUsed")`가 항상 `None`이라 `bool()`이 `false`가 됨. `insert_tax_reduction`도 이 값을 받지 않음
- `Docs/Design/API_SPEC.md`의 `GET /tax/tax-reduction/result` 행은 `llmUsed`를 조건 없이 기재하고 있음. 결함을 고치면 문서가 그대로 맞고, 고치지 않기로 하면 API_SPEC에 단서를 달아야 함
- 조치 방향: `app_extras.sql`에 `llm_used` 컬럼을 추가하고 저장·조회 양쪽에 태움. 컬럼을 늘리지 않으려면 `ERD`·`CLASS`·`API_SPEC` 세 문서에서 이 필드의 의미를 "판정 실행 응답에만 유효"로 좁힘

## 2. 확인 결과 문제가 아닌 것

- **계정을 바꿔도 공고·채팅 기록이 같게 보인 것은 결함이 아님(2026-09-14).** DB 사용자는 `demo@demo.com`(id 1)과 비밀번호를 모르는 계정(id 2)뿐이었음. 로그인 폼 기본값(`Frontend/src/components/LoginModal.jsx:10-11`)과 카카오·네이버 버튼(`LoginModal.jsx:178-187`)이 모두 demo 계정으로 로그인하므로 사실상 같은 계정이었음. Backend는 채팅·저장 정책·캘린더를 전부 토큰의 user_id로 거름. 확인용 계정 `demo1@demo.com`/`demo1`(id 3)을 가입 API로 추가했고 채팅·저장 목록이 비어 있음을 확인함. 이 계정은 DB 볼륨에만 있고 시드에는 없음. 조사 중 결함 50·51을 발견함
- **`GovExplorer`(`Frontend/src/pages/GovExplorer.jsx`)는 죽은 코드임.** 어디서도 렌더되지 않음. 이 컴포넌트만 보면 공고 목록이 서버에서 온다고 오해하기 쉬움
- **목데이터 폴백이 조용함.** `useApi`(`Frontend/src/api.js:226`)가 401이나 타임아웃에 말없이 폴백으로 내려감. 백엔드가 없거나 로그인이 풀렸을 때 가짜 데이터가 진짜처럼 보이므로, 이런 모양의 결함 신고는 먼저 이 경로를 의심할 것
- **`POLICY_DISCOVERY_PROMPT`와 `RAG_PROMPT`는 챗 경로 밖임.** 결함 44에 적음
- **`.env`는 git에 추적되지 않음.** 다만 API 키가 평문으로 들어 있으므로 파일을 팀 밖으로 공유할 때 주의가 필요함
- **`DB/scripts/09_normalize_region.sql`은 적용할 필요가 없음.** 수집기가 적재 시 정규화하고 로컬 DB에 비정규 region이 0건임
- **`DB/scripts/10_backfill_bizinfo_region.py`는 실행되지 않은 상태임.** bizinfo 정책 중 `region IS NULL` 1541건. 외부 API 호출이 필요해 별도 작업으로 둠

## 3. 범위 밖으로 남기는 것

- `Backend/api/chat.py`의 `send_message`가 `async def`가 아니고 `Backend/core/llm_client.py`가 블로킹 `urllib`을 씀. 챗 요청 하나가 스레드풀 워커를 최대 120초 점유하고 기본 풀이 40이라 동시 세무 질문이 몰리면 서버 전체가 멈춤. 비동기 HTTP 클라이언트 전환이 필요함
- 토큰 스트리밍(결함 45)
- 서버 기준 대화방. 대화방은 여전히 브라우저 localStorage 경계라 다른 기기에서는 한 방으로 합쳐 보이고, LLM 문맥 복원(`repo.recent_chats`)도 이전 방 대화를 섞음
- 계정별 브라우저 저장의 한계(결함 50·51). 대화방 경계와 로드맵 진행률이 localStorage라 기기·브라우저 간 공유되지 않고 사이트 데이터를 지우면 사라짐. 이전 전역 키 `changeup:chat-rooms:<category>`는 이관되지 않아 기존 방 경계가 한 번 사라짐
- 대화방 삭제 배포 순서(`978c1c0`). backend는 `--reload` 없이 볼륨 마운트로 돌아 pull 후 재빌드·재시작 전에는 구 코드가 `ids`를 무시하고 `category=None`으로 전체 기록을 삭제함. 각 PC·배포 서버에서 backend 재시작을 프론트 반영보다 먼저 할 것
- SQLite 폴백의 id 재사용. `chat_messages`가 `INTEGER PRIMARY KEY`(AUTOINCREMENT 없음)라 마지막 메시지 삭제 후 같은 id가 재발급되어 localStorage 방 경계·이름·숨김 목록이 새 메시지에 잘못 적용될 수 있음. Postgres(`SERIAL`)는 해당 없음
- 비원자적 삭제. `repo.delete_chats_by_ids`가 메시지마다 커넥션·커밋을 따로 써 중간 실패 시 일부만 삭제됨. 기존 `delete_chats`도 동일함(결함 27과 같은 원인)
- 대화방 UI 잔여. 응답 대기 중 🗑 버튼이 무반응이고, 이름 변경 중인 방을 삭제하면 입력 상태가 남으며, `HIDDEN_ROOMS_KEY`(`Frontend/src/utils.js:81`)·`deleteRoom`(`AiConsult.jsx:384`) 주석이 "서버 기록은 그대로 두고"로 남아 있음

## 4. 관련 문서

- 통합 결함 목록(1~42): `Docs/reports/INTEGRATION_ISSUES_0910.md`
- 진행 현황: `Docs/STATUS.md`
- Backend↔LLM 계약: `Docs/Design/LLM_API_SPEC_V1.md`
- API 규격: `Docs/Design/API_SPEC.md`
- 데이터 구조: `Docs/Design/ERD.md`
