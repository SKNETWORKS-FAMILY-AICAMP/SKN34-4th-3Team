# 유저 개인화 데이터 DB 이관 수정안

> 상태: **대화방 적용, 로드맵·사업계획서는 `USER_PERSONALIZATION_PLAN.md`로 적용(2026-09-25)**. 사업계획서 초안은 이 문서의 `form/plan/evalResult` 대신 `bizplan_drafts.data` JSONB 하나로 저장하도록 바뀌었다(4절 API 형태도 그 문서를 따른다). 스키마는 `DB/app_extras.sql`에 모두 반영했고, 코드는 대화방(Backend 3·4절 chat 부분, Frontend `AiConsult.jsx`)만 전환했다. develop `1f6405e` 기준으로 조사했다.

## 1. 배경

대화방 구분·이름·숨김, 창업 로드맵 체크, 사업계획서 초안이 브라우저 localStorage에만 저장된다. 그래서 다음 문제가 있다.

- 기기·브라우저 간 공유가 안 되고, 사이트 데이터를 지우면 사라진다(`INTEGRATION_ISSUES_0914.md` 결함 50·51).
- 대화방 경계가 클라이언트에만 있어서 서버는 방을 모른다. `repo.recent_chats`가 `(user_id, category)` 기준으로 최근 대화를 모으기 때문에, LLM 문맥에 이전 방 대화가 섞인다.

목표는 이 데이터를 유저별로 서버(DB)에 저장하는 것이다.

## 2. localStorage 사용 현황

`Frontend/src` 전체에서 `localStorage`를 검색한 결과다.

| 키 | 위치 | 저장 내용 | 처리 |
|---|---|---|---|
| `changeup:chat-rooms:{uid}:{cat}` | `utils.js:41`, `components/AiConsult.jsx` | 방 경계(메시지 id 배열) | `chat_rooms` + `chat_messages.room_id` |
| `changeup:chat-room-names:{uid}:{cat}` | `utils.js:62` | 첫 메시지 id → 방 이름 | `chat_rooms.title` |
| `changeup:chat-room-hidden:{uid}:{cat}` | `utils.js:83` | 서버 삭제 실패 시 숨긴 방 | 필요 없어짐(방 단위 DELETE) |
| `changeup:roadmap-done:v2:{uid}` | `utils.js:236`, `App.jsx:64,71` | `{"A:0": true, ...}` | `user_roadmap_progress` |
| `changeup:bizplan-draft:{uid}` | `pages/BusinessPlanPage.jsx:53-69, 326` | `{form, plan, evalResult}` | `bizplan_drafts` |
| `changeup.accessToken` | `api.js:16` | JWT | 유지(인증 수단) |
| `changeup:user` | `constants.js:550`, `App.jsx:26` | 화면 유지용 user 캐시(`api.me()`로 재검증) | 유지 |

`IdeaAssistant`(사업계획서 오른쪽 채팅)는 저장하지 않는 설계라 대상이 아니다.

## 3. 스키마 변경안

`DB/app_extras.sql` 끝에 추가했다. 모든 구문은 재실행해도 안전하다. 파일에는 `DO $$` 블록(`chk_users_region`, `room_id SET NOT NULL`)이 있어 `Backend/core/db.py`의 `_apply_extras`(`;` 단위 분할)로는 적용되지 않는다. `docker compose up`마다 `db-migrate` 서비스가 `psql`로 적용한다(`Docs/Design/ERD.md` "스키마 적용 경로").

```sql
-- 대화방
CREATE TABLE IF NOT EXISTS chat_rooms (
    id         SERIAL PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category   VARCHAR(50) NOT NULL,       -- tax | policy | roadmap
    title      VARCHAR(255),                -- NULL이면 첫 질문을 제목으로 표시
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()      -- 마지막 메시지 시각(목록 정렬)
);
CREATE INDEX IF NOT EXISTS idx_chat_rooms_user_cat ON chat_rooms (user_id, category, updated_at DESC);

ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS room_id INT REFERENCES chat_rooms(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages (room_id, id);

-- 기존 메시지 백필: (user_id, category)당 "이전 대화" 방 1개.
-- room_id IS NULL 행만 대상이라 재실행해도 방이 중복 생성되지 않는다.
INSERT INTO chat_rooms (user_id, category, title, created_at, updated_at)
SELECT user_id, category, '이전 대화', MIN(created_at), MAX(created_at)
FROM chat_messages
WHERE room_id IS NULL AND user_id IS NOT NULL AND category IS NOT NULL
GROUP BY user_id, category;

UPDATE chat_messages m SET room_id = r.id
FROM chat_rooms r
WHERE m.room_id IS NULL AND r.user_id = m.user_id AND r.category = m.category
  AND r.title = '이전 대화';

-- 창업 로드맵 체크: 완료한 항목만 행으로 둔다(해제하면 DELETE)
CREATE TABLE IF NOT EXISTS user_roadmap_progress (
    user_id  INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version  SMALLINT NOT NULL DEFAULT 2,   -- 프론트 ROADMAP_KEY의 v2와 같은 의미
    task_key VARCHAR(20) NOT NULL,          -- "A:0" (단계:항목 인덱스), 현재 키 형식 그대로
    done_at  TIMESTAMP DEFAULT now(),
    PRIMARY KEY (user_id, version, task_key)
);

-- 사업계획서 임시저장: 유저당 1건(현재 동작과 같음)
CREATE TABLE IF NOT EXISTS bizplan_drafts (
    user_id     INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    form        JSONB NOT NULL DEFAULT '{}'::jsonb,
    plan        JSONB,                       -- 공고 양식에 따라 sections 개수·키가 달라 JSONB
    eval_result JSONB,
    updated_at  TIMESTAMP DEFAULT now()
);
```

