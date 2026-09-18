# 프론트엔드 수정 기록

내가 "이렇게 바꿔줘" 라고 요청한 내용과, 그에 따라 실제로 바뀐 파일을 정리한 로그.
최신 항목이 위로 온다.

## 새 요청을 추가하는 방법

아래 템플릿을 복사해 **맨 위 `---` 바로 아래**에 붙여넣는다.

```
## YYYY-MM-DD · <한 줄 제목>
**요청**: <내가 부탁한 내용 그대로 / 요약>
**변경**:
- `<파일경로>` — <무엇을 어떻게>
**메모**: <선택 - 트레이드오프, 되돌리는 법 등>
```

---

## 2026-09-14 · 홈페이지 AI 대화창 로그인 분기 되돌림
**요청**: 메인페이지 3번째(AI 대화) 섹션을 로그인 여부와 무관하게 예전 데모 방식으로 되돌려줘
**변경**:
- `src/pages/Home.jsx` — `ChatDemo`가 `user`를 받아 로그인 시 `<AiConsult>`(실제 세무/공고지원과 같은 백엔드 연결)를, 비로그인 시 데모를 보여주던 분기를 제거. 이제 로그인 여부와 상관없이 항상 정해진 대사가 재생되는 연출용 데모(`chatbox`)만 보여준다
- `src/pages/Home.jsx` — 더 이상 안 쓰는 `AiConsult`, `HOME_CHAT_SUGGESTIONS` import 제거, `<Home>`에서 `<ChatDemo user={user} />` → `<ChatDemo />`
- `src/styles/04-ai-chat.css` — 실제 AI 대화창 크기를 맞추던 `.chat__live` 규칙 제거(더 이상 아무 데서도 안 쓰임)
**메모**: 이 분기는 지난 턴("홈페이지 대화창 로그인 여부로 분기")에서 넣은 것이었는데, 이번 요청으로 그 이전 상태(항상 데모)로 되돌렸다. 로그인·비로그인 양쪽 다 데모가 뜨고 콘솔 에러 없는 것까지 실제 화면으로 확인했다.

## 2026-09-14 · App.jsx · styles.css 파일 분리 (기능 단위 리팩터링)
**요청**: App.jsx(3,954줄)와 styles.css(4,326줄)에 코드가 너무 몰려있어서 나눠서 정리해줘

**변경 — styles.css (12개 파일로 분리)**:
- `src/styles/01-base.css` ~ `12-misc.css` — 원본에 있던 섹션 구분 그대로, 순서대로 12조각
- `src/styles.css` 는 이제 `@import` 12줄만 남았다. **캐스케이드 순서가 결과에 영향을 주므로 원본 순서를 그대로 유지**했고, 빌드된 CSS가 분리 전과 **바이트 단위로 완전히 동일**한 것까지 확인했다(해시 `index-8WPzl_Uf.css` 불변)

**변경 — App.jsx (18개 파일로 분리)**:
```
src/
  constants.js          상수·목데이터 (432줄)
  utils.js              순수 로직 헬퍼: 날짜·localStorage 저장·판정 (231줄)
  hooks.js               useInView / useCountUp / useThemeToggle (75줄)
  components/
    common.jsx           Reveal, Metric, ScrollProgress, FloatingThemeToggle
    Markdown.jsx          AI 답변 마크다운 렌더러
    MenuDrawer.jsx / LoginModal.jsx / Nav.jsx
    AiConsult.jsx         AI 대화 엔진(세무·공고지원·로드맵 공용, 709줄)
    roadmapIcons.jsx      로드맵 단계 아이콘(홈 스트립 + 로드맵 페이지 공용)
  pages/
    MyPage.jsx            마이페이지 전체 — MpCalendar 등 하위 컴포넌트 포함(806줄)
    RoadmapGuide.jsx / TaxAssistantPage.jsx / AnnouncementAnalyzer.jsx / SubPage.jsx
    Home.jsx               홈 화면 전체 — Hero/Calendar/ChatDemo 등 포함(490줄)
    GovExplorer.jsx / TaxTool.jsx  — 확인 결과 어디서도 안 쓰는 화면(메뉴에서 이미 빠짐). 삭제하지 않고 그대로 보존만 함
  App.jsx                 App() 본체만 남음 (3,954줄 → 214줄)
```
- 컴포넌트는 `function` 선언이라 호이스팅되므로, 같은 파일 안에서는 등장 순서를 그대로 유지해 참조 순서 문제가 없게 했다. 파일 간 참조는 전부 `export`/`import`로 명시적으로 연결

**검증**:
- 자동 스크립트로 "파일마다 쓰는데 import도 없고 자기 정의도 아닌 이름"을 전수 검사해 실제 문제 다수 발견·수정: `USER_STORE_KEY`, `useCountUp`, `pad2`, `MenuDrawer`, `eventsByDate`, `HERO_TITLE`, `useApi`, `useCallback`(hooks.js) 등 — import 누락은 `vite build`가 못 잡는 종류(문법은 멀쩡하니 빌드는 성공하고, 실행 시점에 `ReferenceError`로만 드러남)라 이 전수 검사가 없었으면 놓쳤을 것들이다
- `rmIcon`/`rmDoneIcon`(로드맵 단계 아이콘)이 홈 화면과 로드맵 페이지 양쪽에서 쓰여서, 원래 계획대로 Home.jsx 안에만 두지 않고 `components/roadmapIcons.jsx`로 별도 분리
- 실제 크롬을 CDP로 띄워 콘솔 에러를 감시하며 로그인 → 홈 4개 카드(로드맵·세무AI·공고지원AI·마이페이지) → 마이페이지 하위 메뉴 4개 → 로드맵 체크리스트 클릭 → AI 코치에 실제 질문 전송까지 전부 재현 — 마지막에 실제 근거 인용 답변이 정상적으로 돌아오는 것까지 확인했다
- 최종 빌드 결과물이 분리 전과 **완전히 동일**함을 확인(CSS 해시 불변, JS 223.4x kB로 동일 크기대)

**메모**: `GovExplorer.jsx`/`TaxTool.jsx`는 지난 세션에서 메뉴가 빠지면서 이미 죽어있던 코드라 그대로 안 쓰는 상태로 옮겨만 뒀다. 되살리려면 각 파일을 어디선가 import 해서 렌더링하면 된다.

---

## 2026-09-14 · 대화방 삭제 API에 빈 ids 전달 차단
**요청**: ids가 빈 배열이면 대화방 삭제가 전체 기록 삭제로 이어지는 문제 해결
**변경**:
- `src/api.js` — `deleteMessages`가 ids가 비어 있으면 요청을 보내지 않고 reject한다. `qs()`가 빈 값을 빼서 `DELETE /chat/messages`(파라미터 없음 = 전체 삭제)가 되던 경로다. 호출부 `deleteRoom`은 기존 실패 경로(브라우저에서만 숨김 + 안내)로 처리하므로 `App.jsx`는 그대로 둔다
**메모**: 결함 52(`Docs/reports/INTEGRATION_ISSUES_0914.md`), `01a57ee`. 현재 UI 흐름에선 빈 ids가 나올 수 없어 잠재 위험 차단용이다.

## 2026-09-14 · 대화방 삭제 시 서버(DB) 기록도 함께 삭제
**요청**: 대화방 삭제하면 db에서도 제거해줘 — 직전 "이 브라우저에서만 숨기기" 구현을 서버 삭제로 확장하는 요청이라, 이번엔 Backend/DB도 같이 수정했습니다(평소 원칙인 Frontend 전용 범위를 벗어남 — 명확한 요청이라 진행).

**변경**:
- `Backend/core/repo.py` — `delete_chats_by_ids(user_id, message_ids)` 추가. 지정한 id들만 지우되, 그 사용자 소유가 아닌 id는 조용히 건너뛴다(`WHERE id = ? AND user_id = ?`)
- `Backend/services/chat_service.py` — `delete_messages(user_id, message_ids)` 추가 (`repo.delete_chats_by_ids` 호출)
- `Backend/api/chat.py` — 기존 `DELETE /chat/messages`(카테고리 전체 삭제)에 `ids` 쿼리 파라미터 추가. `ids`를 주면 category는 무시하고 그 메시지들(대화방 하나)만 지운다. 새 라우트를 만들지 않고 기존 엔드포인트를 확장했다
- `Frontend/src/api.js` — `api.deleteMessages(ids)` 추가 (`DELETE /chat/messages?ids=1,2,3`)
- `Frontend/src/App.jsx` — `deleteRoom`을 `async`로 바꾸고, 실제 메시지가 있는 방은 `api.deleteMessages(idsToDelete)`를 먼저 호출:
  - **성공** — `rows`에서 그 id들을 실제로 빼고(완전히 사라짐), 관련 `roomNames`/`hiddenIds` 항목도 정리
  - **실패**(네트워크 등) — 기존처럼 이 브라우저에서만 숨기고(`hiddenIds`), "서버에서 지우지 못했어요 — 잠시 후 다시 시도해 주세요" 안내
  - 확인창 문구를 "서버에 저장된 기록도 함께 지워지고, 되돌릴 수 없습니다"로 변경(전에는 "이 브라우저에서만" 이었음)
  - 메시지 없는 "새 대화" 삭제(되돌리기)는 지울 서버 데이터가 없으니 그대로 유지

**메모**: 백엔드는 `uv run uvicorn` 을 `--reload` 없이 띄우고 있어서(`Backend/Dockerfile`) 코드를 바꾼 뒤 `docker restart` 로 반영했다. 검증: (1) 직접 로그인 토큰으로 `curl -X DELETE ".../chat/messages?ids=118,119"` 호출 → DB에서 실제로 사라지는 것 확인 (2) 새 테스트 계정을 만들어 실제 프론트엔드 UI로 방 2개를 만들고, 한 방을 삭제 버튼으로 지운 뒤 `chat_messages` 테이블을 직접 조회 — 지운 방의 메시지만 정확히 사라지고 다른 방은 그대로 남는 것까지 확인했다. 테스트로 만든 메시지·데이터는 정리했다.

## 2026-09-14 · 세무 AI 대화방 삭제 기능
**요청**: 세무AI 대화방들에 삭제 기능도 붙여줘 (백엔드에 방 단위 삭제 API가 없어서, "이 브라우저에서만 숨기기" 방식으로 확인받고 진행)

**변경**:
- `src/App.jsx` — `HIDDEN_ROOMS_KEY`/`loadHiddenRooms`/`saveHiddenRooms` 추가. `changeup:chat-room-hidden:{userId}:{category}` 에 지운 방들의 첫 메시지 id를 배열로 저장한다(이름 바꾸기 때 만든 `ROOM_NAMES_KEY`와 같은 패턴)
- `src/App.jsx` — `AiConsult`에 `hiddenIds` state 추가, 기록 로드·초기화·"대화 기록 지우기" 지점에서 `roomNames`와 동일하게 같이 불러오고/비운다
- `src/App.jsx` — `deleteRoom(room)` 함수 추가. 세 경우로 나뉜다:
  - 메시지가 아직 없는 "새 대화" → 지울 서버 기록이 없으니 그 방을 만든 경계만 되돌린다(사실상 "새 대화 시작 취소"). 이때 되돌아간 방이 전에 숨겨졌던 방이면(아래 항목의 결과) 같이 다시 보이게 한다
  - **지금 이어서 쓰는 방(lastRoom)** → 숨기기 전에 그 방의 마지막 메시지 id를 새 경계로 추가해 먼저 분리한다. 그래야 다음 질문이 지워진 방에 안 섞이고 새 빈 방에서 시작된다
  - 그 외(이미 끝난 옛 방) → 그냥 첫 메시지 id를 숨김 목록에 추가
  - 응답을 기다리는 중인 방(`pendingRoomIdx`)은 삭제 버튼 자체를 숨겨서 못 지우게 막는다
- `src/App.jsx` — `roomList` 필터에 숨김 목록 제외 조건 추가
- `src/App.jsx` — 사이드바 각 방 줄에 🗑 삭제 버튼 추가(이름 바꾸기 ✎ 버튼 옆). 클릭하면 확인창(`confirm`) 후 삭제
- `src/styles.css` — `.cvx__del` 스타일(hover 시 빨간 톤)

**메모**: 서버 기록 자체는 지우지 않는다 — 다른 기기에서 로그인하거나 이 브라우저의 저장 데이터를 지우면 다시 보인다. 전체 삭제가 필요하면 기존 "대화 기록 지우기"(카테고리 전체 삭제)를 쓰면 된다. Node CDP 스크립트로 세 경우(일반 방 삭제, 이어쓰는 방 삭제, 빈 새 대화 되돌리기)를 실제 클릭으로 재현해 확인 — 특히 "이어쓰는 방 삭제 → 되돌리기"를 연달아 했을 때 원래 방 내용이 정확히 복원되는 것까지 확인했다. 이 과정에서 처음엔 테스트 스크립트 자체의 버그(여러 `Runtime.evaluate` 호출에서 변수를 재선언해 예외가 나는데 그 예외를 못 잡고 있었음)로 오작동처럼 보였던 걸 스크립트를 고쳐서 바로잡았다 — 실제 기능 코드는 처음 구현대로 정확했다.

## 2026-09-14 · 응답 기다리는 중에도 다른 대화방 보기 + 대화방 목록 버그 수정
**요청**: 1. LLM 응답 속도 개선 (보류 — LLM/Backend 코드를 손대야 해서 이번엔 제외) 2. 세무AI 대화방은 첫 질문으로 우선 만들고 이후 수정 가능하게 (지난 턴 "대화방 이름 바꾸기" 작업이 이미 이 요구사항 — 추가 작업 없음) 3. 세무 AI에서 응답 생성 중에도 다른 대화방을 볼 수 있게

**변경(3번)**:
- `src/App.jsx` — `AiConsult`에 `pendingRoomIdx`(지금 응답을 기다리는 방), `pendingTurnsRef`(그 방에 막 던진 질문 스냅샷), `roomIdxRef`(비동기 콜백에서 최신 roomIdx를 읽기 위한 ref) 추가
- `src/App.jsx` — `ask()` 안의 모든 `setTurns((cur)=>[...cur, 답변])` 호출을 `appendTurn()` 헬퍼로 바꿨다. 질문을 던진 방을 계속 보고 있을 때만(`isViewingAsked()`) 화면에 반영하고, 다른 방으로 옮겨갔으면 조용히 건너뛴다(응답 자체는 `rows`에 그대로 쌓여 나중에 다시 열면 보인다). `setErr`/`setNeedsLogin`/스트리밍 `setStream`도 같은 방식으로 가드
- `src/App.jsx` — `openRoom()`에서 `busy` 가드 제거(더 이상 응답 중이라고 다른 방 클릭을 막지 않는다). 응답 기다리는 방으로 돌아오면 `rows`(아직 서버 미반영) 대신 `pendingTurnsRef`의 스냅샷으로 복원해 방금 던진 질문이 그대로 보이게 한다
- `src/App.jsx` — 사이드바 목록 필터가 "지금 보고 있는 빈 방"만 남기던 것을 "응답 기다리는 방"도 남기도록 수정(원래 이 필터 때문에 다른 방으로 옮기면 응답 대기 중인 방 자체가 목록에서 사라지는 게 진짜 버그였다). 그 방의 제목도 `rows`에 아직 없으니 "새 대화" 대신 방금 던진 질문 텍스트를 보여주도록 수정
- `src/App.jsx` — 사이드바 각 방 제목 옆에 응답 대기 중 표시(점 3개 깜빡임, `.cvx__pending`) 추가. 입력창 placeholder는 다른 방을 보는 동안 "다른 대화방에서 응답을 기다리는 중이에요…"로 안내
- `src/App.jsx` — (지난 턴 이름 바꾸기 기능의) 숨은 버그 수정: `renamingId`(초기값 null)와 빈 방의 `firstId`(역시 null)가 같아서, 메시지 없는 새 방을 열면 항상 이름 편집 입력칸이 떠 있었다. `renamingId != null && renamingId === room.firstId` 로 조건 보강
- `src/styles.css` — `.cvx__pending` 점 3개 깜빡임 스타일 추가(기존 `.typing`의 `blink` 애니메이션 재사용)

**메모**: 1번(속도 개선)은 보류 상태로 남겨 뒀다 — 다음에 LLM/Backend까지 건드려도 되는지 다시 여쭤보고 진행. 3번은 Node로 실제 크롬을 CDP로 직접 조작하는 스크립트를 만들어 검증했다: 응답을 인위적으로 늦춰 놓고 ① 대기 중 다른 방 클릭 → 정상 전환 + 대기중이던 방에 점 표시 유지 ② 대기 중이던 방으로 복귀 → 스냅샷으로 질문이 그대로 복원되고 타이핑 표시 재개 ③ 응답 도착 시(그 방을 보고 있으면) 정상 반영, busy·대기점 정리까지 전부 확인. 이 과정에서 방 목록 필터 버그와 이름 바꾸기 null 충돌 버그를 추가로 잡았다(둘 다 오늘 새로 만든 게 아니라 원래 있던 문제가 이번 검증으로 드러난 것).

## 2026-09-14 · 세무 AI 대화방 이름 바꾸기
**요청**: 세무 AI 채팅방 이름을 수정할 수 있게 해줘
**변경**:
- `src/App.jsx` — `ROOMS_KEY` 바로 아래 `ROOM_NAMES_KEY`/`loadRoomNames`/`saveRoomNames` 추가. `changeup:chat-room-names:{userId}:{category}` 에 `{ 첫메시지id: 직접정한이름 }` 형태로 저장한다(로그인 여부·화면별로 이미 분리돼 있는 `ROOMS_KEY`와 같은 방식)
- `src/App.jsx` — `AiConsult` 에 `roomNames`/`renamingId`/`renameDraft` state 추가. 기록을 불러오는 `[userId, category]` effect에서 `roomNames` 도 같이 읽어 오고, `대화 기록 지우기` 를 누르면 이름도 함께 비운다
- `src/App.jsx` — `roomList` 의 `title` 이 `roomNames[첫메시지id] || 첫질문` 을 쓰도록 변경. `startRename`/`cancelRename`/`submitRename` 3개 함수 추가 — 이름을 비우고 저장하면 기본 제목(첫 질문)으로 되돌아간다
- `src/App.jsx` — 사이드바 목록 줄마다 연필 아이콘(`✎`, `.cvx__edit`)을 붙였다. 누르면 그 줄이 입력칸(`.cvx__rename`)으로 바뀌고, Enter·체크 버튼·포커스 아웃 중 아무거나로 저장, Esc로 취소된다
- `src/styles.css` — `.cvx__conv` 를 감싸던 `is-active`/hover 배경을 `.cvx__row`(버튼+연필 아이콘을 한 줄로 묶는 wrapper) 로 옮기고, `.cvx__edit`/`.cvx__rename` 스타일 추가
**메모**: 이름 편집은 메시지가 있는 방에만 가능하다(연필 아이콘이 첫 메시지 id가 있을 때만 뜬다) — 빈 "새 대화" 는 아직 식별자가 없어서 대상에서 뺐다. Node CDP 스크립트로 실제 클릭→입력→저장→새로고침까지 시나리오를 돌려 확인: 제목 변경, `localStorage` 저장, 새로고침 후 유지, 빈 값 저장 시 원래 질문으로 복귀까지 전부 의도대로 동작했다.

