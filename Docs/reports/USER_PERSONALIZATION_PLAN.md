# 유저 개인화 DB 연결 계획 (로드맵·지출관리·사업계획서)

> 작성일 2026-09-25, develop `a87bb66`(PR #13 feature/LLM-planfix 병합 후) 기준. 대화방 이관은 `USER_PERSONALIZATION_DB.md`에서 끝났고, 이 문서는 남은 localStorage 데이터와 지출관리를 다룬다. 2026-09-25 `feature/personalize`에서 4~6절을 구현했다(7절 수동 검증은 남음).
>
> PR #13은 사업계획서 생성 타임아웃(Backend 120초, Frontend 130초), 양식 칸 8개 단위 분할 생성, PDF 칸 넘침 처리, `templateContext`의 보완 항목 범위를 고쳤다. 임시저장 필드와 localStorage 키는 바뀌지 않아 아래 계획에 영향이 없다.

## 1. localStorage 사용 현황

`Frontend/src` 전체 검색 결과, 4개 파일에서 쓴다.

| 키 | 위치 | 저장 내용 | 처리 |
|---|---|---|---|
| `changeup.accessToken` | `api.js:21-30` | 로그인 토큰 | 유지(인증 수단) |
| `changeup:user` | `App.jsx:24-31`, `utils.js:165-171` | 화면 유지용 user 캐시, 시작 시 `api.me()`로 재확인 | 유지 |
| `changeup:roadmap-done:v2:{userId}` | `utils.js:176-193`, `App.jsx:64-71` | `{"A:0": true, ...}` | `user_roadmap_progress`로 이관 |
| `changeup:bizplan-draft:{userId}` | `BusinessPlanPage.jsx:185-202, 370-392, 966-971` | 사업계획서 임시저장(16개 필드) | `bizplan_drafts`로 이관 |

예전 키(`chat-rooms:*`, `saved-gov`, `annc-history`, `annc-checks`)는 코드에 남아 있지 않다.

## 2. 기능별 현재 상태

| 기능 | 저장 위치 | 유저별 여부 | 할 일 |
|---|---|---|---|
| 창업 로드맵 체크 | localStorage | 키만 계정별, 기기 간 공유 안 됨 | DB 이관 |
| 사업계획서 초안 | localStorage | 키만 계정별, 기기 간 공유 안 됨 | DB 이관 + 스키마 보강 |
| 지출관리 | DB(`receipts`, `receipt_extractions`, `expenses`) | 이미 유저별 | 변경 없음 |

- 지출관리: `expenses.user_id`(`DB/app_extras.sql:8`)로 저장하고, `repo.list_expenses(user_id)`로 목록을 가져온다. 영수증 원본도 `receipts.image_data`, `mime_type`(`DB/app_extras.sql:20-21`)으로 DB에 둔다. `expense_service.py`의 `get_extraction`, `update_category`, `deductibility`, `analysis`, `add_item`, `delete_item`, `update_vendor`, `get_receipt_image`, `delete_expense`는 모두 소유자가 다르면 404를 돌려준다. 프론트(`ExpenseTracker.jsx`)도 `api.expenses()` 등 서버 API만 쓴다. 추가 작업은 없다.
- `user_roadmap_progress`, `bizplan_drafts` 테이블은 `DB/app_extras.sql:91-106`에 이미 있지만 Backend·Frontend 어디에서도 쓰지 않는다.

## 3. 스키마 변경

### 3.1 로드맵: 변경 없음

`user_roadmap_progress (user_id, version, task_key, done_at)`를 그대로 쓴다. 완료한 항목만 행으로 두고, 해제하면 DELETE한다.

### 3.2 사업계획서: `data` 컬럼 추가

지금 초안은 `form, plan, evalResult` 외에 `revisionSections, finalPlan, finalEvalResult, selectedAnnouncementId, selectedAnnouncementInfo, refinedDone, templateInfo, fieldAnalysis, supplementAnswers, supplementImages, supplementChoices, supplementPage, editedSectionKeys`까지 저장한다. 필드가 자주 늘어나므로 컬럼을 나누지 않고 JSONB 한 덩어리로 둔다.

```sql
-- app_extras.sql 끝에 추가 (재실행해도 안전)
ALTER TABLE bizplan_drafts ADD COLUMN IF NOT EXISTS data JSONB NOT NULL DEFAULT '{}'::jsonb;
```

- 기존 `form/plan/eval_result` 컬럼은 쓰지 않는다. 사용 이력이 없어 지워도 되지만, 컬럼 삭제는 팀 합의 뒤 진행한다.
- 초안에는 파일 두 종류가 base64로 들어간다.
  - `templateInfo.contentBase64`: 공고 양식 원본(PDF/HWPX, 4 MiB 이하, `BusinessPlanPage.jsx:680-692`)
  - `supplementImages`: 보완 이미지(파일당 2 MiB, 합계 4 MiB 이하, `BusinessPlanPage.jsx:842-851`)
- 원본 합계 최대 8 MiB, base64로 약 10.7MB에 본문 JSON이 더해진다. Django `DATA_UPLOAD_MAX_MEMORY_SIZE = 16MB`(`config/settings.py:26`) 안이라 그대로 저장하고, Backend에서 본문 크기 상한을 12 MiB로 검사한다.

## 4. Backend 변경

| 파일 | 변경 |
|---|---|
| `core/repo.py` | `list_roadmap_done(user_id, version)`, `set_roadmap_task(user_id, version, task_key, done)`(done이면 `INSERT ... ON CONFLICT DO NOTHING`, 아니면 `DELETE`), `get_bizplan_draft(user_id)`, `upsert_bizplan_draft(user_id, data)`(`ON CONFLICT (user_id) DO UPDATE SET data=?, updated_at=now()`, JSONB는 기존 방식대로 `json.dumps` 후 `?::jsonb`) |
| `api/users.py`, `services/user_service.py`, `schemas/users.py` | `GET /users/me/roadmap-progress` → `{version, done: ["A:0", ...]}`, `PUT /users/me/roadmap-progress` `{taskKey, done}`. `task_key` 형식(`^[A-Z]:\d+$`) 검사 |
| `api/bizplan.py`, `services/bizplan_service.py`, `schemas/bizplan.py` | `GET /bizplan/draft` → `{data, updatedAt}`(없으면 둘 다 `null`), `PUT /bizplan/draft` `{data}`(dict, 12 MiB 상한 검사, 초과 시 413). 기존 `/generate` 등과 같은 `user_auth` 사용 |

## 5. Frontend 변경

| 파일 | 변경 |
|---|---|
| `api.js` | `roadmapProgress`, `setRoadmapTask`, `bizplanDraft`, `saveBizplanDraft` 추가 |
| `App.jsx` | `[userId]` effect에서 `api.roadmapProgress()` 결과를 `{"A:0": true}`로 바꿔 `setRoadmapDone`. `updateRoadmapDone`은 화면을 먼저 바꾸고 달라진 키만 `api.setRoadmapTask`로 보낸다. 실패하면 이전 값으로 되돌린다 |
| `pages/BusinessPlanPage.jsx` | `loadDraft`/`saveDraft`를 `api.bizplanDraft`/`api.saveBizplanDraft`로 바꾼다(비동기). 로드 effect(370-392)는 응답의 `data`로 같은 복원 로직을 쓴다. 저장 실패는 기존 `savedNote`로 알린다 |
| `utils.js` | `saveRoadmapDone` 제거, `clearLegacyRoadmapDone` 추가. `loadRoadmapDone`과 `DRAFT_KEY` 읽기(`loadLegacyDraft`)는 아래 1회 이관에만 남긴다 |

1회 이관: 로그인 직후 서버 값이 비어 있고 localStorage에 기존 값이 있으면 서버로 올리고, 성공하면 해당 키를 지운다. 이관 기간이 끝나면 읽기 코드도 지운다.

## 6. 테스트

- 신규 `Backend/tests/test_roadmap_progress.py`: 체크/해제 upsert, 잘못된 `taskKey` 422, 다른 유저 데이터 분리
- 신규 `Backend/tests/test_bizplan_draft.py`: 저장·조회·덮어쓰기, 초안 없을 때 `null`, 양식+이미지 최대치(약 10.7MB) 저장 성공, 12 MiB 초과 413, 다른 유저 초안 분리
- 기존 테스트 전체 통과(`cd Backend && uv run python -m unittest discover tests`)

## 7. 검증 절차

1. `psql`에서 `\d bizplan_drafts`로 `data` 컬럼 확인
2. Backend unittest, `npx vite build` 통과
3. 데모 계정으로 로드맵 체크 + 사업계획서 임시저장(양식 첨부, 이미지 첨부 포함) 후 시크릿 창에서 다시 로그인해 같은 상태인지 확인
4. 다른 계정으로 로그인했을 때 앞 계정 데이터가 보이지 않는지 확인
5. 기존 localStorage 값이 있는 브라우저에서 로그인 → 서버로 올라가고 키가 지워지는지 확인

## 8. 남은 위험

- `task_key`가 `단계:인덱스` 형식이라 `constants.js`의 `ROADMAP_TASKS` 순서가 바뀌면 체크가 다른 항목에 붙는다. `version`을 올려 무효화하고, 근본 해결은 항목별 고정 id다.
- 초안에 양식 원본과 이미지가 base64로 들어가 행 하나가 최대 약 11MB가 된다. 저장 빈도가 "임시저장" 버튼뿐이라 당장은 괜찮지만, 커지면 양식·이미지를 별도 테이블로 나눈다.
- `_apply_extras`는 `app_extras.sql` 전체를 한 번에 실행해 `DO $$` 블록도 적용된다(`Backend/core/db.py:196-205`). 다만 실패해도 경고 로그만 남기고 기동하므로, 배포 뒤 7절 1단계로 컬럼 추가를 확인한다.