설계 결정:

- 방 경계를 "메시지 id 목록" 대신 `room_id` FK로 정규화한다. 기기 간 공유가 되고, LLM 문맥을 방 단위로 자를 수 있다.
- `chat_messages.category`는 남긴다. 관리자 통계(`api/admin.py`)와 기존 `/chat/messages` 쿼리가 쓴다.
- Backend가 메시지를 저장할 때 항상 `room_id`를 넣으므로 백필은 기존 데이터에만 한 번 적용된다. 백필 뒤 NULL이 없으면 `room_id`를 `SET NOT NULL`로 고정한다(`DO $$` 블록으로 확인 후 적용).
- 방 삭제는 `chat_rooms.deleted_at`만 채운다(soft delete). 방·메시지·근거 행이 남아 관리자 통계(`api/admin.py`)가 줄지 않는다. 사용자 조회(`list_chats`, `list_rooms`, `get_room`)는 삭제한 방을 뺀다. `DELETE /chat/messages`도 같은 방식으로 방을 삭제 표시한다.
- `room_id ON DELETE CASCADE`는 회원 삭제로 방 행이 실제로 지워질 때만 동작한다.
- ERD는 `Docs/Design/ERD.md`의 "제안: 유저 개인화 저장 이관" 절에 있다.

## 4. Backend 수정안

| 파일 | 변경 |
|---|---|
| `core/repo.py` | 방: `list_rooms(user_id, category)`(첫 질문을 함께 반환), `create_room`, `get_room(room_id, user_id)`(소유 확인), `rename_room`, `delete_room`, `touch_room`(updated_at 갱신). `insert_chat`에 `room_id` 인자 추가, `list_chats`·`recent_chats`에 `room_id=None` 추가(있으면 `WHERE room_id = ?`). 로드맵: `list_roadmap_done(user_id, version)`, `set_roadmap_task(user_id, version, task_key, done)`(done이면 `INSERT ... ON CONFLICT DO NOTHING`, 아니면 `DELETE`). 초안: `get_bizplan_draft`, `upsert_bizplan_draft`(`ON CONFLICT (user_id) DO UPDATE`, JSONB는 `json.dumps` 후 `?::jsonb`) |
| `services/chat_service.py` | `send_message(..., room_id=None)`: room_id가 없으면 첫 메시지를 저장할 때 방을 만든다(빈 방이 DB에 남지 않음). 있으면 `get_room`으로 소유자·category를 확인하고 다르면 404. `_conversation_history(user_id, category, room_id)`는 같은 방 대화만 문맥으로 쓴다. 응답에 `roomId` 포함 |
| `schemas/chat.py` | `ChatMessageRequest.roomId: int \| None`, `ChatMessageResponse.roomId`, 방 목록·이름 변경 스키마 |
| `api/chat.py` | `GET /chat/rooms?category=`, `PATCH /chat/rooms/{id}` `{title}`, `DELETE /chat/rooms/{id}`, `GET /chat/rooms/{id}/messages`. 기존 `GET/DELETE /chat/messages`는 전체 삭제·호환용으로 유지 |
| `api/users.py`, `services/user_service.py`, `schemas/users.py` | `GET /users/me/roadmap-progress` → `{version, done: ["A:0", ...]}`, `PUT /users/me/roadmap-progress` `{taskKey, done}` |
| `api/bizplan.py`, `services/bizplan_service.py`, `schemas/bizplan.py` | `GET /bizplan/draft` → `{form, plan, evalResult, updatedAt}` 또는 `null`, `PUT /bizplan/draft` `{form, plan, evalResult}` |

## 5. Frontend 수정안