## 2026-09-14 · 홈페이지 대화창 로그인 여부로 분기
**요청**: 홈페이지 대화창을 사용자별로 뜨게 해줘 (확인 결과: 비로그인은 지금처럼 연출용 데모, 로그인하면 실제 AI와 연결된 대화창)
**변경**:
- `src/App.jsx` — `ChatDemo()` → `ChatDemo({ user })`. 이 화면에 오는 `Home`은 이미 `user`를 갖고 있어 그대로 내려주기만 했다(`<ChatDemo user={user} />`)
- `src/App.jsx` — 오른쪽 대화창 영역을 `user` 유무로 분기. 비로그인은 기존 정해진 대사 재생 데모(`chatbox`) 그대로. 로그인 상태는 `<AiConsult user={user} category="saving" suggestions={HOME_CHAT_SUGGESTIONS} compact title="창업ON 어시스턴트" />` — 세무 AI·공고지원 AI와 같은 실제 백엔드/LLM 연결 컴포넌트를 그대로 재사용
- `src/App.jsx` — `HOME_CHAT_SUGGESTIONS` 신설: 왼쪽 마케팅 태그(지원사업 매칭·세액감면 판정·신고 일정 등록·경비처리 상담) 4개와 짝을 맞춘 시작 질문
- `src/styles.css` — `.chat__live { align-self:center }` + `.chat__live .ai { max-width:none; height:520px }` 로 기존 데모 chatbox와 같은 자리·크기에 들어가게 맞춤
**메모**: category는 `saving`을 썼다 — 세무 AI(`tax`)·공고지원 AI(`policy`)·로드맵(`roadmap`)은 이미 전용 화면이 있어서 같은 category를 재사용하면 그 화면들의 "상담 기록"에 홈 대화가 섞여 보이게 된다. `saving`은 전용 화면이 없어 겹치지 않는다. AiConsult 안내문(`user.biz · user.region 기준으로 답해 드려요`)이 로그인한 사용자의 실제 사업 정보를 그대로 반영해 보여준다. 검증: 이 페이지는 스크롤 진입 애니메이션(Reveal)이 있어 스크린샷보다 렌더된 DOM 텍스트로 확인 — 로그아웃 시 기존 데모 문구, 로그인 시 `chat__live`/실제 힌트 문구/추천 질문 4개가 정확히 나오는 것을 확인했다.

## 2026-09-14 · 마이페이지 메뉴에서 진단 결과·상담 기록 제거
**요청**: 마이페이지 왼쪽 메뉴에서 진단 결과, 상담 기록 제거
**변경**:
- `src/App.jsx` — `MP_MENU` 에서 `{ key: 'diagnosis', label: '진단 결과' }`, `{ key: 'chatlog', label: '상담 기록' }` 두 항목 삭제. 남은 메뉴는 `마이페이지 / 내 정보(사업자 정보) / 저장한 것(공고·정책, 서류) / 설정`
- `src/App.jsx` — `MyPage` 렌더링에서 `menu === 'diagnosis'`(`<BizTypeDiagnosis /> + <TaxTool />`), `menu === 'chatlog'`(`<ChatLog />`) 분기 삭제
**메모**: 화면 컴포넌트 정의는 **남겨 뒀다** — `BizTypeDiagnosis`, `TaxTool`, `ChatLog` 는 소스에 그대로 있다. 되살리려면 `MP_MENU` 항목과 분기 한 줄씩만 되돌리면 된다. `setMenu` 는 메뉴 클릭에서만 호출하므로 지운 키로 들어갈 경로는 없다. 참조가 끊겨 번들에서는 빠졌다(빌드 217.26 kB, 이전 224.22 kB).

## 2026-09-14 · 메인 달력 고정 · 안내 문구 삭제 · 카드 상담 연동 · 로드맵 진행률 저장
**요청**: 1. 메인페이지 달력을 마이페이지와 연동하지 말고 임의 일정 3개로 고정  2. "로그인하면 맞춤 공고와 세무 대시보드가 열립니다" 문구 삭제  3. 마이페이지 세무AI·공고지원AI 카드를 실제 상담 내용과 연동(카드 크기 고정)  4. 창업 로드맵 %가 새로고침해도 유지되게

**변경**:
- `src/App.jsx` — `Calendar`(메인) 의 `useApi('/calendar?...')` + `pickImportant()` 호출 제거 → `const events = CAL_EVENTS`. 서버를 아예 부르지 않으므로 마이페이지에서 등록한 일정이 메인에 뜨지 않는다
- `src/App.jsx` — `CAL_EVENTS` 를 2025년 10~11월 7건(지금 달에는 보이지도 않던 값) → **이번 달 기준 3건**(10일 원천세, 17일 청년창업사관학교 마감, 25일 부가세 예정신고)으로 교체. `dayKey` 정의 뒤로 옮겼다. 쓰이지 않게 된 `pickImportant()` 정의도 삭제
- `src/App.jsx` — 안내 문구 두 군데 삭제: 햄버거 드로어의 로그인 버튼 아래 `.drawer__hint`, 메인 맨 아래 CTA 문단
- `src/App.jsx` — 하드코딩 상수 `MP_TAX_SUMMARY`/`MP_GOV_SUMMARY` 삭제, `MP_RECENT_MAX = 5` 추가. `MyPage` 에서 `api.chatHistory('tax')`·`('policy')` 를 한 번에 불러 **최근 질문 5개**를 최신순으로 카드에 띄운다(`recentQ`). 기록이 없으면 "아직 상담 기록이 없어요"
- `src/styles.css` — `.mp-rows--recap .mp-consult` 에 `white-space: nowrap` + `text-overflow: ellipsis`. 질문이 길어도 한 줄이라 줄 수가 고정되고 카드 높이가 안 흔들린다. 잘린 질문은 `title` 속성으로 전체 확인 가능. 빈 상태용 `.mp-consult--none` 추가
- `src/App.jsx` — 로드맵 체크 상태를 `useState({})` → `useState(loadRoadmapDone)` 로 바꾸고, `roadmapDone` 이 바뀔 때마다 `localStorage`(`changeup:roadmap-done`)에 저장하는 effect 추가. `savedGov` 와 같은 방식

**메모**: 4번은 크롬 프로필을 유지한 채 2회 실행해 확인했다 — 1차에서 체크 3개를 심어 `{"A:0":true,"A:1":true,"B:0":true}` 가 저장되고, 심는 코드를 뺀 2차(=새로고침 상황)에서도 그대로 복원됐다. 1번은 렌더된 DOM에서 `cal__dot` 이 정확히 3개, 3번은 기록 6건 중 최신 5건만 뜨는 것을 화면으로 확인했다.

## 2026-09-14 · 세무 AI 대화방 목록 날짜 오류 수정
**요청**: 새 대화를 띄우면 '새 대화' 창만 떠야 하는데 '날짜 없음' 그룹이 생기고 '오늘'이 여러 번 나오는 오류 수정
**변경**:
- `src/App.jsx` — 방금 보낸 메시지를 `rows` 에 넣을 때 `created_at` 을 안 넣고 있었다. `created_at: new Date().toISOString()` 추가. 이게 `날짜 없음` 그룹의 직접 원인(서버에서 다시 받아오면 정상이라 새로고침하면 사라지던 증상)
- `src/App.jsx` — 사이드바 그룹핑이 **바로 옆 방끼리만** 묶던 것을 `Map` 으로 같은 날짜를 모두 모은 뒤 `roomGroups.sort((a, b) => (b.day || '').localeCompare(a.day || ''))` 로 최신순 정렬. 방 순서(메시지 id 순)와 날짜 순서가 어긋나도 "오늘"은 항상 하나
- `src/App.jsx` — 날짜를 모르는 옛 기록 라벨 `날짜 없음` → `날짜 미상`, 정렬상 맨 아래로
- `src/App.jsx` — `roomList` 에서 메시지가 없는 방을 걸러낸다. 지금 보고 있는 방(`room.i === roomIdx`)만 남기므로 `빈 대화` 항목이 사라지고, 현재 새 대화는 `새 대화` 로 계속 보인다
- `src/App.jsx` — 기록을 불러올 때(`api.chatHistory` 성공 직후) 빈 방을 만드는 죽은 경계를 정리한다. 비어 있지 않은 방 + 마지막 방만 남기고(`live`) 경계를 다시 계산(`tidy`)해 `localStorage`(`changeup:chat-rooms:<category>`)에 덮어쓴다
**메모**: 사용자 화면과 같은 조건(중복 경계로 생긴 빈 방 + 날짜가 뒤섞인 방 + `created_at` 없는 행)을 넣고 확인 — `오늘 2`(새 대화 + 부가세 방), `9월 12일 1`, `날짜 미상 1` 로 정리되고 `빈 대화` 는 사라졌다. 대화 기록 자체는 지우지 않고 경계만 정리한다.

## 2026-09-14 · 세무 AI 대화방 목록 날짜별 묶기
**요청**: 세무 어시스턴트 왼쪽 대화방 모아놓은 걸 오늘·어제·날짜별로 볼 수 있게 수정
**변경**:
- `src/App.jsx` — `rowsToTurns` 위에 날짜 헬퍼 2개 추가. `dayKeyOf(v)` 는 저장 시각을 `YYYY-MM-DD` 로 줄이고(형식이 예상과 달라도 앞 10글자는 건진다), `dayLabel(key)` 는 오늘/어제/`9월 12일`(해가 다르면 `2025년 9월 12일`)로 바꾼다
- `src/App.jsx` — 사이드바 `roomList` 항목에 `day` 추가. 방의 **마지막 메시지** `created_at` 을 기준으로 잡는다(마지막으로 대화한 날에 묶이도록). 아직 비어 있는 새 방은 오늘로 둔다
- `src/App.jsx` — `roomList` 를 최근 방부터 훑어 같은 날짜끼리 `roomGroups` 로 묶는다
- `src/App.jsx` — 사이드바 렌더링에서 `대화 N개` 머리글 하나 → 날짜 머리글마다 방을 나열. 머리글 오른쪽에 그 날짜의 방 개수를 붙였다
- `src/styles.css` — `.cvx__group` 을 flex 로 바꿔 라벨/개수를 양끝 정렬, `:not(:first-child)` 에 위 여백 12px, 개수용 `.cvx__group-n` 추가
**메모**: 사이드바(`withSidebar`)를 쓰는 화면은 `TaxAssistantPage` 하나뿐이라 다른 상담 화면에는 영향이 없다. 방 구분 자체는 기존대로 localStorage 경계(`changeup:chat-rooms:tax`)를 그대로 쓰고, 표시 방법만 바뀌었다. 4개 방(오늘·어제·9월 12일·9월 8일)을 넣고 화면으로 확인했다.

## 2026-09-14 · 마이페이지 카드 높이 채우기 · 달력 일정 목록 스크롤
**요청**: 이미지처럼 마이페이지 카드 크기를 바꾸고, 달력에 일정을 넣을 때 크기는 고정되고 스크롤로 내려서 볼 수 있게 수정
**변경**:
- `src/App.jsx` — 마이페이지 `<main className="mp-main">` → 대시보드일 때만 `mp-main--dash` 를 붙인다 (`menu === 'home'`). 다른 메뉴 화면 레이아웃은 건드리지 않기 위한 분기
- `src/App.jsx` — `MpCalendar` 의 일정 항목들을 `<div className="cal__evlist">` 로 감쌌다. 추가 입력 폼(`.cal__add`)은 바깥에 그대로 둬서 일정이 늘어도 위치가 움직이지 않는다
- `src/styles.css` — `.mp-main--dash` 를 flex 세로 배치로 두고 `.mp-dash { flex: 1; min-height: 430px }`. 대시보드가 화면에 남는 세로를 끝까지 쓴다
- `src/styles.css` — `.mp-dash .mp-grid` 의 `grid-auto-rows: 1fr`(두 줄 균등) → `grid-template-rows: minmax(190px, auto) minmax(0, 1fr)`. 윗줄(로드맵 진행률)은 제 높이만 쓰고 아랫줄(세무 AI·공고지원 AI)이 나머지를 가져간다
- `src/styles.css` — `.mp-dash .cal` 의 `align-self: start` → `stretch` + flex 세로 배치. 캘린더 카드도 왼쪽 카드와 같은 높이로 맞춰진다. 달력 칸(`.cal__grid`)·입력 폼은 고정, `.cal__events`/`.cal__evlist` 가 남는 세로를 먹는다
- `src/styles.css` — `.cal__evlist` 신설: 기본 `max-height: 150px; overflow-y: auto`(다른 화면용), 대시보드에서는 `max-height: none` 으로 풀고 flex 로 늘린다. 스크롤바는 기존 `.govm__scroll` 과 같은 톤으로 얇게
- `src/styles.css` — 1080px / 860px 이하 분기에서 `grid-template-rows: none`, `.cal { align-self: start }`, `.mp-dash { min-height: 0 }` 로 되돌려 좁은 화면에서는 예전처럼 내용 높이대로 쌓인다
**메모**: 9건을 넣고 확인 — 캘린더 카드 높이와 "일정 추가" 입력칸 위치는 그대로고 목록만 스크롤된다. 공고지원 AI 화면의 달력은 일정 목록·추가 폼이 없는 구성이라 영향 없음(확인 완료).

## 2026-09-14 · 마이페이지 메뉴 이름 변경 · 상담 기록 기능별 분리
**요청**: 1. 마이페이지 왼쪽 "상담하기" -> "마이페이지" 이름 변경  2. 상담 기록에 저장되는 대화들을 창업로드맵 / 세무AI / 공고지원AI 기능별로 나눠서 볼 수 있게 수정
**변경**:
- `src/App.jsx` — `MP_MENU` 첫 항목 라벨 `'상담하기'` → `'마이페이지'` (키 `home` 은 그대로라 동작 변화 없음)
- `src/App.jsx` — `ChatLog` 위에 `CHATLOG_TABS`(roadmap / tax / policy) 상수 추가. 각 상담 화면이 저장할 때 쓰는 `category` 와 같은 값이다
- `src/App.jsx` — `ChatLog` 가 `api.chatHistory('tax')` 하나만 부르던 것을 `Promise.all` 로 세 카테고리를 한 번에 받아 `logs` 에 보관하도록 변경. 탭 버튼(`.mp-tabs`/`.mp-tab`)에 `라벨 N건` 을 표시하고, 선택한 탭의 기록만 최신순으로 나열한다
**메모**: 탭 전환은 이미 받아 둔 데이터를 바꿔 끼우는 것이라 재요청이 없다. 세 호출 모두 실패할 때만 오류 문구를 띄우고, 일부만 실패하면 해당 탭이 0건으로 보인다. `.mp-tabs`/`.clog` 스타일은 이미 있던 것을 그대로 쓴다.

## 2026-09-12 · 로드맵 단계 스트립 축소 · 대화창 확대

**요청**: 창업 로드맵 페이지의 위쪽 단계 이미지를 약간 줄이고, 아래 대화창 높이를 더 키우기.

**변경**: `src/styles.css` `.fp--wide` 압축 모드 — 로드맵 화면은 대화창이 남은 높이를 채우는 구조라, 위쪽을 줄인 만큼 대화창이 커진다
- `.rz--nav` 아이콘 38 → **30px**(radius 12 → 10), 내부 svg 19 → **16px**
- `.rz--nav .rz__step` 세로 padding 7 → **5px**, gap 4 → 3px
- `.rz--nav` 아래 여백 `padding-bottom` 8 → 5px, `margin-bottom` 8 → 6px
- `.rz--nav .rz__sep`(화살표) `margin-top` 18 → 13px, 15 → 14px
- `.rg2__prog`(진행률 줄) 아래 여백 12 → **8px**

**메모**: 실제 높이를 재서 확인했다 — 단계 스트립 **106 → 89px**, 대화창 **532 → 555px**(1450×900 기준). 단계명·라벨 글자 크기는 그대로 둬서 읽기 어려워지지 않게 했다. `npx vite build` 통과.

## 2026-09-12 · AI 답변 마크다운 렌더 + 저장한 공고 유지

**요청**: 실사용에서 발견된 문제 중 (1) AI 답변이 마크다운인데 화면에는 문자열 그대로 나옴 (6) 마이페이지 저장한 공고가 다른 페이지 갔다 오면 초기화됨 (7) 캘린더 일정이 늘면 로드맵 진행률도 같이 늘어남 — 세 가지 해결.

**변경**:
- `src/App.jsx` (신규) `Markdown`·`mdInline` — AI 답변을 마크다운으로 렌더한다. **외부 라이브러리 없이** `### 제목`, `- `/`1. ` 목록, `**굵게**`, `*기울임*`, `` `코드` ``, `> 인용`, 빈 줄 문단을 React 엘리먼트로 변환한다. HTML 문자열을 주입하지 않아(`dangerouslySetInnerHTML` 미사용) XSS 위험이 없다
- `src/App.jsx` `AiConsult` — AI 답변(`role === 'assistant'`)과 생성 중 스트리밍 텍스트에 `<Markdown>` 적용. 내가 보낸 질문은 그대로 텍스트로 둔다
- `src/styles.css` (신규) `.md-p`/`.md-head`/`.md-list`/`.md-quote`/`.md-code` — 말풍선 안에서 쓰는 마크다운 스타일(사용자 말풍선의 코드 배지는 별도 대비색)
- `src/App.jsx` (신규) `SAVED_KEY`/`loadSavedGov` + `App`의 `savedGov`/`toggleSavedGov` — **저장한 공고를 App 레벨 상태로 올리고 `localStorage`(`changeup:saved-gov`)에 저장**한다. 기존에는 `MyPage` 내부 state라 화면을 벗어나면 컴포넌트가 언마운트되며 초기화됐다
- `src/App.jsx` `MyPage` — 내부 `saved` state를 제거하고 App이 내려준 `saved`/`onToggleSave`를 쓴다

**검증**: 마크다운은 제목·굵게·기울임·글머리 목록·번호 목록·코드·인용이 모두 렌더되는 것을 확인했다. 저장 목록은 공고 저장 → `localStorage`에 `["g9"]` 기록 → "상담하기"로 이동 후 복귀 → **"저장한 공고 1건" 유지**를 자동 클릭 테스트로 확인했다(기존에는 0건으로 초기화).

**메모(7번 — 해결 못 함)**: 캘린더와 로드맵 진행률은 **코드상 연결이 없다**. 진행률은 `roadmapDone`만 보고 계산하고(`rmDoneCount = Object.values(roadmapDone).filter(Boolean).length`), `roadmapDone`은 로드맵 체크리스트 토글에서만 바뀐다. `MpCalendar` 안에는 로드맵 관련 참조가 하나도 없다. 다만 레이아웃상 `.mp-dash .mp-grid { grid-auto-rows: 1fr }` 때문에 **캘린더가 세로로 길어지면 로드맵 카드도 같이 길어진다** — 이걸 "진행률이 늘어난다"로 보셨을 가능성이 있어 확인이 필요하다. 백엔드 미기동으로 일정 추가를 재현하지 못했다.