| 파일 | 변경 |
|---|---|
| `api.js` | `chatRooms`, `chatRoomMessages`, `renameChatRoom`, `deleteChatRoom`, `roadmapProgress`, `setRoadmapTask`, `bizplanDraft`, `saveBizplanDraft` 추가. `chat` body에 `roomId` 전달 |
| `components/AiConsult.jsx` | `bounds`/`roomNames`/`hiddenIds` 상태와 경계로 방을 나누는 계산(`rooms` useMemo, 기록 로드 시 `tidy`) 제거. 방 목록은 `api.chatRooms(category)`, 방을 고르면 `api.chatRoomMessages(id)`. `startNew`는 현재 `roomId`만 `null`로 바꾸고, 첫 질문 응답의 `roomId`를 목록에 추가. `submitRename` → `api.renameChatRoom`, `deleteRoom` → `api.deleteChatRoom`(실패하면 숨기지 않고 오류만 표시). `clearHistory`는 기존 `api.clearChat` 유지 |
| `App.jsx` | `[userId]` effect에서 `api.roadmapProgress()` 결과를 `{"A:0": true}` 형태로 바꿔 `setRoadmapDone`. `updateRoadmapDone`은 화면을 먼저 바꾸고 바뀐 키만 `api.setRoadmapTask`로 보낸다. 실패하면 되돌린다 |
| `pages/BusinessPlanPage.jsx` | `loadDraft`/`saveDraft`를 `api.bizplanDraft`/`api.saveBizplanDraft`로 교체. 저장 실패는 `savedNote`로 알린다 |
| `utils.js` | `saveRooms`·`saveRoomNames`·`saveHiddenRooms`·`saveRoadmapDone` 제거. load 함수는 아래 1회 이관에만 쓰고, 이관 기간이 끝나면 지운다 |

1회 이관: 로그인 직후 서버 값이 비어 있고 localStorage에 기존 값이 있으면, 로드맵 체크와 사업계획서 초안을 서버로 올린 뒤 해당 키를 지운다. 대화방 경계는 올리지 않는다. 서버 백필로 만든 "이전 대화" 방 하나로 합쳐진다.

## 6. 영향받는 테스트

- `Backend/tests/test_chat_history.py`: fake repo의 `recent_chats(user_id, category, limit)` 시그니처에 `room_id` 추가
- `Backend/tests/test_repo_recent_chats.py`: room_id 필터 케이스 추가
- 신규: 남의 방 `roomId`로 질문·삭제·이름 변경 시 404, 로드맵 체크·해제 upsert, 사업계획서 초안 upsert

## 7. 검증 절차

1. Backend 기동 로그에 오류가 없고, `psql`에서 `\d chat_rooms`, `\d user_roadmap_progress`, `\d bizplan_drafts`, `\d chat_messages`(room_id) 확인
2. `SELECT COUNT(*) FROM chat_messages WHERE room_id IS NULL AND user_id IS NOT NULL` 결과가 0
3. Backend를 재기동해도 `chat_rooms` 행 수가 늘지 않음(백필 멱등성)
4. `pytest Backend/tests` 통과, `npx vite build` 통과
5. 데모 계정으로 방 2개 생성·이름 변경·삭제, 로드맵 체크, 사업계획서 임시저장 후 시크릿 창에서 로그인해 같은 상태인지 확인
6. 두 번째 방에서 질문할 때 LLM 요청의 `conversationHistory`에 첫 방 대화가 없는지 Backend 로그로 확인

## 8. 남은 위험

- `task_key`가 `단계:인덱스` 형식이라 `constants.js`의 `ROADMAP_TASKS` 항목 순서가 바뀌면 체크가 다른 항목에 붙는다. 지금 프론트가 키에 `v2`를 붙여 대응하는 것과 같이 `version` 컬럼을 올려 무효화한다. 근본 해결은 각 항목에 고정 id를 두는 것이다.
- compose 밖(호스트)에서 띄운 Backend는 `_apply_extras`에 의존하는데, `DO $$` 블록 때문에 파일 전체가 적용되지 않는다. 이 경우 `psql`로 직접 적용해야 한다. 백필 결과는 7절 2번 쿼리로 확인한다.
- 기존 localStorage의 방 구분·이름·숨김은 서버로 옮기지 않는다. 기존 대화는 카테고리별 "이전 대화" 방 하나로 합쳐져 보이고, 예전에 숨긴 방도 다시 보인다.
- 방 삭제가 soft delete라 사용자가 지운 대화 원문이 서버에 남는다. 보존 기간과 완전 삭제(회원 탈퇴 등) 정책은 팀 합의가 필요하다.
- `DELETE /chat/messages?ids=`를 없앴다. 방 단위 삭제는 `DELETE /chat/rooms/{id}`를 쓴다.