## 2026-09-12 · 마이페이지 사업자 정보 폼을 회원가입과 동일하게

**요청**: (1) 마이페이지 사업자 정보의 업종·사업장 지역을 회원가입처럼 드롭다운으로, 대표자 연령은 숫자 입력으로 (2) 진단 결과를 누르면 흰 화면이 뜸.

**변경**:
- `src/App.jsx` `ProfileSettings` — 업종·사업장 지역을 자유 입력에서 **드롭다운**(`INDUSTRIES` 15개 / `REGIONS` 17개)으로, 대표자 연령을 선택형("청년/그 외")에서 **만 나이 숫자 입력**으로 교체. 회원가입 폼과 입력 방식을 통일했다
- `src/App.jsx` `ProfileSettings` — 저장된 값이 목록에 없을 때를 대비해 `pick()` 폴백 추가. 예전 형식(`대전광역시`)처럼 `REGIONS`에 없는 값이면 첫 항목으로 맞춘다. 연령은 `user.age`가 있으면 초기값으로 채운다

**메모(흰 화면 건)**: 현재 코드에서 **재현되지 않는다**. dev 서버(5173)에 오류 수집 스크립트를 붙여 ① 진단 결과 화면을 바로 열었을 때 ② 메뉴를 클릭해 들어갔을 때 ③ 보내주신 것과 같은 `#onboarding` 해시가 붙은 URL에서 모두 확인했는데, `rootEmpty=false` · 런타임 오류 없음 · "사업자 유형 진단 / 세액감면 판정 / 주요 신고 일정"이 정상 렌더됐다. 확인 작업 중 `App.jsx`를 임시 패치했다가 되돌리는 일이 반복됐고 그때 dev 서버가 중간 상태를 HMR로 반영했을 가능성이 높다. 브라우저 새로고침 후 재확인이 필요하다.

**참고**: 사업자 정보의 "저장" 버튼은 아직 화면에만 반영되고 서버 저장은 하지 않는다(회원가입 때만 `PUT /users/me`·`/users/me/business-profile`로 저장). 저장까지 연결하려면 별도 작업이 필요하다. `npx vite build` 통과, 헤드리스 크롬으로 드롭다운 15/17개와 연령 숫자 입력을 확인했다.

## 2026-09-12 · 회원가입 업종 드롭다운 + 지역 기본값 서울

**요청**: (1) 마이페이지 진단 결과를 누르면 아무것도 안 뜸 (2) 회원가입의 업종을 여러 업종 중 스크롤로 선택하게 (3) 사업장 지역은 처음에 서울이 뜨게.

**변경**:
- `src/App.jsx` (신규) `INDUSTRIES` — 한국표준산업분류 대분류 기준 업종 15개(정보통신업·전문과학기술·도소매·숙박음식·교육·제조 등)
- `src/App.jsx` `LoginModal` — 회원가입 폼의 업종을 자유 입력(`<input>`)에서 **드롭다운(`<select>`)** 으로 교체. 기본 선택은 `정보통신업`
- `src/App.jsx` `LoginModal` — 사업장 지역 초기값을 `DEFAULT_REGION`(대전) → **`REGIONS[0]`(서울)** 로 변경

**메모**: 1번(진단 결과 빈 화면)은 **현재 코드에서 재현되지 않았다**. 헤드리스 크롬으로 마이페이지에서 "진단 결과"를 눌러 보면 사업자 유형 진단과 세액감면 판정이 정상 표시된다. 확인 작업 중 임시로 `App.jsx`를 여러 번 패치했다가 되돌렸는데, 그때 켜져 있던 dev 서버(5173)가 중간 상태를 HMR로 밀어 넣었을 가능성이 있다. 지금은 dev 서버도 최신 소스를 서빙하는 것을 확인했으니 브라우저 새로고침 후 재현 여부를 봐야 한다. 회원가입 폼은 헤드리스 크롬으로 업종 15개·지역 17개 드롭다운과 초기값(정보통신업/서울)을 확인했다. `npx vite build` 통과.

## 2026-09-12 · 마이페이지 왼쪽 메뉴 재구성

**요청**: 마이페이지 왼쪽 메뉴를 "상담하기 / 내 정보(사업자 정보·진단 결과) / 저장한 것(공고·정책·상담 기록·서류) / 설정" 구조로 바꾸기(이모지 제외). 확정 사항: 자리가 없어진 화면은 다른 메뉴에 합치기, 진단 결과는 두 진단을 한 화면에, 상담 기록만 실제 구현하고 서류는 준비 중.

**변경**:
- `src/App.jsx` `MP_MENU` — 새 구조로 교체. `홈(대시보드)` → **상담하기**, 그룹 `세무관리`/`지원정책` → **내 정보**/**저장한 것**, `프로필 · 설정` → **설정**
- `src/App.jsx` `ProfileSettings` — `only` prop 추가해 한 컴포넌트를 둘로 나눠 쓴다. **사업자 정보**(`only="profile"`, 이름·이메일·업종·지역·연령 폼)와 **설정**(`only="notif"`, 알림 설정)으로 분리. 폼 제목도 "프로필" → "사업자 정보"
- `src/App.jsx` (신규) `SavedGov` — **공고 · 정책** 화면. 기존 `SavedPolicies`(저장한 공고)와 `MatchedGov`(AI 추천 공고)를 탭으로 합쳤다. 저장한 공고가 없을 때 누르던 "AI 추천 공고 보기"는 탭 전환으로 연결
- `src/App.jsx` (신규) `ChatLog` — **상담 기록** 화면. `GET /chat/messages?category=tax`로 서버에 저장된 내 질문·답변을 최신순으로 보여준다(비로그인·빈 기록·조회 실패 안내 포함)
- `src/App.jsx` 마이페이지 라우팅 — `profile`/`diagnosis`/`saved`/`chatlog`/`settings` 키로 교체. **진단 결과**는 `BizTypeDiagnosis` + `TaxTool`을 한 화면에 이어 붙였고, **서류**(`docs`)는 렌더 분기를 두지 않아 기존 "준비 중입니다" 안내로 처리된다
- `src/styles.css` (신규) `.mp-tabs`/`.mp-tab`(공고·정책 탭), `.clog*`(상담 기록 목록)

**메모**: 메뉴에서 빠진 화면 중 **AI 추천 공고는 공고·정책 탭으로 이동**했고, **세금 일정**은 상담하기(대시보드) 오른쪽에 이미 달력이 있어 생략했다. **지출관리(BETA)**는 메뉴에서만 빼고 `ExpenseTracker` 컴포넌트는 남겨 뒀다(나중에 되살리기 쉽게). 헤드리스 크롬으로 메뉴를 차례로 눌러 각 화면이 맞게 열리는지 확인했다 — 사업자 정보 / 사업자 유형 진단+세액감면 판정 / 상담 기록 / "서류 화면은 준비 중입니다" / 알림 설정. `npx vite build` 통과.

## 2026-09-12 · 회원가입·공고 상세 모달 모서리 둥글게

**요청**: 회원가입 창과 공고지원 공고를 눌렀을 때 뜨는 창의 모서리를 둥글게.

**원인**: 두 모달 모두 바깥 박스에 `border-radius`와 `overflow-y: auto`가 같이 걸려 있었다. 내용이 길어 스크롤이 생기면 **Windows 기본 스크롤바(화살표가 있는 사각 형태)가 오른쪽 모서리를 덮어** 각져 보였다.

**변경**:
- `src/App.jsx` `GovDetailModal` — 바깥 `.govm__box`는 `overflow: hidden`으로 두고, 내용을 `.govm__scroll` 래퍼로 감싸 **스크롤을 안쪽에서만** 처리하도록 구조 변경(닫기 버튼은 바깥 박스 기준 고정 유지)
- `src/App.jsx` `LoginModal` — 같은 방식으로 변경. 바깥 박스는 `overflow: hidden` + `display: flex`, 내용은 `.lgm__scroll` 래퍼 안에서 스크롤
- `src/styles.css` `.govm__box` — `border-radius` 18 → **22px**, `overflow-y: auto` → `overflow: hidden`, flex 컬럼으로 전환. `LoginModal`의 인라인 `borderRadius`도 18 → 22
- `src/styles.css` (신규) `.govm__scroll` + 모달 스크롤바 스타일 — `.govm__scroll`·`.lgm__scroll`의 스크롤바를 얇고 둥근 형태로(webkit `::-webkit-scrollbar*`, Firefox `scrollbar-width/color`) 지정

**메모**: 스크롤 영역을 안쪽으로 옮기면서 `overscroll-behavior: contain`도 넣어, 모달 안에서 끝까지 스크롤해도 뒤 페이지가 같이 밀리지 않는다. 두 모달 모두 헤드리스 크롬으로 모서리와 스크롤바를 확인했다(확인용으로 빌드 산출물의 애니메이션만 잠시 끄고 촬영, 소스는 그대로). `npx vite build` 통과.

## 2026-09-12 · 로드맵 체크리스트·설명 글씨 크기 조정 (전부 13px)

**요청**: 체크리스트와 그 안의 내용 글씨를 키우고, 이어서 전부 13px로 통일.

**변경**:
- `src/styles.css` base — `.rg2__taskbtn`(항목 제목), `.rg2__tasklabel`("왜 필요한가요?" 소제목), `.rg2__taskwhy`(설명 본문), `.rg2__taskmeta`(기간·준비물 줄)를 **모두 13px로 통일**(기존 13.5 / 11.5 / 12.5 / 11.5px)
- `src/styles.css` `.fp--wide` — 로드맵 화면에 실제 적용되던 압축 모드의 `font-size` 재정의를 **삭제**해 base 13px가 그대로 쓰이게 했다. 줄간격·여백 조정(`line-height`, `margin`, `padding-top`)은 그대로 남겨 압축 배치는 유지

**메모**: 로드맵 화면은 `fp--wide` 압축 모드라 base만 바꾸면 반영되지 않던 구조였는데, 이번에 압축 모드의 글자 크기 재정의를 없애 **크기는 한 곳(base)에서만 관리**되도록 정리했다. 항목이 5개라 커진 뒤에도 한 화면에 들어간다(넘치면 `.rg2__list` 세로 스크롤). 체크리스트 위의 단계 목표 바(`.rg2__goaltext`, 12px)는 요청 범위가 아니라 그대로 뒀다. `npx vite build` 통과.

## 2026-09-12 · 로드맵 펼침 카드에 소제목 추가

**요청**: 체크리스트를 눌렀을 때 아래쪽 "준비물 메모장"처럼 위쪽 본문에도 소제목을 넣기(문구는 직접 정하기).

**변경**:
- `src/App.jsx` `RoadmapGuide` — 펼침 카드 본문 위에 소제목 **"왜 필요한가요?"**(`.rg2__tasklabel`) 추가. 내용이 "이 일을 왜 해야 하는지"를 설명하는 문단이라 그에 맞춰 정했다
- `src/styles.css` (신규) `.rg2__tasklabel` — 아래쪽 부가 정보 라벨(기간·준비물 등)과 시각적 위계를 맞춘 파란 볼드 소제목. `.fp--wide` 압축 오버라이드도 추가

**메모**: `npx vite build` 통과, 헤드리스 크롬으로 확인 완료.

## 2026-09-12 · 로드맵 체크리스트를 창업 7단계 가이드(PDF) 기준으로 교체

**요청**: 첨부한 `창업가이드_7단계_2.pdf` 내용을 참고해 창업 로드맵 체크리스트를 수정하고, 항목을 눌렀을 때 왜 필요한지·목표·시기·대상 등을 정리해서 보여주기. 확정 사항: 단계 목표는 체크리스트 위에 표시, PDF의 개인 맞춤 표현은 일반 창업자용으로 바꿔 쓰기.

**변경**:
- `src/App.jsx` `ROADMAP_TASKS` — PDF의 7단계 구성이 기존 로드맵 단계(A~Z)와 그대로 맞아떨어져, 할 일을 **단계당 4개 → 5개(총 28 → 35개)** 로 PDF 기준 교체. 각 항목은 `{ t: 할 일, why: 왜 필요한지, mk/mv: 단계별 부가 정보 }` 구조로, PDF 표의 부가 열을 그대로 옮겼다(1·3·6단계=기간/시기, 2·4단계=준비물, 5단계=대상, 7단계=목표)
- `src/App.jsx` (신규) `ROADMAP_GOALS` — 단계별 목표와 소요 시간(예: "실제 고객이 느끼는 문제인지 확인하기 · 약 8주")
- `src/App.jsx` `RoadmapGuide` — 체크리스트 위에 단계 목표 바(`.rg2__goal`) 추가. 펼침 카드는 설명 한 줄에서 **왜 필요한지(`.rg2__taskwhy`) + 부가 정보 줄(`.rg2__taskmeta`, 예: "기간 2주")** 구성으로 변경
- `src/styles.css` — `.rg2__goal`/`.rg2__goallabel`/`.rg2__goaltext`/`.rg2__goalspan`, `.rg2__taskwhy`/`.rg2__taskmeta` 추가하고 `.fp--wide` 압축 오버라이드도 함께 정리

**메모**: PDF가 특정 개인(핀테크·Quant 창업 지향, AI 캠프 수강생) 맞춤 문서라 "주식·투자 불편 기록" → "내 분야에서 겪는 불편 기록", "AI 캠프 동료" → "커뮤니티·동료"처럼 **일반 창업자 기준으로 문장을 바꿔** 넣었다. 단계 구성·기간·준비물 같은 뼈대는 PDF 그대로다. 전체 작업 수가 28 → 35개로 늘어 진행률 계산도 자동으로 바뀐다(기존에 체크해 둔 항목은 `단계:인덱스` 키 기준이라 같은 자리의 새 항목에 체크가 남을 수 있다). `npx vite build` 통과, 헤드리스 크롬으로 단계 목표 바와 펼침 카드 확인 완료.

## 2026-09-12 · 로그인 버튼 · 공고 상세 모달 · 로드맵 체크리스트 설명

**요청**: (1) '3분 만에 시작하기' 버튼을 '로그인'으로 변경 (2) 공고지원 AI의 추천 공고를 누르면 상세 정보를 별도 화면으로(간단한 애니메이션) (3) 로드맵 체크리스트 항목을 누르면 할 일 설명 카드가 뜨고, 체크는 빈 네모를 눌렀을 때만. 확정 사항: 공고 상세는 가운데 모달, 설명 카드는 누른 항목 바로 아래, 버튼은 로그인 상태에 따라 표기 변경.

**변경**:
- `src/App.jsx` `Closing`/`Home` — 버튼 문구를 로그인 상태에 따라 `'로그인'` / `'마이페이지 바로가기'`로 표시(`user` prop 추가). 누르면 로그인 모달이 열리는 기존 동작은 그대로다
- `src/App.jsx` (신규) `GOV_DETAILS` — 추천 공고 10건의 상세(요약·신청 자격·지원 내용·제출 서류·신청 방법·유의사항)를 기존 목데이터 톤에 맞춰 새로 작성. `GOV_LISTINGS`에는 공고명·기관·지원금·D-day만 있어 상세 내용이 없었다
- `src/App.jsx` (신규) `GovDetailModal` — 공고 상세 모달. 요약 박스(지원 규모·대상·마감), 적합도 근거 칩(`scoreProgram`의 `why` 재사용), 자격·지원내용·서류·신청방법·유의사항 순으로 보여 준다. 바깥 클릭·ESC·× 버튼으로 닫힌다
- `src/App.jsx` `AnnouncementAnalyzer` — 추천 공고 항목을 버튼(`.az2__recbtn`)으로 바꿔 클릭 시 모달을 연다(`openGov` 상태)
- `src/styles.css` (신규) `.govm*` — 모달 스타일 + 배경 페이드(`govmFade`)·카드 팝업(`govmPop`) 애니메이션. `prefers-reduced-motion`에서는 애니메이션을 끈다
- `src/App.jsx` `ROADMAP_TASKS` — 문자열 배열에서 `{ t: 제목, d: 설명 }` 객체 배열로 변경하고 **28개 작업 설명을 새로 작성**
- `src/App.jsx` `RoadmapGuide` — 체크리스트 구조를 `<label>` 한 덩어리에서 `체크박스 + 제목 버튼`으로 분리. **빈 네모를 눌러야만 체크**되고, 제목을 누르면 `openTask` 상태로 바로 아래에 설명 카드가 펼쳐진다(+/− 표시). 단계를 바꾸면 펼친 항목은 닫힌다
- `src/styles.css` — `.rg2__task label` 계열을 `.rg2__taskrow`/`.rg2__taskbtn`/`.rg2__taskcaret`/`.rg2__taskinfo`로 교체(펼침 애니메이션 `taskInfoIn` 포함), `.fp--wide` 압축 오버라이드도 새 클래스에 맞게 수정

**메모**: 공고 상세와 작업 설명은 실제 공고 원문이 아니라 **화면 확인용으로 새로 작성한 데모 내용**이다(Backend `/policies/{id}`의 실제 공고와는 id 체계가 달라 연결하지 않았다). 자동 클릭으로 동작을 검증했다 — 모달은 정상 표시, 체크리스트는 제목 클릭 시 설명만 펼쳐지고(`info=1`) 네모 클릭 시에만 체크된다(`checked=1`). `npx vite build` 통과.

## 2026-09-12 · 세무 AI 대화방 분리 + 데모·안내 문구 일괄 삭제

**요청**: (1) AI 세무의 "새 대화 시작"을 누르면 현재 대화는 두고 별도의 새 대화방을 만들기 (2) "이 화면에서는 실시간 AI 응답을 사용할 수 없어요…" 같은 안내 문구 전부 삭제. 확정 사항: 대화방 경계는 브라우저에 저장, 안내 문구는 데모·상태 표시까지 전부 삭제(실제 응답 실패 시 오류 문구는 유지).

**변경**:
- `src/App.jsx` (신규) `ROOMS_KEY`/`loadRooms`/`saveRooms`/`rowsToTurns` — Backend `chat_messages`는 category당 한 스레드라 대화방 구분이 없다. "새 대화 시작"을 누른 시점의 **마지막 메시지 id를 경계로 `localStorage`(`changeup:chat-rooms:<category>`)에 저장**하고, 기록을 불러올 때 그 id를 기준으로 방을 나눠 보여준다
- `src/App.jsx` `AiConsult` — `rows`(서버 기록 원본, id 포함)·`bounds`(방 경계)·`roomIdx`(보고 있는 방) 상태 추가. 기록 로딩 시 방을 나눠 마지막(현재) 방을 열고, 기록보다 뒤에 있는 경계는 정리한다. `ask()`는 응답의 `messageId`를 `rows`에 반영해 경계 계산이 계속 맞도록 하고, 지난 방을 보는 중에 질문하면 현재 방으로 옮겨 이어간다(서버는 항상 스레드 끝에 쌓이므로)
- `src/App.jsx` `startNew()` — 기존 동작(기록 삭제)을 걷어내고 **경계만 추가해 빈 방을 새로 여는** 방식으로 교체. 서버 기록은 그대로 보존된다. 이미 비어 있는 새 방이면 중복 생성하지 않는다
- `src/App.jsx` 사이드바 — "내 질문 목록"에서 **대화방 목록**으로 변경(최신 방이 위, 방마다 첫 질문이 제목, 클릭하면 그 방으로 전환). `src/styles.css`에 `.cvx__conv.is-active` 추가. 질문 위치로 스크롤하던 `scrollToTurn`·`data-turn`은 쓰이지 않아 제거
- `src/App.jsx` `clearHistory()` — 기록을 지울 때 방 경계도 함께 초기화
- `src/App.jsx` 안내 문구 삭제 — 대화창의 "이 화면에서는 실시간 AI 응답을 사용할 수 없어요…", 하단 `.ai__note`("데모 화면입니다…"), 헤더 부제(`status`: "LLM 생성 + DB 근거 검색 (RAG)"), 로그인 모달의 "데모 화면입니다 · 소셜 로그인·회원가입 모두…", 푸터 2곳의 "데모용 예시 데이터입니다" 제거. 오류 문구에서 claude.ai·Backend 포트 언급을 빼고 "지금은 답변을 불러올 수 없어요. 잠시 후 다시 시도해 주세요."로 통일

**메모**: 대화방은 **이 브라우저에만 기록되는 경계**라서, 다른 기기·브라우저에서는 구분 없이 한 덩어리로 보인다(Backend에 `conversation_id`가 없어 Frontend만으로는 여기까지가 한계다). 데모 계정으로 실제 질문 전송 → "새 대화 시작" 클릭 → 같은 브라우저로 새로고침까지 자동 재현해 확인했다(대화 2개 유지, 이전 대화 보존, 경계 `[45]` 저장). `npx vite build` 통과.

## 2026-09-11 · 대화 후 대화창 폭이 줄어들던 문제 수정 (세무 AI · 공고지원 AI)

**요청**: 대화창 크기가 유지되지 않는 문제가 아직 남아 있음. 세무 AI와 공고지원 AI에서 발생.

**원인**: `.fp__body`는 `max-width: 1180px; margin: 0 auto`로 가운데 정렬되는데, 부모 `.fp--wide`가 `display: flex; flex-direction: column`이다. **flex 아이템에 가로 `auto` 마진이 있으면 `stretch`가 적용되지 않고 폭이 "내용 크기(shrink-to-fit)"로 결정된다.** 그래서 대화 내용이 바뀔 때마다 `.fp__body` 폭 자체가 달라졌다(실측: 질문을 보내기 전 1180px → 보낸 뒤 615px). 로드맵 화면은 `.fp--wideplus` 규칙에 `width: 100%`가 이미 있어 영향이 없었고, 그게 없는 세무·공고지원만 증상이 나타난 것이다.

**변경**:
- `src/styles.css` `.fp--wide .fp__head-in, .fp--wide .fp__body` — **`width: 100%` 추가**. `max-width: 1180px` + `margin: 0 auto`는 그대로라 가운데 정렬은 유지되고, 폭은 내용과 무관하게 고정된다
- `src/styles.css` `.cvx` — `width: 100%`, `min-width: 0` 추가(그리드가 flex 컨테이너 안에서 쪼그라들지 않게 하는 방어)

**메모**: 앞선 커밋에서 `.ai__body`에 넣은 `min-height: 0`은 **세로** 높이 고정이었고, 이번 건은 **가로** 폭 문제로 원인이 다른 별개 버그였다. 진단은 데모 계정으로 로그인한 상태에서 실제로 질문을 보내는 흐름을 자동 재현하고, 페이지에 측정 스크립트를 넣어 각 요소의 계산된 폭을 찍어 확인했다(수정 후 `.fp__body` 1180px, 대화창 864px로 고정됨). 진단 과정에서 데모 계정의 `tax` 대화 기록에 테스트 질문 2건이 저장됐는데, 개별 삭제 API가 없고 카테고리 전체 삭제만 가능해 지우지 않고 두었다(화면의 "대화 기록 지우기"로 한 번에 정리할 수 있다). `npx vite build` 통과.

## 2026-09-11 · 메인 달력 축소 · 대화창 높이 고정 · 세무 페이지를 상담 AI 레이아웃으로

**요청**: (1) 메인페이지 달력의 일정을 몇 개 지우고 한 페이지에 보이게 (2) AI 세무·공고지원 AI의 대화창이 대화를 해도 크기가 유지되게 (3) AI 세무 어시스턴트 페이지를 전의 상담 AI 레이아웃으로. 확정 사항: 달력은 공고 마감 2건 + 선택 날짜 목록 2건까지, 세무 페이지는 판정서·신고일정 카드를 없애고 대화창만, 사이드바에는 실제 내 질문 목록.

**변경**:
- `src/App.jsx` `pickImportant()` — 기본 `maxPolicy` 5 → **2**, 날짜별로 남기는 세금·내 일정도 3 → 2건으로 축소
- `src/App.jsx` `Calendar` — 선택한 날짜의 일정 목록을 **2건까지만** 표시하고, 더 있으면 "외 N건 · 전체는 마이페이지에서 확인하세요"(`.cal__more`)로 대체. 목록이 길어져 달력이 한 화면을 넘어가던 문제 해결
- `src/styles.css` `.ai__body` — **`min-height: 0` 추가**. flex 규칙상 내용보다 작아지지 않으려 해서 대화가 쌓이면 대화창이 늘어나던 게 원인이었다. 이제 대화가 길어져도 대화창 크기는 그대로고 내부에서만 스크롤된다
- `src/App.jsx` `AiConsult` — `withSidebar` prop 추가. 켜면 `.cvx` 레이아웃(왼쪽 내 질문 목록 + 오른쪽 대화 패널)으로 감싸서 렌더한다. 사이드바는 `turns`에서 내 질문만 뽑아 보여주고, 누르면 대화창의 해당 위치로 스크롤(`data-turn` 속성 + `scrollIntoView`). "+ 새 대화 시작"은 기록이 있으면 기존 `clearHistory()`(서버 삭제), 없으면 화면만 초기화
- `src/App.jsx` `TaxAssistantPage` — `.tax2` 2단 레이아웃(대화창 + 판정서·신고일정 카드)을 걷어내고 `<AiConsult … withSidebar />` 하나로 교체
- `src/styles.css` — 예전 상담 AI용 `.cvx*` 스타일 복원(+ `.cvx__empty`, `.cvx__new:disabled` 추가)하고, `.fp--wide`의 세무 전용 블록을 `.cvx` 전체 높이 레이아웃으로 교체. 더 이상 쓰지 않는 `.tax2*` 스타일은 base·공유 셀렉터까지 모두 삭제

**메모**: 대화창이 늘어나던 원인은 `.ai__body`에 `min-height: 0`이 없던 것과, `.fp--wide .tax2__chat`에 같은 선언이 빠져 있던 것(로드맵·공고지원에는 있었다) 두 가지였는데, 세무 페이지가 `.cvx`로 바뀌면서 후자는 자연히 없어졌다. 세무·공고지원 두 화면 모두 대화 12턴을 넣어 1400×900에서 크기가 유지되고 내부 스크롤만 생기는 것을 헤드리스 크롬으로 확인했다. 세무 페이지의 세액감면 판정서·주요 신고 일정 카드는 요청대로 제거했고, 같은 정보는 마이페이지의 "세액감면 판정"·"세금 일정" 메뉴에 그대로 남아 있다. `npx vite build` 통과.

## 2026-09-11 · AI 대화 예시 제거 · 로드맵 설명 삭제 · 달력 내 일정만 · 회원가입 프로필 입력

**요청**: (1) 모든 AI 대화창의 예시 대화를 지우고 추천 질문을 눌러 시작하게 (2) 로드맵 단계의 작은 설명 글씨 제거 (3) 마이페이지 달력의 일정 제거 (4) 회원가입 시 프로필(업종·지역·연령) 입력 (5) 지역은 17개 시도 드롭다운. 확정 사항: 달력은 내가 등록한 일정만 표시, 스트립은 맨 아래 설명만 제거, 연령은 만 나이 숫자 입력.

**변경**:
- `src/App.jsx` — `TAX_SEED`/`GOV_SEED`/`RG_CHAT_SEED`(미리 채워져 있던 예시 대화) 삭제하고 `AiConsult`의 `seed` prop도 제거. 이제 모든 AI 대화창이 빈 상태로 시작한다
- `src/App.jsx` `AiConsult` 빈 화면 — "어떤 게 궁금하신가요?"(`.ai__hintttl`) + 업종·지역 안내 한 줄(`.ai__hintsub`) + 추천 질문 칩 구성으로 변경. `src/styles.css`에 두 클래스 추가
- `src/App.jsx` — `TAX_CHIPS`/`GOV_CHIPS`/`RG_CHAT_CHIPS` 문구를 LLM이 실제로 답할 수 있는 질문으로 교체(공고문 없이도 답할 수 있게 "이 공고에 지원 가능한지" → "예비창업패키지 지원 자격이 어떻게 되나요?" 식으로)
- `src/App.jsx` `RoadmapGuide` — 단계 스트립에서 설명(`rz__d`, "업종 창·폐업률과 상권 확인" 등) 제거. 아이콘·단계 라벨(창업 전/준비/성장)·단계명만 남김
- `src/App.jsx` `MpCalendar` — 달력에 **내가 등록한 일정(`mine`)만** 표시하도록 필터 추가. 서버 공고 마감·세금 일정은 공고지원 AI 화면에서 확인. 기본 일정을 화면에서만 숨기던 `removed` state와 목데이터 fallback(`CAL_EVENTS`) 제거(대신 빈 객체 `NO_EVENTS`), 삭제는 항상 서버 삭제로 단순화
- `src/App.jsx` `LoginModal` — 회원가입 폼에 **업종**(입력), **사업장 지역**(17개 시도 `REGIONS` 드롭다운), **대표자 연령**(만 나이 숫자) 필드 추가. 가입 직후 `PUT /users/me`(지역·나이)와 `PUT /users/me/business-profile`(업종)로 서버 저장. 로그인 시에는 `GET /users/me`·`GET /users/me/business-profile`로 저장된 프로필을 불러와 반영하고, 값이 없으면 기본값(`DEFAULT_BIZ`/`DEFAULT_REGION`) 사용. 하드코딩돼 있던 `biz: '정보통신업'` / `region: '대전광역시'` 제거. 409(이미 가입된 이메일) 안내 문구도 추가
- `src/api.js` — `apiPut()` 추가. `api.updateMe()`, `api.businessProfile()`, `api.updateBusinessProfile()` 헬퍼 추가

**메모**: 회원가입 프로필 저장도 Backend에 이미 있던 `PUT /users/me`·`PUT /users/me/business-profile`을 쓴 것이라 Frontend 파일만 수정했다. 실제 Backend로 가입 → 지역·나이 저장 → 업종 저장 → 재조회까지 전 과정을 호출해 확인했다(테스트 계정 `testsignup…@demo.com`이 데모 DB에 하나 남아 있다). 회원가입 화면과 로드맵 화면은 헤드리스 크롬으로 확인. 마이페이지 프로필 화면(`ProfileSettings`)의 지역은 아직 자유 입력이라, 회원가입의 드롭다운과 형식을 맞추려면 별도 작업이 필요하다. `npx vite build` 통과.

## 2026-09-11 · 로드맵 단계 UI 교체 · 대화창 2/3 · 페이지 한줄요약 삭제 · 달력 연동

**요청**: (1) 창업 로드맵의 단계별 부분을 홈 화면의 아이콘 스트립 디자인으로 교체 (2) AI 코치 대화창을 2/3로 확대 (3) 각 페이지의 한줄요약 삭제 (4) 공고지원 AI 달력과 마이페이지 달력 연동. 확정 사항: 스트립은 압축 버전, 왼쪽 중복 제목은 제거, 내 일정은 지원사업과 같은 색으로 표시.

**변경**:
- `src/App.jsx` `RoadmapGuide` — 단계 선택 UI를 `.rg2__steps`(알약 버튼 A/B/C…)에서 홈의 `.rz` 아이콘 스트립(`rz--nav` 변형)으로 교체. 클릭 선택·완료 표시는 유지하고, 완료 단계는 아이콘 자리에 체크(`rmDoneIcon()` 신규)를 초록 배경으로 표시. 스트립이 단계명·설명을 보여주므로 왼쪽 패널의 중복 제목(`.rg2__phase`/`.rg2__title`/`.rg2__desc`)은 제거하고 체크리스트만 남김
- `src/styles.css` — `.rg2__steps`/`.rg2__step`/`.rg2__badge`/`.rg2__phase`/`.rg2__title`/`.rg2__desc` 삭제하고 `.rz--nav` 압축 스타일 신규 추가(아이콘 76→46px, `.fp--wide`에서 38px로 한 번 더 축소). `.rz--nav .rz__row`에 `align-items: stretch`를 줘 선택 하이라이트 박스 높이를 단계끼리 맞춤
- `src/styles.css` `.rg2__cols` — `minmax(0,1fr) 520px` → `minmax(0,1fr) minmax(0,2fr)`로 AI 코치 대화창을 전체의 2/3로 확대
- `src/App.jsx` `SubPage` — `meta.lead`와 `<p className="fp__lead">` 제거(로드맵·세무 Assistant·공고지원 AI 3개 페이지의 한줄요약). `src/styles.css`의 `.fp__lead`, `.fp__head--plain .fp__lead`, `.fp--wide .fp__lead`도 삭제
- `src/App.jsx` `eventsByDate()` — **기존 버그 수정**: 서버는 `dueDate`/`eventType`(TAX·POLICY·USER)로 내려주는데 코드는 `e.date`/`e.type`을 읽어서 서버 일정이 **전부 걸러지고 있었다**(달력에 항상 "0건"). `dueDate`/`eventType`을 읽도록 고치고 목데이터 형식(`date`/`type`)도 계속 지원. `id`·`mine` 필드도 함께 넘김
- `src/App.jsx` `pickImportant()` — 내가 등록한 일정(`mine`)은 "가까운 지원사업 5건" 상한과 무관하게 항상 남도록 변경
- `src/App.jsx` `MpCalendar` — 직접 추가한 일정을 React state(`added`)에 담던 것을 **서버 저장**으로 변경: `api.calendarCreate()`로 등록하고 `reload` 카운터로 다시 조회. 삭제는 내 일정이면 `api.calendarDelete(id)`로 서버에서 지우고, 서버가 주는 기본 일정(세금·공고 마감)은 지금처럼 화면에서만 숨김. 실패 시 `.cal__err` 문구 표시(비로그인은 "로그인이 필요해요")
- `src/api.js` — `api.calendarCreate(body)`(`POST /calendar`), `api.calendarDelete(eventId)`(`DELETE /calendar/{id}`) 추가
- `src/styles.css` (신규) `.cal__err`

**메모**: 달력 연동은 Backend에 이미 있던 `POST /calendar`·`DELETE /calendar/{id}`와, 내 개인 일정까지 함께 돌려주는 `GET /calendar`를 쓴 것이라 Frontend 파일만 수정했다. 공고지원 AI 화면의 달력도 같은 `GET /calendar`를 쓰므로, 마이페이지에서 등록하면 그쪽에도 그대로 보인다. **로그인 필요** — 비로그인 상태에서는 API가 401이라 지금처럼 목데이터가 보이고 일정 추가가 안 된다. 실제 Backend로 등록→조회→삭제를 모두 호출해 확인했고(서버 일정 427건 → 17개 날짜로 매핑, 수정 전에는 0건), 공고지원 화면은 "중요 일정만" 정책대로 세금·내 일정 전부 + 가까운 공고 마감 5건만 점으로 표시된다(전체는 마이페이지). 로드맵 화면은 헤드리스 크롬으로 확인. `npx vite build` 통과.

## 2026-09-11 · AI 상담 메뉴·기능 삭제 + 마이페이지 카드 재배치 + 로드맵 대화창 확대

**요청**: (1) 상담 AI 메뉴 및 기능 삭제 (2) 창업 로드맵의 AI 대화창 폭 키우기. 추가로 마이페이지 "최근 AI 상담" 카드는 카드째 삭제하고, 창업 로드맵 카드를 전체 폭으로 늘린 뒤 세무 AI 카드를 아랫줄로 내려 공고지원 AI와 좌우 폭을 맞추기로 확정.

**변경**:
- `src/App.jsx` `NAV_MENU` — `{key:'ai', label:'AI 상담'}` 제거 (헤더 ☰ 드로어 메뉴에서 사라짐)
- `src/App.jsx` `MP_MENU` — `{key:'ai', label:'AI 상담'}` 제거 (마이페이지 사이드바에서 사라짐)
- `src/App.jsx` — `AiConsultPage` 컴포넌트와 `AI_HISTORY`(가짜 대화목록 사이드바 데이터) 삭제, 마이페이지의 `menu === 'ai'` 분기 삭제, 미사용 상수 `PAGES.ai` 삭제
- `src/App.jsx` `SubPage` — `meta.ai`, `slim` 조건의 `pageKey === 'ai'`, `fp--wideplus` 조건의 `pageKey === 'ai'`, `{pageKey === 'ai' && <AiConsultPage/>}` 렌더 분기 모두 삭제. `handleNavigate` 주석도 `'roadmap' | 'tax' | 'gov'`로 수정
- `src/App.jsx` 마이페이지 대시보드 — "최근 AI 상담" 카드와 `MP_CONSULTS` 상수 삭제. 창업 로드맵 카드에 `mp-card--wide` 클래스 추가
- `src/styles.css` — `.cvx*` 스타일 전체 삭제(`.cvx`/`__side`/`__new`/`__list`/`__group`/`__conv`/`__main`, `.fp--wide .cvx*` 블록, `.cvx__main .ai` 공유 셀렉터 포함). AiConsultPage 전용이라 삭제 후 참조처 없음
- `src/styles.css` (신규) `.mp-card--wide { grid-column: 1 / -1; }` — 로드맵 카드가 윗줄을 가로로 다 쓰고, 아랫줄에 세무 AI·공고지원 AI가 같은 폭으로 들어감
- `src/styles.css` `.rg2__cols` — `grid-template-columns: minmax(0,1fr) 400px` → **520px**로 로드맵 AI 대화창 확대 (왼쪽 할 일 목록은 그만큼 좁아짐)

**메모**: 공용 `AiConsult` 채팅 컴포넌트 자체는 그대로 유지 — 로드맵·세무·공고지원 화면에서 계속 사용한다. 어제 넣은 대화기록 복원·삭제 기능은 `AiConsultPage`가 사라지면서 이제 **AI 세무 Assistant 화면에만** 남는다(그 화면의 `category="tax"`는 그대로). 홈 화면의 "대화하듯 물어보면" 마케팅 데모 섹션은 별개 기능이라 유지. `npx vite build` 통과, 헤드리스 크롬으로 로드맵 화면(대화창 확대)과 마이페이지 대시보드(로드맵 전체폭 + 아랫줄 2칸) 모두 확인 완료.

## 2026-09-11 · AI 대화 기록 복원 · 삭제 (Frontend 담당분, CHAT_MEMORY_FRONTEND.md)

**요청**: 로그인 사용자가 새로고침·재접속해도 Backend DB(`chat_messages`)에 저장된 이전 질문·답변을 이어서 볼 수 있게 복원하고, 기록 삭제 UI를 추가. (팀 작업 분배 문서 `CHAT_MEMORY_OVERVIEW.md`/`CHAT_MEMORY_FRONTEND.md`의 Frontend 담당분)

**충돌 체크 결과 (진행 전 확인)**:
- Backend `GET/DELETE /chat/messages` 두 엔드포인트가 이미 구현돼 있고(`Backend/api/chat.py`), 응답 행 모양(`id/user_id/category/question/answer/created_at`, `GET`은 `{messages:[...]}`로 감쌈)도 문서 설명과 정확히 일치 — 충돌 없음.
- **로그인 시 `user` 객체에 `id`가 아예 없었음** — `LoginModal.authenticate()`가 `{name, email, biz, region}`만 채워서 `setUser`에 넘기고 있어, 문서가 요구하는 "`user?.id`가 있으면 기록 조회" 조건이 실제로는 한 번도 참이 될 수 없는 상태였음. Frontend 파일(App.jsx)만으로 고칠 수 있는 범위라 `id: r.userId`를 채워 넣어 해결.
- **카테고리 기본값 충돌 위험**: 문서대로 `category` prop 기본값을 `'tax'`로 하면, 로드맵·공고지원 AI 페이지의 `AiConsult`(둘 다 category를 안 넘김)도 로그인 시 자동으로 "세무 Assistant"의 대화 기록을 불러와 버려 화면 간 대화가 섞임. Backend가 받는 카테고리도 `tax/expense/saving/policy` 네 개뿐이라 로드맵용 카테고리 자체가 없음. → 기록 조회/삭제 로직은 **`category`를 명시적으로 넘긴 화면에서만** 동작하도록 설계해 해결(문서의 "다른 화면은 향후 지정 가능하게"라는 범위 제한과도 일치). 결과적으로 이번엔 문서가 지정한 대로 Tax Assistant·일반 AI 상담 두 화면에만 `category="tax"`를 명시했고, 로드맵·공고지원 AI는 기존 seed 동작 그대로 유지.
- Backend `POST /chat/messages` 응답에는 문서가 언급한 `ragUsable`/`status`/`guardrailReason`이 실제로 없음(`messageId/answer/grounded/llmUsed/needsConfirmation`만 있음) — 기존 Frontend 코드도 이 필드들을 쓰고 있지 않아 "보존" 대상 자체가 없는 상태. 실제로 있는 필드 기준으로 구현했고 별도 조치는 하지 않음.
- 위 세 가지 모두 Frontend 파일 범위 안에서 해결 가능해 별도 확인 없이 그대로 진행함.

**변경**:
- `src/api.js` — `apiDelete(path, opt)` 추가(기존 `apiGet`/`apiPost`와 동일하게 인증 헤더·timeout·AbortSignal 처리). `api.chatHistory(category, opt)`(`GET /chat/messages?category=`), `api.clearChat(category, opt)`(`DELETE /chat/messages?category=`) 추가.
- `src/App.jsx` `LoginModal.authenticate()` — `onSuccess()`에 `id: r.userId` 추가(백엔드 로그인 응답의 `userId`를 `user.id`로 연결).
- `src/App.jsx` `AiConsult` — `category` prop 추가(기본값 없음). 로그인(`user.id` 존재) + `category` 지정 시: mount/`user`/`category` 변경마다 `api.chatHistory(category)`로 기록을 불러와 시간순(`question`→`assistant`/`answer`) `turns`로 세팅, 실패 시 seed로 되돌리지 않고 오류 문구만 표시. 조회 중에는 "이전 대화를 불러오는 중…" 표시. 기존 하드코딩됐던 `api.chat({..., category:'tax'})`를 `category: category || 'tax'`로 교체(미지정 화면은 기존과 동일하게 항상 'tax' 전송, 동작 변화 없음). 기록이 있고 로그인 상태일 때만 "대화 기록 지우기" 버튼(`window.confirm` 확인 후 `api.clearChat` 호출, 성공 시 `turns`/`stream`/오류 초기화, 실패 시 화면은 그대로 두고 오류만 표시) 노출. unmount/의존성 변경 시 `alive` 플래그로 오래된 응답 무시.
- `src/App.jsx` `TaxAssistantPage`, `AiConsultPage` — 각 `<AiConsult>` 호출에 `category="tax"` 추가(문서가 지정한 두 화면). `RoadmapGuide`, `AnnouncementAnalyzer`(공고지원 AI)의 `<AiConsult>` 호출은 그대로 둠 — category 미지정이라 여전히 seed만 쓰고 새 기록 기능과 무관.
- `src/styles.css` — `.ai__histrow`(대화 기록 지우기 버튼을 담는 얇은 상단 바) 추가.

**메모**: `npx vite build` 통과. 실행 중인 로컬 Docker Backend(`localhost:8000`)에 데모 계정으로 직접 로그인해 `GET /chat/messages?category=tax`를 호출해 실제 저장된 23건의 기록과 응답 모양을 확인했고, 프론트의 파싱 로직과 정확히 일치함을 확인. Vite 개발 서버에서 로그인 상태·토큰을 임시로 주입해 "이전 대화를 불러오는 중…" 로딩 상태까지는 화면에서 직접 확인했으나, 그 다음 헤드리스 크롬 스크린샷이 안전장치에 의해 추가로 막혀 기록이 채워진 최종 화면은 스크린샷으로는 확인하지 못함 — 대신 동일 토큰으로 실제 Backend 응답을 직접 대조해 파싱·표시 로직이 맞는지 확인했다. 브라우저에서 직접 눌러 최종 확인해 보는 걸 권장.

## 2026-09-11 · 공고지원 AI — 추천 공고 D-day 표시 + 달력 카드 밖 넘침 수정

**요청**: 추천 공고에서 %(적합도 점수) 대신 D-day(남은 일수)로 표시하고, 아래 달력이 카드 밖으로 넘치는 문제를 카드 안에 들어오도록 수정.

**변경**:
- `src/App.jsx` `AnnouncementAnalyzer` — 추천 공고 리스트의 굵은 배지를 `{score}%` → `{g.dday >= 100 ? '상시' : `D-${g.dday}`}`로 교체, 중복이라 메타 줄의 D-day는 제거하고 기관명만 남김
- `src/styles.css` `.az2__recscore` — 색상을 매칭 점수용 초록(`#16a34a`)에서 마감일 강조용 빨강(`var(--red)`, 기존 D-day 표기 관례와 통일)으로 변경
- `src/App.jsx` `Calendar` — `compact` prop 추가: 켜면 하단 "선택한 날짜 일정 상세"(`.cal__events`) 블록을 숨겨서, 좁은 카드 안에서 월 달력 그리드가 넘치지 않고 남은 세로 공간을 온전히 쓸 수 있게 함. 홈 화면 `<Calendar />` 호출부는 prop을 안 넘겨 기존 동작 그대로 유지
- `src/App.jsx` `AnnouncementAnalyzer` — `<Calendar />` → `<Calendar compact />`로 변경
- `src/styles.css` `.fp--wide .cal__grid` — `flex:1; min-height:0; grid-template-rows:auto; grid-auto-rows:minmax(0,1fr);`로 요일 헤더 행은 내용 높이만, 날짜 행들은 남은 높이를 균등 분배하도록 변경. `.fp--wide .cal__day`에 `aspect-ratio:auto` 추가(기존 `1/1` 정사각형 강제 때문에 카드 높이가 좁아져도 셀 높이가 줄지 않아 넘쳤던 게 근본 원인). `.fp--wide .az2__cols > .cal`에 `overflow:hidden` 추가(안전장치)

**메모**: 넘침의 근본 원인은 `.cal__day`의 `aspect-ratio: 1/1`이 셀 높이를 카드 너비 기준으로 고정해버려서, 압축 레이아웃에서 카드 세로 폭을 줄여도 달력 그리드 자체 높이가 줄지 않고 카드 밖으로 삐져나온 것. `npx vite build` 통과, 헤드리스 크롬 스크린샷으로 D-day 배지와 달력이 카드 안에 온전히 들어오는 것 확인 완료.

## 2026-09-11 · 공고지원 AI — 좌측 카드 구성을 "추천 공고 + 달력"으로 개편

**요청**: 위 카드는 내 정보와 맞는 추천 공고, 아래 카드는 달력을 넣고, 두 카드 크기를 동일하게 해서 오른쪽 AI 대화창과 높이를 맞춰달라는 요청.

**변경**:
- `src/App.jsx` `AnnouncementAnalyzer` — 기존 "내 조건 적합도"(적합도%·rows·비슷한 공고·최근 확인) + "필요 서류 체크리스트" 카드 구성을 걷어내고, 위 카드는 `GOV_LISTINGS`를 기존 `scoreProgram`으로 채점한 상위 4건을 보여주는 **추천 공고** 리스트로, 아래 카드는 홈 화면에서 쓰던 **`Calendar()`** 컴포넌트(세금 신고·지원사업 마감일 통합 달력, 백엔드 `/calendar` 연동 + 로컬 목데이터 폴백)를 그대로 재사용하도록 교체
- `src/App.jsx` `AiConsult` — 이전에 추가했던 `draftRequest`/`chatDraft`/`inputRef` (체크리스트 클릭 → 챗 입력창 자동 채움) 로직 제거: 체크리스트 카드 자체가 없어져 더 이상 쓰이는 곳이 없어 죽은 코드가 되므로 정리. `ANNC_DOCS`/`ANNC_STATUS`/`ANNC_CHECKS_KEY`/`loadStoredChecks`/`ANNC_HISTORY_KEY`/`loadAnncHistory`도 함께 제거
- `src/styles.css` — `.az2__score`/`.az2__bar`/`.az2__rows`/`.az2__dday`/`.az2__subhd`/`.az2__similar`/`.az2__simlist*`/`.az2__history*`/`.az2__docs*`/`.az2__st*`/`.az2__draft*`(기존 두 카드 전용 스타일, base + `.fp--wide` 압축 오버라이드 모두) 삭제하고 `.az2__reclist`/`.az2__recmain`/`.az2__rectitle`/`.az2__recmeta`/`.az2__recscore`(추천 공고 리스트) 신규 추가
- `src/styles.css` `.fp--wide .az2__cols` — `grid-template-rows: auto 1fr` → **`1fr 1fr`**로 바꿔 두 카드 높이를 절반씩 동일하게 고정(전체 높이는 기존과 동일하게 오른쪽 `.az2__chat`과 맞춤). `.fp--wide .az2__cols > .cal`에 카드와 맞춘 라운드·패딩, `.cal__events`에 `flex:1`+스크롤을 추가해 달력이 절반 높이 안에서 넘치지 않게 처리

**메모**: 달력은 실제 오늘 날짜 기준으로 그려지고 목데이터(`CAL_EVENTS`)는 2025년 10~11월에 고정돼 있어, 지금 시점(2026-09)에는 "이번 달 주요 일정 0건"으로 보일 수 있음 — 이는 홈 화면 달력도 동일하게 겪는 기존 한계라 이번 변경으로 새로 생긴 문제는 아님. 추천 공고는 데모 프로필(`user || {biz:'정보통신업', region:'대전광역시'}`) 기준 계산. `npx vite build` 통과, 헤드리스 크롬 스크린샷으로 두 카드 높이가 동일하게 나뉘고 전체가 오른쪽 대화창과 맞는 것 확인 완료.

## 2026-09-11 · 공고지원 AI — 비슷한 공고 미리보기 + 최근 확인 이력

**요청**: "내 조건 적합도" 카드에 (2) 비슷한 조건의 다른 공고 3개 미리보기, (4) 최근 분석 이력(로컬 저장) 추가.

**변경**:
- `src/App.jsx` (신규) `ANNC_HISTORY_KEY`/`loadAnncHistory` — 최근 확인한 공고 이력을 `localStorage`(`changeup:annc-history`)에 저장/복원 (최신순, 중복 제거, 최대 5개)
- `src/App.jsx` `AnnouncementAnalyzer` — `history` state 추가. `GOV_LISTINGS`를 기존 `scoreProgram`으로 채점해 상위 3건을 `similar`로 계산, 카드 진입 시 1회 `history`에 병합·저장하는 `useEffect` 추가
- `src/App.jsx` `AnnouncementAnalyzer` JSX — `.az2__rows` 아래에 "비슷한 조건의 다른 공고" 리스트(`.az2__similar`/`.az2__simlist`, 공고명·기관·D-day·적합도 점수)와 "최근 확인" 태그 리스트(`.az2__history`/`.az2__histags`) 추가
- `src/styles.css` — `.az2__subhd`, `.az2__similar`, `.az2__simlist`, `.az2__simtitle`, `.az2__simmeta`, `.az2__simscore`, `.az2__history`, `.az2__histags`, `.az2__histag` 신규 스타일 추가(기존 `.az2__rows` 블록 뒤), `.fp--wide` 압축 모드용 대응 오버라이드도 함께 추가해 한 화면 안에 다 보이는 레이아웃 유지

**메모**: "비슷한 공고"는 실제로는 데모 프로필(`user || {biz:'정보통신업', region:'대전광역시'}`) 기준 정적 계산이라 로그인 사용자 조건에 따라 달라짐. 이력은 브라우저(같은 기기·같은 브라우저) 로컬 저장이라 다른 기기에서는 안 보임. `npx vite build` 통과, 헤드리스 크롬 스크린샷으로 레이아웃 확인 완료.

## 2026-09-11 · 공고지원 AI — 체크 상태 저장 + 서류 클릭 시 챗 질문 자동입력

**요청**: 공고지원 AI 페이지 "필요 서류 체크리스트" 카드에 (5) 체크 상태 localStorage 저장, (7) "AI 초안 가능" 항목 클릭 시 오른쪽 공고 상담 입력창에 관련 질문 자동으로 채우기 적용.

**변경**:
- `src/App.jsx` `ANNC_DOCS` — 사업계획서 항목에 `question: '사업계획서 초안 방향 잡아줘'` 필드 추가(AI 초안 가능 항목 전용)
- `src/App.jsx` (신규) `ANNC_CHECKS_KEY`/`loadStoredChecks` — 체크 상태를 `localStorage`(`changeup:annc-checks`)에 저장/복원
- `src/App.jsx` `AnnouncementAnalyzer` — `checks` 초기값을 `loadStoredChecks()`로, 변경될 때마다 `localStorage`에 저장하는 `useEffect` 추가. `chatDraft` state 신규 — `question`이 있는 서류는 상태 뱃지를 버튼(`az2__st--btn`)으로 바꿔 클릭 시 `chatDraft` 세팅
- `src/App.jsx` `AiConsult` — `draftRequest` prop 추가: 값이 오면 입력창 `draft`를 채우고 포커스(`inputRef`). 다른 페이지의 `AiConsult` 호출부는 prop을 안 넘기니 영향 없음
- `src/styles.css` `.az2__st--btn` — 버튼 리셋 + hover 시 밑줄(클릭 가능함을 표시)

**메모**: 체크 상태는 브라우저(같은 기기·같은 브라우저)에 로컬 저장이라 다른 기기에서는 안 보임 — 서버 저장은 별도 작업. `npx vite build` 통과.
## 2026-09-11 · develop 병합 때 사라진 Backend 연동 로직 복구

**요청**: feat/frontend 를 develop 에 병합해도 되는지 확인. 병합 가능성과 예상 문제점 점검.

**원인**: `a900489` (Merge origin/develop into feat/frontend) 에서 `App.jsx` 충돌을 파일 통째로 ours 로 덮었음. 당시 충돌 블록은 10개(약 450줄)였는데 병합 결과가 `a556579` 와 바이트 단위로 동일함. `-X ours` 도 `-s ours` 도 아님 — 같은 병합에서 Backend 24개 파일은 develop 것이 정상 반영됐음. 그래서 **충돌도 안 났고 git 이 이미 자동 병합한 코드까지** 같이 버려졌고, 충돌 마커로 보인 적이 없어 아무도 인지하지 못했음. 되돌아간 항목은 전부 `Docs/reports/INTEGRATION_ISSUES_0910.md` 에 해결로 기록된 결함임.

**변경** (`src/App.jsx`):
- `AiConsult` — `api.chatSources(rag.messageId)` 로 근거 조문을 따로 받아옴. `ChatMessageResponse` 에 `sources` 가 없어 `rag.sources` 는 항상 빈 배열이었음
- `AiConsult` — `ragUsable`(`llmUsed` 이고 `status` 가 `error`·`integration_unavailable` 아님) 이면 Backend LLM 답변을 먼저 씀. 뷰어 `window.claude` 는 그다음임. 순서가 설계와 반대로 뒤집혀 있었음
- `AiConsult` — `api.chat` 의 401 을 `needLogin` 으로 구분해 로그인 안내와 로그인 버튼을 띄움. 이전에는 catch 가 통째로 삼켜 "Backend 미실행" 으로 안내했음
- `AiConsult` — `needsConfirmation` 배지("확인 필요 · 근거가 충분하지 않은 답변이에요") 배선
- `TaxTool` — `legalBasis` 를 문자열로 렌더하고 `reasons` 배열을 함께 보여줌. 배열로 다뤄 `.map()` 에서 TypeError 로 화면이 죽던 결함 8 재발분임. 스키마에 없는 `srv.rate` 비교 문구 제거
- `App` — 마운트 시 `api.me()` 로 실제 세션을 확인함. localStorage 의 user 는 화면 유지용일 뿐이라 토큰이 만료돼도 로그인 상태로 보였음
- `App`, `MyPage` — 로그아웃 시 `api.logout()` 호출. 이전에는 화면만 로그아웃되고 토큰이 localStorage 에 남았음
- `SubPage` → `TaxAssistantPage`·`AnnouncementAnalyzer`·`AiConsultPage`·`AiConsult` 로 `onRequireLogin` 배선

**메모**: `src/api.js` 는 손대지 않음 — 필요한 함수가 모두 이미 export 되어 있고 develop 과 동일함. `npx vite build` 통과. **공고문 붙여넣기 요약(`api.summarizeAnnouncement`)은 복구하지 않음** — feat/frontend 가 `AnnouncementAnalyzer` 를 원문 입력 textarea 가 있는 화면에서 정적 적합도 카드로 재설계해 호출할 UI 자체가 없음. 화면 설계 결정이 필요해 별건으로 둠.

**재발 방지**: App.jsx 충돌은 파일 단위 `--ours`/`--theirs` 로 넘기지 않음. `git checkout --conflict=diff3` 로 base 를 함께 보고, 병합 직후 `git diff HEAD^2 HEAD -- Frontend/src/App.jsx` 로 상대 쪽에서 무엇을 버렸는지 확인함.

## 2026-09-11 · AI 응답 안 되던 문제 — 로그인이 Backend 토큰을 안 받아오고 있었음

**요청**: 홈페이지에서 AI 응답이 안 됨. Docker로 해결.

**원인**: Docker 백엔드(`:8000`)는 정상이었음(`/auth/login`, `/chat/messages` 모두 정상). 문제는 프론트 — 이전 병합 충돌 해결 때 `App.jsx`를 "ours"로 택하면서, `LoginModal`이 실제 `POST /auth/login`을 호출하지 않고 화면에만 `onSuccess`로 로그인 처리를 해왔음. 그래서 `localStorage`에 토큰이 없어 `POST /chat/messages`(인증 필요) 요청마다 401 → "AI 응답을 사용할 수 없어요" 메시지로 이어짐.

**변경** (`src/App.jsx` `LoginModal`):
- 기본 이메일/비밀번호를 `demo@demo.com` / `demo123`(Backend 시드 데모 계정)로 변경
- `submit` — 로그인 모드는 `api.login(email, pw)`, 회원가입 모드는 `api.signup(email, pw, name)` 실제 호출 → 성공 시 받은 토큰이 `api.js`의 `setToken`으로 `localStorage`에 저장됨. 실패 시 401→"이메일/비밀번호 확인", 그 외→"Backend(:8000) 연결 확인" 안내. `busy` 상태로 버튼 비활성화("확인 중…")
- 소셜 로그인(카카오·네이버) 버튼 — 실제 대응 API가 없어 데모 계정으로 실제 로그인해 토큰만 받아오도록 변경(`socialDemo`)

**메모**: Docker 스택 자체는 손대지 않음(이미 정상). `npx vite build` 통과. 확인 방법: 로그인 모달 열기 → 미리 채워진 데모 계정으로 로그인 → 세무 AI 페이지에서 질문 전송 → 이전처럼 에러 대신 답변(또는 RAG 안내) 표시.

## 2026-09-10 · 로드맵·AI 상담 폭 1300px → 1200px

(요청에 따라 `.fp--wideplus` max-width 를 최종 `1200px` 로 조정)

## 2026-09-10 · 로드맵·AI 상담 폭 1300px (구)

**요청**: 창업 로드맵·AI 상담 페이지 폭 `1180 → 1300px`, 가운데 정렬.

**변경**:
- `src/App.jsx` `SubPage` — `pageKey==='roadmap' || pageKey==='ai'` 이면 `.fp` 에 `fp--wideplus`
- `src/styles.css` `.fp--wideplus .fp__head-in`/`.fp__body` — `max-width: 1600 → 1300px` (`width:100%; margin:0 auto` 유지)

**메모**: 세무·공고는 1180px 유지. `npx vite build` 통과.

## 2026-09-10 · 로드맵·AI 상담 폭을 세무 AI(1180px)로 통일

**요청**: 창업 로드맵·AI 상담 페이지 폭을 세무 AI 페이지와 동일하게.

**변경**:
- `src/App.jsx` `SubPage` — `pageKey==='ai' → fp--full`, `pageKey==='roadmap' → fp--wideplus` 클래스 부여 제거. 4개 슬림 서브페이지 모두 `fp--wide`(max-width 1180px) 로 통일
- `.fp--full` / `.fp--wideplus` CSS 는 미사용으로 남겨둠

**메모**: `npx vite build` 통과.

## 2026-09-10 · 창업 로드맵 기능 영역 폭 확대 (1180 → 1600)

**요청**: 로드맵 페이지 기능부분 폭을 (표시한) 빨간 선까지.

**변경**:
- `src/App.jsx` `SubPage` — `pageKey==='roadmap'` 이면 `.fp` 에 `fp--wideplus`
- `src/styles.css` `.fp--wideplus .fp__head-in`/`.fp__body` — `max-width: 1180 → 1600px`, `width: 100%; margin: 0 auto`(플렉스 자식이 `margin:0 auto` 로 콘텐츠 폭에 수축하던 문제 해결 → 1600px 가운데 정렬로 확실히 확대). `.fp--full` 도 `width: 100%` 추가
- 헤더·스텝 탭·진행률·체크리스트·대화창이 모두 넓어진 영역을 사용 (1920 화면에서 좌우 약 160px 여백)

**메모**: 다른 서브페이지(세무/공고)는 1180px 유지, AI 상담은 전체 폭. `npx vite build` 통과.

## 2026-09-10 · 말풍선 테두리 + AI 상담 전체 폭 레이아웃

**요청**: (1) AI 대화 말풍선에 테두리 (2) AI 상담 페이지를 이미지처럼(전체 폭).

**변경**:
- `src/styles.css` `.msg--ai` — 배경 `--ground → --surface-solid`, `border: 1px solid --line-strong`. `.msg--user` — `border: 1px solid --blue-deep`. 전 대화(홈 데모·로드맵·세무·공고·AI상담)에 적용. 로드맵 전용 `.msg--ai` 오버라이드도 `--line-strong` 로 통일
- `src/App.jsx` `SubPage` — `pageKey==='ai'` 일 때 `.fp` 에 `fp--full` 클래스
- `src/styles.css` `.fp--full .fp__head-in`/`.fp__body` — `max-width: none; margin: 0`(플렉스 자식의 `margin:0 auto` 로 인한 가운데 정렬 제거 → 전체 폭). `.fp--wide .cvx__side` 오른쪽 구분선 제거

**메모**: AI 상담만 전체 폭, 나머지 서브페이지는 1180px 유지. `npx vite build` 통과.

## 2026-09-10 · 창업 로드맵 대화 패널 — 회색 패널 + 흰 말풍선 (첨부 이미지)

**요청**: 로드맵 페이지를 첨부 이미지처럼.

**변경** (`src/styles.css` `.fp--wide .rg2__chat` 계열):
- `.rg2__chat .ai` 배경 `--surface-solid → --ground`(회색 패널)
- `.rg2__chat .ai__bar` / `.ai__foot` / `.ai__foot input` 은 흰색으로 고정
- `.rg2__chat .msg--ai` 배경 `--ground → --surface-solid` + `border 1px --line`(회색 패널 위 흰 말풍선으로 대비)

**메모**: 레이아웃(가로 스텝 탭 + 체크리스트 | 대화창)은 그대로. 대화창 색 처리만 이미지에 맞춤. `npx vite build` 통과.

## 2026-09-10 · AI 상담 클린 패널 · 홈으로 버튼 제거 · 홈 축소 · 메뉴 글자 축소

**요청 4건**:
1. AI 상담을 이미지처럼(카드 테두리 없는 전체 패널)
2. "홈으로" 버튼 전부 제거
3. 메인(홈)을 지금에서 다시 90%(→ 누적 81%)
4. 메뉴 글씨크기 현재의 80%로

**변경**:
- `src/styles.css` `.fp--wide .cvx__main` — `border`/`border-radius`/`box-shadow` 제거(테두리 없는 패널). `.cvx__main .ai__body` 회색 틴트 제거(흰 배경 유지). `.cvx__side` 오른쪽 구분선만
- `src/App.jsx` `SubPage` — 슬림 헤더 `← 홈으로`(`.rmhead__back`) 제거, 햄버거만. 비-슬림 `fp__head` 의 `← 홈으로`(`.fp__back`) 렌더 제거. (로고 클릭 홈 이동은 유지)
- `src/styles.css` `.home-scale` `zoom: 0.9 → 0.81`
- `src/styles.css` `.drawer__link` font `clamp(20,5vw,27) → clamp(16,4vw,21.5)`, padding `20 → 15`, gap `16 → 13`. `.drawer__num` `12 → 10`, `.drawer__desc` `11.5 → 9.5`

**메모**: `.rmhead__back`/`.fp__back`/`.rmhead__actions` CSS는 미사용이지만 남겨둠. `npx vite build` 통과.

## 2026-09-10 · 뒤로가기/메뉴 버튼 · 홈 90% · 공고지원 좌우 반전 · 한 화면

**요청 6건**:
1. 서브페이지 뒤로가기 버튼 복구(눌리게)
2. 메인(홈) 90% 크기
3. 공고지원 AI: 대화창 오른쪽 / 카드 왼쪽 (높이 맞춤)
4. 모든 페이지 한 화면(레이아웃 유지)
5. 마이페이지에도 메뉴(햄버거) 버튼
6. 홈 AI 데모 대화창이 늘어나지 않게

**변경**:
- `src/App.jsx` `SubPage` 슬림 헤더 — 햄버거 옆에 `← 홈으로`(`.rmhead__back`) 버튼 복구 (`.rmhead__actions` 그룹)
- `src/App.jsx` `App` 홈 분기 — `Nav`+`Home`+`footer` 를 `<div className="home-scale">` 로 감쌈 → `zoom: 0.9`
- `src/App.jsx` `App` — `MyPage` 에 `onNavigate`/`onLoginClick` 전달
- `src/App.jsx` `MyPage` — `mp-head` 우측에 햄버거 + `<MenuDrawer>` 추가(`siteMenuOpen` state)
- `src/App.jsx` `AnnouncementAnalyzer` — JSX 순서 반전: `.az2__cols`(카드) 먼저, `.az2__chat` 나중
- `src/styles.css`
  - `.chatbox` `min-height:440` + `.chatbox__body { max-height:420 }` → `.chatbox { height: 520px }` **고정**(메시지 쌓여도 안 늘어남)
  - `.rmhead__actions`, `.rmhead__back`(패딩), `.mp-head__actions`, `.home-scale { zoom: 0.9 }`
  - `.fp--wide .az2` → `display:grid; grid-template-columns: 348px minmax(0,1fr)`(카드|챗), `align-items:stretch`. `.az2__cols` 는 세로 1열 + `grid-template-rows: auto 1fr`(체크리스트가 남는 높이 채워 챗과 바닥 맞춤). 체크리스트 카드는 flex column + `.az2__docs { flex:1; overflow-y:auto; align-content:start }`
  - `.fp--wide .rg2__chat { display:flex; flex-direction:column }` 추가 → 로드맵 챗도 높이 꽉 채움
  - `@media (max-height: 680px → 600px)` — fit 모드를 더 낮은 높이까지 유지

**메모**: 1366×740 기준 홈 포함 전 페이지 한 화면. `zoom` 은 크로미움/파폭126+/사파리 지원(데모 허용). `npx vite build` 통과.

## 2026-09-10 · 서브페이지 대화 패널 재구성 (첨부 이미지 기준)

**요청**: 이미지처럼 + (1) 세무 AI 오른쪽 카드 축소·대화창 확대·좌우 높이 맞춤 (2) 공고지원 AI 대화창 확대·아래 카드 축소 (3) AI 상담 마지막 이미지처럼(전체 높이 대화 패널).

**변경**:
- `src/App.jsx` — 세무/공고 페이지의 `<h2 class="tax2__h/az2__h">` → `<div class="chatpanel__hd">`(대화 박스 헤더바). AiConsult props는 그대로
- `src/styles.css`
  - `.chatpanel__hd` + `.tax2__chat`/`.az2__chat`/`.cvx__main` 을 **테두리 컨테이너**로, 내부 `.ai` 는 테두리 제거하고 `flex:1` 로 꽉 채움, `.ai__body` 는 연한 회색(`--ground`) 틴트 — 3개 페이지 대화 박스 통일
  - `.fp--wide .fp__body` = flex column, 자식이 `flex:1` 로 남는 높이 채움 → 4개 페이지 모두 대화창이 세로를 꽉 채우고 입력창이 바닥 고정
  - 세무: `.tax2 { align-items: stretch }` + `.tax2__side { grid-template-rows: auto 1fr }` → 오른쪽 카드가 대화창과 바닥 정렬. 카드 패딩/폰트/`.tax2__rate`(24→22)/행 간격 추가 축소
  - 공고: `.az2` flex column, `.az2__chat` `flex:1`(대화창 최대), `.az2__cols` `flex:none`(카드는 압축 유지). `.az2__draft` 배경 `#14181f` → `var(--blue)`(파란 버튼, 이미지 기준)
  - AI 상담: `.cvx { align-items: stretch }`, `.cvx__side` 오른쪽 구분선, `.cvx__main` 테두리 패널 + 대화창 전체 높이

**메모**: 1366×768/720/1600×900 모두 한 화면. 680px 미만은 기존대로 문서 스크롤 폴백. `npx vite build` 통과.

## 2026-09-10 · 서브페이지 한 화면 맞춤 — 페이지별 재조정

**요청**: (1) 로드맵은 기존 레이아웃 + 한 화면 (2) 세무 AI는 대화창·카드 모두 축소 (3) 공고지원 AI는 대화창 키우고 아래 카드 축소 (4) AI 상담은 기존 레이아웃 + 한 화면.

**변경** (`src/styles.css` 뷰포트-맞춤 블록 재작성):
- 이전엔 `.ai` 를 `flex:1` 로 세로를 꽉 채워 배치가 어색했음 → **페이지별 고정 높이 + `align-items: start`(자연 높이)** 로 전환. `.fp__body` 는 `overflow: hidden → overflow-y: auto`(안전망)
- 로드맵: 레이아웃 그대로, 챗 `min(52vh, 400px)`, 스텝/진행률/체크박스 간격만 축소
- 세무 AI: `.tax2` `align-items: start`, `.tax2__chat` flex 해제, 챗 `min(46vh, 360px)`, 판정서·신고일정 카드 패딩·`.tax2__rate`(30→24)·행 간격 축소
- 공고지원 AI: 챗 `clamp(220px, 44vh, 380px)`(상대적으로 크게), 아래 `.az2__cols` 카드는 패딩·폰트·바 높이·행 간격·버튼 패딩 전부 축소. `meta.gov.lead` 도 한 줄로 단축(`src/App.jsx`)
- AI 상담: `.cvx` `align-items: start`, 챗 `min(56vh, 440px)`
- `@media (max-height: 640px → 680px)` 로 상향 — 680px 미만 화면은 일반 문서 스크롤로 폴백

**메모**: 1366×720(노트북 100% 유효 높이)에서 4개 페이지 모두 스크롤 없이 한 화면. `npx vite build` 통과.

## 2026-09-10 · 홈 AI 어시스턴트 데모 — "세액 감면도 되나요?" 답변까지 재생 유지

**요청**: 메인페이지 세금 어시스턴트 애니메이션에서 "세액 감면도 되나요?" 질문의 답변까지 나오게.

**원인**: `ChatDemo` 의 `useInView(..., true)`(repeat) 때문에 섹션이 화면에서 벗어나면 `shown` 이 0으로 리셋됨 → 스크롤로 지나가면 앞 1~2개 말풍선만 보이고 세액감면 답변(`CHAT[3]`)까지 못 감.

**변경** (`src/App.jsx` `ChatDemo`):
- `useInView({ threshold: 0.3 }, true)` → `useInView({ threshold: 0.25 })` (one-shot). 한 번 보이면 `inView` 가 계속 true (실패 대비 2.8s 후 자동 시작)
- `if (!inView) { setShown(0); ... }` 리셋 블록 제거 → `if (!inView) return;` 만. 스크롤 아웃해도 진행 상태 유지
- 재생 간격 소폭 단축(950/560 → 900/520ms)으로 6개 말풍선(질문·답변 3쌍) 약 4.3초에 완주

**메모**: `CHAT` 스크립트는 그대로(세액감면 답변 다음에 부가세 신고 일정 등록 시연이 이어짐 — "신고 일정 등록" 태그 시연 유지). `npx vite build` 통과.

## 2026-09-10 · 고정 다크모드 버튼 + 앱 화면 한 화면에 담기

**요청**:
1. 다크모드 버튼을 어느 페이지에서나 보이도록 고정
2. 100% 배율에서 전체 페이지가 한 화면에 들어오도록

**변경**:
- `src/App.jsx` (신규) `FloatingThemeToggle` — `position: fixed` 우하단 원형 버튼(`.theme-fab`). App 의 3개 return(홈/서브페이지/마이페이지) 모두에 렌더 → 항상 보임. `Nav` 안에 있던 `◐` 아이콘 버튼은 중복이라 제거(홈에서 두 개 겹침 방지)
- `src/styles.css` — `.theme-fab` 신규
- `src/App.jsx` `SubPage` — 슬림 페이지를 `<div className="slim-shell">`(100vh flex column, overflow hidden)로 감싸고 그 안에 `rmhead`(flex:none) + `.fp--wide`(flex:1). 기존엔 `.fp--wide` 가 `100vh` 라 위의 `rmhead` 높이만큼 아래가 잘렸음
- `src/styles.css` (파일 끝에 블록 추가) — 앱 화면 뷰포트 맞춤:
  - `.slim-shell` 100vh flex, `.fp--wide` flex:1 + overflow hidden, `.fp__head--plain`/`.fp__title`/`.fp__lead`/`.fp__body` 패딩·폰트 축소
  - `.fp__body` = flex column, 자식 페이지가 `flex:1; min-height:0` 로 남는 높이 채움
  - `.rg2`/`.tax2`/`.az2`/`.cvx` 를 flex/그리드로 높이 채우고 `.ai` 는 `flex:1` 로 늘려 입력창까지 보이게. 목록(`.rg2__list`, `.cvx__side`, `.tax2__side`)은 내부 스크롤
  - `.mp` = `height:100vh; overflow:hidden`, `.mp-main` 내부 스크롤, 대시보드 카드·달력 셀 살짝 압축
  - `@media (max-height: 640px)` 에서는 다시 문서 스크롤 허용(내용 잘림 방지)
- `src/App.jsx` `SubPage` — 슬림 페이지에서 하단 `footer.foot` 숨김(이전 커밋)

**메모**: 홈 랜딩은 스크롤 스토리라 대상 제외. 1366×768(노트북 100%) 기준 5개 앱 화면(마이페이지/로드맵/세무/공고/AI상담) 문서 스크롤 없이 한 화면에 들어옴. 그보다 세로가 짧으면 자동으로 일반 스크롤로 폴백. `npx vite build` 통과.

## 2026-09-10 · 세무·공고지원 카드 = 진행률 대신 대화 요약

**요청**: 세무·공고지원 카드에 진행률 말고 해당 AI와 나눈 대화를 간단히 정리한 내용 표시.

**변경**:
- `src/App.jsx` — `MP_TAX_SUMMARY`(3줄), `MP_GOV_SUMMARY`(3줄) 상수 추가(각 AI 페이지 시드 대화 기준 요약)
- `src/App.jsx` `MyPage` — "세무 AI Assistant" / "공고지원 AI" 카드에서 `mp-pct`+`mp-bar`+`mp-cite` 제거하고 "최근 상담 요약" 라벨 + `.mp-rows--recap` 목록으로 교체(공고 카드는 라벨에 `저장 N건` 유지). 카드 전체 클릭 이동은 그대로
- `src/App.jsx` `MyPage` — 안 쓰게 된 `taxNext`/`govMatchCount` 계산 제거
- `src/styles.css` — `.mp-recap`, `.mp-rows--recap`(줄바꿈되는 요약 줄)

**메모**: 요약 3줄은 데모 고정(TAX_SEED/GOV_SEED 대화 내용 기준). 실제 대화에서 자동 생성하려면 chat turns 를 App 레벨로 올려야 함. 로드맵 카드는 진행률 유지. `npx vite build` 통과.

## 2026-09-10 · 마이페이지 대시보드 카드를 AI 현황 카드로 통일

**요청**: "다가오는 일정" 상자 자체를 세무 AI로 바꾸고 내용도 세무 AI 진행 상황을 표시. "추천 정책"도 공고지원 AI 현황으로.

**변경**:
- `src/App.jsx` `MyPage` — "다가오는 일정" 카드 → **"세무 AI Assistant"** 카드: 큰 `100%`(세액감면 판정) + 진행바 + `세액감면 판정 · 조특법 제6조 · 5년` / `다음 신고 · {taxNext.title} · {taxNext.when}`(= MP_SCHEDULE 의 `mark` 항목). 클릭 시 세무 페이지 (기존 `.mp-card--action` 유지)
- `src/App.jsx` `MyPage` — "추천 정책 Top 3" 카드 → **"공고지원 AI"** 카드: 큰 `92%`(내 조건 적합도) + 진행바 + `추천 {GOV_LISTINGS.length}건 · 저장 {saved.size}건`(저장 수는 "AI 추천 공고" 탭과 실시간 공유). 클릭 시 공고지원 AI 페이지
- `src/App.jsx` `MyPage` — `taxNext`, `govMatchCount` 계산 추가
- `src/styles.css` — `.mp-cite` 에 `gap`, `.mp-cite + .mp-cite { margin-top }`(2줄 인용), 값 오른쪽 정렬

**메모**: 로드맵/세무/공고 3개 카드가 이제 같은 "큰 % + 진행바 + 인용" 레이아웃. `MP_RECO` 는 미사용이 됐지만 남겨둠. 세무 카드의 100%/조특법 값은 데모 고정(세무 페이지 판정서와 동일). `npx vite build` 통과.

## 2026-09-10 · 마이페이지 "다가오는 일정"·"추천 정책" 카드를 통째로 클릭 이동

**요청**: 창업 로드맵 카드처럼 "다가오는 일정"·"추천 정책" 상자를 누르면 각각 세무 AI / 공고지원 AI 페이지로 이동.

**변경**:
- `src/App.jsx` `MyPage` — 두 카드를 로드맵 카드와 동일 패턴으로: `mp-card mp-card--action` + `role="button"` + `tabIndex={0}` + `onClick`(다가오는 일정 → `onOpenTax`, 추천 정책 → `onOpenGov`) + Enter/Space `onKeyDown`. 카드 안에 있던 개별 행 `<button>` 제거(중첩 인터랙티브 방지) → 행은 일반 텍스트로. 헤더 우측은 클릭 큐 문구(`<span className="mp-card__link">` "세무 AI Assistant ›" / "공고지원 AI ›")
- `src/styles.css` — `.mp-card--action:hover .mp-card__link { text-decoration: underline }` 추가(카드 hover 시 큐 강조)

**메모**: 직전 커밋에서 넣었던 헤더 링크버튼/행버튼 방식을 카드 전체 클릭으로 교체. `npx vite build` 통과.

## 2026-09-10 · 마이페이지 카드 연동 + AI 추천 공고 + 로그인 유지

**요청**:
1. "다가오는 일정" 상자를 세무 AI Assistant와 연동
2. "추천 정책" 상자를 공고지원 AI와 연동
3. 지원정책의 "탐색"을 공고지원 AI가 맞는 공고를 저장해주는 메뉴로
4. 로그인하면 로그아웃 누를 때까지 유지

**변경**:
- `src/App.jsx` `App` — `localStorage('changeup:user')` 로 로그인 세션 유지: `useState(loadStoredUser)` + `useEffect([user])`(있으면 저장, 없으면 삭제). 로그아웃(`setUser(null)`)하면 자동으로 지워짐
- `src/App.jsx` `App` — `MyPage` 에 `onOpenTax`/`onOpenGov`(= `handleNavigate('tax'|'gov')`) 전달
- `src/App.jsx` `MyPage` "다가오는 일정" 카드 — 헤더에 "세무 AI에게 묻기 ›" 링크, 각 행을 버튼으로 만들어 클릭 시 세무 페이지로
- `src/App.jsx` `MyPage` "추천 정책 Top 3" 카드 — 헤더에 "공고지원 AI ›" 링크, 행 클릭 → 공고지원 AI 페이지(기존 `setMenu('explore')` → `onOpenGov`)
- `src/App.jsx` `MP_MENU` — `탐색` → **`AI 추천 공고`** (key `explore` 유지)
- `src/App.jsx` (신규) `MatchedGov` — `scoreProgram(user)` 로 `GOV_LISTINGS` 를 적합도순 정렬, 매칭 이유 칩 + "☆ 저장하기"(=`saved` set 토글, "저장한 정책" 과 공유). `menu==='explore'` 렌더를 `GovExplorer` → `MatchedGov` 로 교체
- `src/App.jsx` `SavedPolicies` — 안내문 "탐색" → "AI 추천 공고"
- `src/styles.css` — `.mp-card__link`, `.mg*`

**메모**: `GovExplorer`/`GOV_REGIONS`/`GOV_TYPES` 는 이제 미사용이지만 남겨둠. 로그인 유지는 localStorage 라 같은 브라우저에서만 유효(시크릿창/다른 브라우저는 재로그인). `npx vite build` 통과.

## 2026-09-10 · 마이페이지 ↔ AI 상담 / 창업 로드맵 연동

**요청**:
1. 마이페이지의 AI 상담을 메뉴의 AI 상담과 이어지게
2. 마이페이지 "세액감면 판정 요약" 카드를 창업 로드맵 진행률로 연동

**변경**:
- `src/App.jsx` `App` — `roadmapDone` state 신설(로드맵 페이지 ↔ 마이페이지 공유). `MyPage` 에 `roadmapDone` + `onOpenRoadmap={() => handleNavigate('roadmap')}`, `SubPage` 에 `roadmapDone`/`setRoadmapDone` 전달
- `src/App.jsx` `RoadmapGuide({ user })` → `({ user, done, setDone })` — 내부 `useState(done)` 제거하고 props로 받음. `setDone` 은 상위 setter(함수형 업데이트 그대로 동작)
- `src/App.jsx` `MyPage` — 시그니처에 `roadmapDone`/`onOpenRoadmap`. "세액감면 판정 요약" 카드를 **"창업 로드맵 진행률"** 카드로 교체: `rmPct`(완료 작업/28), `rmStepsDone / 7단계`, 현재 단계(첫 미완료 단계) 표시. 카드 클릭/Enter 로 로드맵 페이지 이동(`.mp-card--action`)
- `src/App.jsx` `MyPage` — `menu === 'ai'` 렌더를 `<AiConsult user>` → `<AiConsultPage user>` 로 (메뉴의 AI 상담과 동일한 화면: 대화 기록 사이드바 + 같은 rules/seed/chips). "최근 AI 상담" 카드 항목도 이 탭으로 연결됨
- `src/styles.css` — `.mp-card--action`(hover/focus)

**메모**: 진행 상태는 세션 메모리(App state)만 — 새로고침하면 초기화. 로드맵에서 체크한 게 마이페이지 카드에 실시간 반영됨(반대는 로드맵에서만 편집). AI 상담은 컴포넌트 공유라 화면·설정이 같아지는 수준이고, 두 위치의 대화 내용이 실시간으로 합쳐지진 않음(그건 turns 상위 이관 필요). `npx vite build` 통과.

## 2026-09-10 · AI 상담 페이지 — 대화 기록 사이드바 추가

**요청**: "해당 페이지를 이미지처럼 바꿔줘" (왼쪽에 대화 기록 리스트, 오른쪽에 챗).

**변경**:
- `src/App.jsx` (신규) `AiConsultPage` — `.cvx` 2열: 왼쪽 `.cvx__side`("+ 새 대화 시작" + "오늘"/"지난 7일" 그룹별 대화 목록, 활성 항목 하이라이트), 오른쪽 `.cvx__main`(`AiConsult`, 짧은 칩 3개 전달)
- `src/App.jsx` (신규) `AI_HISTORY` 상수 (대화 목록 데모 데이터)
- `src/App.jsx` `SubPage` — `pageKey==='ai'` 를 `slim` 에 추가(간결 헤더+메뉴버튼), 렌더를 `<AiConsult/>` → `<AiConsultPage/>` 로
- `src/styles.css` — `.cvx*` 신규 (860px 이하 세로 스택)

**메모**: 대화 목록은 데모 고정값이고 클릭 시 하이라이트만 바뀜(실제 대화 전환 없음). "+ 새 대화 시작" 도 현재 동작 없는 데모 버튼. `npx vite build` 통과.

## 2026-09-10 · 후속 수정 3건 (슬림 헤더 메뉴버튼 / 세무 높이 / 공고지원 챗)

**요청**:
1. 메뉴에서 들어간 서브페이지 우측 상단을 "홈으로" → 메뉴(햄버거) 버튼으로
2. AI 세무 Assistant: 챗 상자와 옆 상자 높이 맞추기
3. "공고문 AI 분석" 메뉴명을 "공고지원 AI"로, 공고문 입력부를 AI 챗봇으로

**변경**:
- `src/App.jsx` `SubPage` — `slim` 헤더의 `.rmhead__back`("← 홈으로") 제거, `.hamburger` 버튼 + `<MenuDrawer>` 추가(`menuOpen` state). 로고 클릭은 여전히 홈 이동
- `src/styles.css` `.tax2` — `align-items: start → stretch`, `.tax2__chat` 를 flex column + `.ai { flex:1; min-height:min(66vh,560px) }`, `.tax2__side` 에 `grid-template-rows: auto 1fr`(신고 일정 카드가 남는 높이 채움) → 좌우 상자 하단 정렬
- `src/App.jsx` `NAV_MENU` gov 항목 label `공고문 AI 분석 → 공고지원 AI`, desc 수정
- `src/App.jsx` `AnnouncementAnalyzer` — 공고문 textarea/예시/`analyze`/`result`/`cell` 등 전부 제거하고 `.az2__chat`(= `AiConsult`, `GOV_RULES`/`GOV_SEED`/`GOV_CHIPS`) 로 교체. 아래 적합도/체크리스트 카드는 유지(값은 데모 고정). `user` prop 추가
- `src/App.jsx` — `GOV_RULES`/`GOV_SEED`/`GOV_CHIPS` 신규
- `src/styles.css` — `.az2__h`, `.az2__chat .ai` 높이(min(60vh,460px))

**메모**: `ANNC_SAMPLES`/`ANNC_FALLBACK`, `.az2__paste`·`.az2__result` CSS, `.rmhead__back` CSS 는 이제 미사용이지만 남겨둠(추후 정리). 공고지원 챗의 "지원서 초안 작성하기" 검정 버튼은 현재 동작 없는 데모 버튼. `npx vite build` 통과.

## 2026-09-10 · 공고문 AI 분석 페이지 → "공고지원 AI" 로 재구성

**요청**: "해당 페이지 이미지처럼 바꿔줘" (붙여넣기 카드 + [내 조건 적합도 | 필요 서류 체크리스트] 2열).

**변경**:
- `src/App.jsx` `SubPage` meta.gov — 제목 `지원사업 공고문 AI 분석 → 공고지원 AI`, 리드 문구 교체. `slim` 대상에 `gov` 추가(간결 헤더 + `fp__head--plain`)
- `src/App.jsx` `AnnouncementAnalyzer` 반환부 교체 — `.tool az` → `.az2`:
  - `.az2__paste` 붙여넣기 카드 (예시 칩 + textarea + "AI로 분석 시작")
  - `.az2__cols` 2열:
    - 왼쪽 `.az2__card` = 내 조건 적합도 92%(초록) + 진행바 + 안내문 + 지원대상/지원내용/접수기간(D-43 빨강). 지원대상·지원내용은 분석 결과(`result`) 있으면 그 값, 없으면 데모 기본값
    - 오른쪽 `.az2__card` = 필요 서류 체크리스트(체크 토글) + 상태 뱃지(준비 필요=빨강 / AI 초안 가능=파랑 / 준비 완료=초록) + 검정 버튼 "지원서 초안 작성하기"(→ `analyze` 실행)
  - 분석을 실제로 돌리면 기존 `구조화 결과`(`az__grid`)가 아래에 그대로 표시됨(AI 기능 유지)
- `src/App.jsx` — `ANNC_DOCS` / `ANNC_STATUS` 상수 추가, `checks` state 추가
- `src/styles.css` — `.az2*` 신규 (860px 이하 세로 스택). 적합도 진행바 초록 그라디언트, 검정 버튼

**메모**: 적합도 92%와 체크리스트 항목/상태는 데모 고정값(이미지 기준). 기존 `.az*` CSS와 `ANNC_FALLBACK`·`cell()` 은 결과 표시에 계속 쓰여서 유지. `npx vite build` 통과.

## 2026-09-10 · AI 세무 Assistant 페이지 — 이미지대로 2열, 단 대화창을 왼쪽에

**요청**: "해당 페이지를 이미지처럼 바꾸는데 대화창이 왼쪽으로 배치해줘" (이미지는 왼쪽 판정서·일정 / 오른쪽 챗이지만, 챗을 왼쪽으로).

**변경**:
- `src/App.jsx` `TaxAssistantPage` 교체 — 세로 스택(챗 + `TaxTool`) → `.tax2` 2열:
  - 왼쪽(넓게) `.tax2__chat` = "AI와 대화하기" 제목 + `AiConsult`
  - 오른쪽(340px) `.tax2__side` = "세액감면 판정서" 요약 카드 + "주요 신고 일정" 카드(`TAX_SCHEDULE` 앞 4건)
  - 판정서는 인터랙티브 세그먼트 없이 읽기 전용 요약(업종 지역/대표자 연령/감면대상 업종/예상 감면율 100%/조특법 제6조 근거)
- `src/App.jsx` `AiConsult` — `noHeader` prop 추가: true면 내부 `.ai__bar`(ON 아바타 + 제목) 전체를 숨김. 세무 페이지 챗에 `compact noHeader` 적용
- `src/App.jsx` `SubPage` — 간결 헤더/`fp__head--plain` 적용 대상을 `roadmap` → `roadmap` + `tax` 로 확장(`slim` 플래그)
- `src/styles.css` — `.tax2*` 신규 (2열 그리드, 900px 이하 세로 스택). 오른쪽 카드 스타일

**메모**: `TaxTool`(인터랙티브 세액감면 계산기, 약 130줄)은 이제 이 페이지에서 안 쓰지만 삭제하지 않고 남겨둠([[로드맵 재구성]]과 동일한 판단 — 추후 정리). 되돌리려면 `TaxAssistantPage` 를 이전 버전(챗 `large` + `<TaxTool/>` 스택)으로 복구하고 `SubPage` 의 `slim` 을 `pageKey==='roadmap'` 으로 되돌리면 됨. `npx vite build` 통과.

## 2026-09-10 · 창업 로드맵 페이지 — 첨부 이미지대로 단순화 재구성

**요청**: "이미지처럼 해당 페이지 바꿔줘" (가로 단계 탭 + 왼쪽 체크리스트 + 오른쪽 AI 코치, 헤더는 브랜드 + "홈으로"만).

**변경**:
- `src/App.jsx` `RoadmapGuide` 전면 교체 — 기존 [전체 진행률 카드 + 맞춤 지원사업 리포트 + 세로 단계 nav + 단계별 지원사업 + "이 단계 AI에게 물어보기"] 제거하고, `.rg2` 구조로:
  - `.rg2__steps` 가로 단계 탭(A~Z, 활성=파란 원, 완료=✓)
  - `.rg2__prog` 한 줄 진행률 ("전체 진행률 N% · x / 28 작업 완료")
  - `.rg2__cols` = 왼쪽 `.rg2__list`(단계 pill + 제목 + 설명 + 체크리스트), 오른쪽 `.rg2__chat`(`AiConsult`)
  - 관련 state/함수 제거: `sampleFn`/`aiText`/`aiBusy`/`sumText`/`askAi`/`askSummary`/`stepProgs`/`matches`/`completedSteps` 등
- `src/App.jsx` `AiConsult` — `compact` prop 추가: true면 헤더의 상태줄(`{status}`)과 하단 면책문구(`.ai__note`) 숨김. `.ai--compact` 클래스 부여
- `src/App.jsx` `RG_CHAT_SEED` — 답변 말풍선을 이미지의 짧은 문장으로 교체
- `src/App.jsx` `SubPage` — `pageKey==='roadmap'` 이면 `<Nav>`(햄버거·테마 토글) 대신 `.rmhead`(브랜드 + "← 홈으로")를 쓰고, `.fp__head` 에 `fp__head--plain`(회색 배경/보더 제거, 자체 back 버튼 숨김)
- `src/styles.css` — `.rmhead*`, `.fp__head--plain`, `.rg2*` 신규. `.fp--wide` max-width `1340 → 1180`

**메모**: 기존 `.rgx*` / `.rg__*` CSS(약 200줄)와 `progById`/`ddayLabel`/`scoreProgram`/`ROADMAP_PROGRAMS` 상수는 이제 로드맵에서 안 쓰지만, 다른 곳 영향 최소화를 위해 삭제하지 않고 남겨둠(추후 정리 대상). `npx vite build` 통과, JS 번들 약 6KB 감소.

## 2026-09-10 · 마이페이지 대시보드 — 첨부 이미지에 맞춰 레이아웃/크기 정리

**요청**: "이미지처럼 마이페이지를 바꿔주고 레이아웃 크기를 맞춰줘" (토스증권 톤의 대시보드 스크린샷 첨부).

**변경**:
- `src/styles.css` `.mp-dash` — 캘린더 열 `340px → 320px`, gap `18 → 20`, `max-width 1180 → 1200`
- `src/styles.css` (신규) `.mp-dash .cal__day { aspect-ratio: auto; height: 40px }` — 마이페이지 안에서 캘린더 셀이 열 너비 따라 거대해지던 문제 고정(항상 40px)
- `src/styles.css` 반응형 재구성 — 기존 `@media (max-width:1180px)` 단일 스택을 둘로 분리: `≤1080px` 은 카드만 1열(`.mp-dash .mp-grid`)로 접고 캘린더는 오른쪽 유지, `≤860px` 에서만 캘린더를 아래로 내리되 `max-width:420px` 로 폭 제한
- `src/styles.css` `.mp-rows li` 패딩 `11px → 13px`(이미지의 넉넉한 행 간격), `.mp-consult` 색 `--ink-faint → --ink-soft`(최근 AI 상담 글자가 너무 흐렸음)
- `src/styles.css` (신규) `.mp-dot`(파란 점), `.mp-rowval--urgent`(빨간 글자)
- `src/App.jsx` `MP_SCHEDULE` — `{ ..., urgent: true }`(예비창업패키지 마감 = D-43 빨강), `{ ..., mark: true }`(부가세 2기 예정신고 앞 파란 점)
- `src/App.jsx` `MyPage` "다가오는 일정" 렌더 — `s.mark` 이면 `.mp-dot`, `s.urgent` 이면 값에 `.mp-rowval--urgent`

**추가 (같은 날)**: "카드 4개 블록 높이 = 오른쪽 캘린더 높이" 요청 반영
- `src/styles.css` `.mp-dash` — `align-items: start → stretch` (카드 열이 캘린더 높이만큼 늘어남)
- `src/styles.css` `.mp-dash .mp-grid` — `grid-auto-rows: 1fr; min-height: 0` 추가 (카드 두 줄이 캘린더 높이를 균등 분할)
- `src/styles.css` `@media (max-width:1080px)` — `.mp-dash{ align-items:start }`, `.mp-grid{ grid-auto-rows:auto }` 로 되돌려 1열 스택 시 카드가 늘어나지 않게
- `.mp-dash .cal { align-self:start }` 는 유지 → 캘린더는 콘텐츠 높이 그대로, 이 높이가 기준

**메모**: 3열(카드 2×2 + 캘린더) 레이아웃이 1080px 까지 유지됨. 카드 내용은 위 정렬이라 카드가 늘어나면 아래쪽 여백이 생김(의도). 되돌리려면 위 셀렉터들을 원복하고 `.mp-dash` 브레이크포인트를 `@media (max-width:1180px){ .mp-dash{ grid-template-columns:1fr } }` 하나로 되돌리면 됨. `npx vite build` 통과 확인.

## 2026-09-09 · 창업 로드맵 페이지에 AI 코치 사이드 챗 추가

**요청**: 기존 로드맵 가이드를 왼쪽으로 밀고, 오른쪽에 AI 챗봇을 레이아웃 맞춰 배치.

**변경**:
- `src/App.jsx` `RoadmapGuide` — 반환부를 2열(`.rgx`)로 감쌈: 왼쪽 `.rgx__main`(기존 진행률·리포트·단계 가이드), 오른쪽 `.rgx__chat`(`AiConsult`)
- `RG_CHAT_RULES` / `RG_CHAT_SEED` / `RG_CHAT_CHIPS` 추가 — 7단계(A~Z) 맥락을 프롬프트에 주입한 "로드맵 AI 코치"
- `src/App.jsx` `SubPage` — `pageKey==='roadmap'` 이면 `.fp` 에 `fp--wide` 부여
- `src/styles.css` — `.fp--wide`(본문 max-width 1340), `.rgx`(`minmax(0,1fr) 380px`), `.rgx__chat`(sticky top 84), 1100px 이하 세로 스택

**메모**: 오른쪽 챗은 Backend `/api/chat`(RAG) + `window.claude.use('sample')` 를 함께 씀(기존 `AiConsult` 그대로). 근거 문서 링크도 표시됨.

## 2026-09-07 · 백엔드 연동 준비 레이어 추가 (api.js)

**요청**: 팀원들이 올린 파일들(Backend/LLM/DB)을 브랜치로 받아왔는데 내가 만든 프론트엔드랑 연결할 수 있나? → "프론트만 연결 준비(안전)" 선택.

**변경**:
- `src/api.js` (신규) — `apiGet(path)` fetch 래퍼 + `useApi(path, fallback, map)` 훅. 백엔드 없으면 실패 → `fallback`(목데이터) 사용, `/api/*` 나오면 자동 전환. BASE = `import.meta.env.VITE_API_BASE_URL || '/api'`
- `src/App.jsx` — `import { useApi } from './api.js'` 추가
- `src/App.jsx` `DeadlinePanel` — `DEADLINES` 상수 대신 `useApi('/announcements?deadline=soon&limit=4', DEADLINES, map)` 사용 (연동 예시 1곳)

**메모**: 지금은 Backend가 스텁(`print("Hello from backend!")`)이라 실제로는 목데이터가 보임. DB(Postgres)에는 데이터 적재 완료(policies 2,907 / announcements 2,045 등). Backend가 `API_SPEC.md` 대로 구현되면 `DeadlinePanel` 은 코드 수정 없이 붙고, 나머지 데이터 지점(METRICS, CAL_EVENTS, 마이페이지 카드, 챗봇)은 `api.js` 상단 주석의 목록대로 `useApi` 로 교체하면 됨.

## 2026-09-08 · 홈 캘린더 — 중요 일정만 표시

**요청**: 메인페이지 일정관리 캘린더가 전체 다 보이지 않고 몇 가지 중요 일정만.

**변경**: `src/App.jsx`
- `pickImportant(map, maxPolicy=5)` 추가 — 세금 신고일은 전부(날짜당 최대 2건), 지원사업 마감은 **가까운 순 5건**만 남김
- 홈 `Calendar` — API 응답을 `pickImportant` 로 걸러서 표시 (`MpCalendar`·`세금 일정` 메뉴는 전체 유지)
- `cal__sub` 문구 → "이번 달 주요 일정 N건 · 전체 일정은 마이페이지에서"

## 2026-09-08 · Backend·DB·LLM 실연동 (목데이터 → 실제 API)

**요청**: 백엔드·DB·프론트·LLM 폴더 내용을 유기적으로 연결하고 홈페이지에서 구동되게.

**변경** (Frontend 쪽):
- `src/api.js` 전면 개편 — `apiGet`/`apiPost` + 엔드포인트 헬퍼 `api.{stats,announcements,policies,recommendations,calendar,taxCheck,taxDocuments,chat}` + `useApi`(실패 시 목데이터 폴백, 빈 배열도 폴백 처리)
- `Hero` — `GET /api/stats` 로 **모집 중 공고 수(860)·정책 2,907·세법 4,459** 실데이터 표시 + `● 실시간 DB 연동 중 / ○ 데모 데이터` 배지
- `DeadlinePanel` — `GET /api/announcements` 로 실제 마감 임박 공고, D-day 자동 계산
- `Calendar`(홈) / `MpCalendar`(마이페이지) — `GET /api/calendar?year&month` 로 세금 신고일 + 정책 마감일 통합. 오늘 날짜 기준으로 시작, 월 이동 시 재조회. 직접 추가/삭제는 로컬 오버레이로 유지
- `GovExplorer` — `GET /api/announcements?limit=60` 실데이터 + 지역/유형 필터, `● DB 실시간` 표시
- `TaxTool` — `POST /api/tax/tax-reduction/check` 서버 Rule Engine 병행 호출 → **DB 근거 조문 링크** 표시
- `AiConsult` — 질문 시 `POST /api/chat/messages` 로 근거 문서 검색 → 그 근거를 컨텍스트로 넣어 생성(RAG). 답변 아래 **근거 문서 목록·원문 링크**(`.msg-src`). Backend만 있어도 사용 가능하도록 입력창 활성화 조건 완화
- `styles.css` — `.msg-src` 추가

**함께 만든 것** (Frontend 외):
- `Backend/` — FastAPI 앱(`main.py`), `core/{config,db}`, `services/{policy,calendar,tax,stats,chat}_service`, `api/routes.py`, `schemas/models.py`. 지역 법정동 코드 → 시·도명 정규화 포함
- `LLM/src/serving/app.py` — 근거 기반 생성(LangChain) 또는 추출 요약
- `run_all.bat`, 루트 `README.md`(구성도·실행법·API 표·제약)

**메모**: `tax_documents.content` 평균 53자(수집 스크립트가 조문 제목만 저장) → 검색은 정확하나 답변 근거 본문이 부족. `DB/scripts/collect_tax_law.py` 보완 필요.

## 2026-09-08 · 로드맵 단계별 지원사업 + 완료 리포트 / AI 대화창 확대

**요청**: (1) 창업 로드맵에서 단계별 지원사업을 알려주고, 로드맵 완료 시 그 내용 기준으로 맞춤 지원사업을 정리해 보여주기. (2) AI 세무 Assistant 대화창을 더 크게, 글씨도 잘 보이게.

**변경**:
- `src/App.jsx` — `ROADMAP_PROGRAMS`(단계 A~Z ↔ `GOV_LISTINGS` id 매핑), `progById`, `ddayLabel`, `scoreProgram`(프로필 기반 매칭 점수+이유) 추가
- `src/App.jsx` `RoadmapGuide`
  - 각 단계 패널 하단에 **"이 단계에서 활용할 수 있는 지원사업"** 목록(기관·금액·지역·D-day)
  - 진행률 아래 **완료 리포트** — 100% 미만은 잠금 안내(남은 개수), 100% 달성 시 `추천 지원사업 Top 5(매칭 점수·이유 태그)` + `세무 체크포인트` + `다음 액션` 표시
  - **AI로 실행 계획 정리받기** 버튼 — 완료 단계·매칭 사업을 프롬프트에 넣어 `sample`로 신청 우선순위/준비서류/주의사항 생성(스트리밍·중지 지원)
- `src/App.jsx` `AiConsult` — `large` prop 추가 → `.ai--lg` 클래스 / `TaxAssistantPage` 에 `large` 적용, `tool` maxWidth 900 → 980
- `src/styles.css` — `.ai--lg`(높이 `min(74vh,760px)`, 말풍선 15px, 입력·칩·헤더 확대), 기본 `.msg` 13 → **14px**, `.rg__progs/.rg__prog/.rg__report/.rg__match/.rg__why/.rg__next` 등 추가

**메모**: 매칭 점수는 지역 일치·창업 단계 대상·마감 임박·자금 유형 가중치의 룰 기반(데모). 실서비스는 `/api/policies/recommendations` 로 교체.

## 2026-09-08 · 마이페이지 캘린더 추가 + 사이드바 메뉴 기능 구현

**요청**: (1) 대시보드 오른쪽에 일정 확인·관리 캘린더 추가. (2) 마이페이지 사이드바 메뉴별 실제 기능 구현.

**변경**: `src/App.jsx` + `src/styles.css`
- `MpCalendar` (신규) — 월 이동 · 날짜 클릭 · **일정 추가/삭제**(세금·지원사업 분류). 대시보드 우측 + `세금 일정` 메뉴에서 사용
- `MyPage` 대시보드를 `.mp-dash`(카드 4개 + 캘린더 2열) 로 재구성
- 사이드바 메뉴별 화면 연결:
  - `사업자유형 진단` → `BizTypeDiagnosis` (신규, 매출·B2B·업종 → 간이/일반 + 개인/법인 추천)
  - `세액감면 판정` → `TaxTool` (기존 재사용)
  - `세금 일정` → `MpCalendar full`
  - `탐색` → `GovExplorer` (기존, `saved` 상태를 MyPage로 리프트)
  - `저장한 정책` → `SavedPolicies` (신규, `탐색`의 ★ 저장 목록 공유)
  - `지출관리` → `ExpenseTracker` (신규, 지출 입력·분류·합산)
  - `프로필 · 설정` → `ProfileSettings` (신규, 프로필 폼 + 알림 토글)
- `GovExplorer` — `{ saved, onToggleSave }` prop 선택적으로 받도록(없으면 기존 내부 상태)
- `styles.css` — `.mp-dash` `.cal__add` `.cal__ev-del` `.exp-*` `.pf-*` 추가

**메모**: 데이터는 목/로컬 상태(추가·삭제·저장 모두 새로고침 시 초기화). 실서비스는 `/api/calendar`·`/api/policies/saved`·`/api/expenses` 연동으로 교체.

## 2026-09-08 · 창업 A-Z 로드맵 아이콘·글씨 확대

**요청**: 창업 순서(A-Z) 부분의 아이콘·글씨 등을 더 크게.

**변경**: `src/styles.css` `.rz*`
- `.rz__ico` 52×52 → **76×76**, radius 16 → 22 / `.rz__ico svg` 22 → **34**
- `.rz__t`(단계명) 13 → **17px** / `.rz__phase` 10.5 → 12.5px / `.rz__d`(설명) 11 → 13px, max-width 15ch → 17ch
- `.rz__sep`(화살표) 16 → **26px**, 위치 보정(margin-top 18 → 28) / `.rz__step` gap 9 → 13, `.rz` margin-top 44 → 60

## 2026-09-08 · 로그인 모달 소셜 버튼 위치 변경

**요청**: 네이버·카카오 버튼을 로그인 버튼 아래로.

**변경**: `src/App.jsx` `LoginModal` — 소셜 버튼 블록(+"또는" 구분선)을 이메일 폼 위 → **`</form>` 아래**(로그인/가입하기 버튼 밑)로 이동.

## 2026-09-08 · 로그인 모달에 소셜 로그인 + 회원가입 추가

**요청**: (1) 카카오·네이버 연동 로그인. (2) 로그인 모달에 회원가입 버튼 등 추가.

**변경**:
- `src/App.jsx` `LoginModal` 재구성
  - `mode` 상태(`login` / `signup`) — 모달 안에서 로그인 ↔ 회원가입 전환
  - 소셜 버튼: **카카오로 계속하기**(#FEE500, 말풍선 아이콘) / **네이버로 계속하기**(#03C75A, N 마크) + "또는" 구분선
  - 회원가입 모드: 이름 · 이메일 · 비밀번호 · 비밀번호 확인(불일치 시 인라인 에러) · `가입하기`
  - 하단: "아직 계정이 없으신가요? 회원가입" ↔ "이미 계정이 있으신가요? 로그인" 링크, "비밀번호를 잊으셨나요?"(데모 안내)
  - 모달에 `maxHeight: 90vh; overflowY: auto`
- `src/App.jsx` 상단 — `linkBtn` `fieldLabel` `socialBtn` 스타일 상수 추가

**메모**: 데모라 소셜/이메일/가입 **모두 예시로 바로 로그인**됨(`onSuccess`로 정석/카카오 사용자/네이버 사용자 등). 실서비스는 카카오·네이버 OAuth(`/oauth/authorize` 리다이렉트) + 백엔드 `/auth/*` 연동으로 교체.

## 2026-09-08 · 창업 A-Z 순차 애니메이션 강화 + 홈 섹션 화면 전체

**요청**: (1) 창업 순서(A-Z) 부분이 차례대로 나오는 애니메이션. (2) 메인페이지에서 각 섹션이 화면 전체에 나오게.

**변경**:
- `src/App.jsx` `Roadmap` — 스텝 stagger 간격 `i*80` → `i*160` ms 로 확대(7단계가 또렷하게 하나씩)
- `src/styles.css` `.rz__step` — 진입 모션 강화: `translateY(26px) scale(0.9)` → 0, `0.6s`. 아이콘도 `scale(0.5) rotate(-8deg)` → 0 로 팝인. reduced-motion 예외 추가
- `src/App.jsx` `Home` — `<main>` → `<main className="home-flow">`
- `src/styles.css` — `.home-flow > section { min-height: 100dvh; flex column center; scroll-snap-align:start }`, `html { scroll-padding-top: 66px }`, 데스크톱(≥768px) `scroll-snap-type: y proximity`, 모바일(<768px) 예외

**메모**: 09-06 에 넣었다가 병합으로 유실됐던 "한 화면에 한 섹션씩"을 다시 적용(이번엔 커밋 필요). "큰 모니터 zoom"(아래 항목)은 이번에 재적용 안 함 — 필요 시 별도 요청.

## 2026-09-06 · 큰 모니터에서도 노트북과 비슷한 비율로  *(유실됨 — 미재적용)*

**요청**: 큰 모니터로 보면 여백이 많고 노트북으로 보면 여백이 적다. 어느 모니터에서 보든 같은 비율로.

**변경**:
- `src/styles.css` — `.wrap` `max-width: 1160px` → `clamp(1120px, 82vw, 1500px)`
- `src/styles.css` — `:root { zoom }` 반응형 추가: `min-width` 1600→1.1 / 1920→1.22 / 2300→1.4 / 2800→1.65. 노트북(~1440px 이하)은 1.0

**메모**: `zoom` 이라 경계값에서 단계적으로 커짐. 연속 스케일 필요하면 JS로 전환. 배율·경계값 조정 가능.

## 2026-09-06 · 홈 메인, 한 화면에 한 섹션씩  *(09-08 에 재적용)*

**요청**: 홈 메인 화면이 2개 섹션이 동시에 보이지 않고 하나하나씩 떴으면 좋겠다.

**변경**:
- `src/App.jsx` — `Home` 의 `<main>` → `<main className="home-flow">`
- `src/styles.css` — `.home-flow > section { min-height: 100dvh; flex column center; scroll-snap-align:start }`, `html { scroll-padding-top: 66px }`, 데스크톱(≥768px) `scroll-snap-type: y proximity`, 모바일(<768px) 예외

**메모**: 스냅이 부담스러우면 `scroll-snap-type` 줄만 제거.

## 2026-09-06 · 리액트 실행 방법을 README에 정리

**요청**: 리액트 실행 방법을 정리해서 프론트엔드에 넣어줘.

**변경**:
- `README.md` — 맨 위 `## 빠른 시작`(3줄) 추가 + `## 실행` 섹션(사전요구사항, clone/pull 흐름, `npm ci`, API 프록시, 문제 해결) + `## 화면 구성` 표 갱신

## 2026-09-06 · Frontend를 창업ON 프로토타입으로 교체

**요청**: 로컬 5173(팀 스캐폴드)은 제거해도 되고, 5180(창업ON 프로토타입)을 메인 프론트엔드로 바꿔줘.

**변경**:
- `src/` — 기존 react-router 스캐폴드 전체 삭제(`router.jsx`, `pages/**`, `components/**`, `context/`, `data/`, `services/`, `styles/`)
- `src/App.jsx`, `src/styles.css` 신규 — 창업ON 프로토타입(홈 / 창업 로드맵 / AI 세무 Assistant / 지원사업 공고문 AI 분석 / AI 상담 / 마이페이지). 라우팅은 `App.jsx` 내부 `view` 상태 전환
- `src/main.jsx` — `createRoot` 마운트로 단순화
- `package.json` — `react-router-dom` 제거, `react`/`react-dom`만. `lint` 스크립트 제거
- `vite.config.js` — `port: 5173`, `open: true`, `/api` → `http://localhost:8000` 프록시
- `index.html` — 폰트 로드 + `favicon.svg` + 기본 리셋

**메모**: 프로토타입 원본은 Claude 아티팩트(`window.claude.use('sample')`)에서 이식. 로컬엔 `window.claude` 없어 AI 기능은 예시 데이터/비활성 폴백 → 실서비스는 `sampleFn` 호출부를 백엔드 `/api/chat`(RAG)로 교체. 삭제된 스캐폴드는 git 이력에 있어 복구 가능.
