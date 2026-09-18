# Frontend · 청년 창업 & 세금 내비게이터 (창업ON)

토스증권 랜딩 톤(넉넉한 여백 · 화이트 배경 · 블루 포인트)을 참고한 React 프론트엔드입니다.
홈 · 창업 로드맵 · AI 세무 Assistant · 공고지원 AI · 마이페이지 화면을 포함합니다.

## 빠른 시작

> 사전 조건: Node.js 18 이상 (`node -v` 로 확인)

```bash
cd Frontend        # 저장소 루트에서
npm install        # 최초 1회 / package.json·lock 이 바뀐 뒤. (권장: npm ci)
npm run dev        # → http://localhost:5173  (브라우저 자동 실행)
```

- 중단: 터미널에서 `Ctrl + C`
- 포트 5173 이 사용 중이면 5174… 로 자동 이동
- `git pull` 로 최신 코드를 받은 뒤에는 `npm install` 을 다시 실행
- 자세한 설명·문제 해결은 아래 [실행](#실행) 참고

## 스택

- React 18 + Vite 5
- 라우팅: `App.jsx` 내부 상태 기반 뷰 전환 (`home` / `page` / `mypage`) — 라우터 라이브러리 미사용. `page` 안의 화면(`roadmap` / `tax` / `gov`)은 `pages/SubPage.jsx`가 고른다
- 스타일: `src/styles.css`가 `src/styles/01-base.css` ~ `12-misc.css` 12개를 순서대로 `@import`. CSS 변수 기반 라이트·다크 토큰 + 반응형. **import 순서가 캐스케이드에 영향을 주므로 바꾸지 않는다**
- API: `src/api.js`. 토큰은 localStorage에 두고 `Authorization: Bearer`로 보낸다
- AI 기능: `components/AiConsult.jsx`가 Backend `POST /chat/messages`(RAG)로 질문하고 `GET /chat/messages/{id}/sources`로 근거를 붙인다. `window.claude.use('sample')` 런타임은 Backend가 쓸 만한 답을 못 줬을 때만 쓰는 보조 경로이며 로드맵 코치는 이 보조 경로를 끈다(`allowSampleFallback={false}`)

## 실행

### 사전 요구사항

- Node.js **18 이상** (Vite 5 기준, 20 LTS 권장) — `node -v` 로 확인
- npm (Node 설치 시 포함)

### 처음 받는 사람 (clone 후 최초 1회)

```bash
git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-3rd-3Team.git
cd SKN34-3rd-3Team/Frontend

npm ci               # package-lock.json 그대로 설치 (권장). 없으면 npm install
cp .env.example .env # 백엔드 API 주소 설정 (기본값 /api 프록시면 그대로 둬도 됨)

npm run dev          # http://localhost:5173 (포트 사용 중이면 5174…로 자동)
```

### 이미 clone 했고, 다른 사람이 push한 걸 받아서 실행할 때

```bash
cd SKN34-3rd-3Team
git pull                     # 최신 코드 받기
cd Frontend
npm ci                       # package.json / lock 이 바뀌었을 수 있으니 pull 후 매번
npm run dev
```

### 기타 명령

```bash
npm run build     # 프로덕션 빌드 → dist/
npm run preview   # 빌드 결과 로컬 미리보기
```

### git이 나르지 않는 것 → 각자 PC에서 생성

| 저장소에 올라감 (pull 시 받음) | `.gitignore` (각자 생성) |
|---|---|
| `src/`, `public/`, `index.html`, `package.json`, **`package-lock.json`**, `.env.example`, `vite.config.js`, `Dockerfile`, `nginx.conf`, `.dockerignore`, `CHANGES.md` | **`node_modules/`**, `.env`, `dist/` |

- `node_modules/` 는 push되지 않으므로 **clone·pull 후 `npm ci`(또는 `npm install`) 필수**.
- `npm ci` 는 `package-lock.json` 과 100% 동일하게 설치해 "내 PC에선 됐는데" 문제를 줄인다. `package.json` 을 직접 고쳐 의존성을 추가/변경할 때만 `npm install`.
- `.env` 는 개인 설정이라 공유하지 않는다. 새 환경변수가 생기면 `.env.example` 에 키를 추가해 커밋한다.

### API 프록시

개발 서버는 `/api` 요청의 접두사를 벗겨 `http://localhost:8000`(FastAPI)으로 프록시합니다. (`vite.config.js`)
배포에서는 nginx(`nginx.conf`)가 같은 역할을 하며 대상만 `http://backend:8000`입니다.

대부분의 화면이 Backend를 실제로 호출합니다. Backend가 없으면 로그인·AI 상담·맞춤 추천은 오류 안내가 뜨고, `useApi`로 부르는 일부 GET(홈 마감 임박 공고·통계, 마이페이지 캘린더, 로드맵 추천 질문)만 목데이터로 조용히 폴백합니다.

### 자주 나는 문제

| 증상 | 조치 |
|---|---|
| `vite: command not found` / 모듈 없음 | `npm ci` 를 안 했거나 실패 → 다시 실행 |
| `EADDRINUSE` (포트 충돌) | 5173 사용 중 → Vite가 자동으로 다음 포트 사용, 또는 `npm run dev -- --port 5180` |
| Node 버전 에러 | Node 18+ 로 업그레이드 (nvm 등) |
| 설치가 계속 깨짐 | `rm -rf node_modules package-lock.json && npm install` (lock 재생성은 팀 공유 후) |

## 폴더 구조

```
Frontend/
├─ index.html              진입 HTML (폰트 로드 + 기본 리셋)
├─ vite.config.js          Vite 설정 (port 5173, /api 프록시)
├─ nginx.conf / Dockerfile 배포용 (frontend 프로필 컨테이너, :80)
├─ CHANGES.md              화면 변경 기록
├─ public/favicon.svg
└─ src/
   ├─ main.jsx             createRoot 마운트
   ├─ App.jsx              로그인 세션·뷰 전환·관심 정책·로드맵 진행 상태
   ├─ api.js               Backend 호출 함수, useApi(GET + 목데이터 폴백)
   ├─ constants.js         상수·목데이터
   ├─ utils.js             날짜·localStorage 저장·판정 헬퍼
   ├─ hooks.js             useInView / useCountUp / useThemeToggle
   ├─ components/
   │  ├─ AiConsult.jsx     AI 대화 엔진(세무·공고지원·로드맵 공용, 대화방 사이드바)
   │  ├─ Markdown.jsx      AI 답변 마크다운 렌더러
   │  ├─ LoginModal.jsx / Nav.jsx / MenuDrawer.jsx
   │  ├─ common.jsx        Reveal, Metric, ScrollProgress, FloatingThemeToggle
   │  └─ roadmapIcons.jsx  로드맵 단계 아이콘
   ├─ pages/
   │  ├─ Home.jsx          홈 랜딩
   │  ├─ SubPage.jsx       roadmap / tax / gov 페이지 셸
   │  ├─ RoadmapGuide.jsx / TaxAssistantPage.jsx / AnnouncementAnalyzer.jsx
   │  ├─ MyPage.jsx        마이페이지(하위 컴포넌트 포함)
   │  └─ GovExplorer.jsx / TaxTool.jsx   미사용 (아래 참고)
   ├─ styles.css           styles/*.css import 목록
   └─ styles/01-base.css ~ 12-misc.css
```

## 화면 구성

`App.jsx` 가 `view` 상태로 화면을 전환한다 (URL 라우팅 없음). `page` 뷰의 본문은 `pages/SubPage.jsx` 가 `pageKey` 로 고른다.

| view | 화면 | 주요 컴포넌트 |
|---|---|---|
| `home` | 홈 랜딩 — Hero(마감 임박 공고·관심 저장) · 창업 일정 캘린더(예시 데이터) · AI 대화 데모(정해진 대사 재생) · 창업 A–Z 로드맵 · 지표+시작 CTA | `Hero` `DeadlinePanel` `Schedule`(`Calendar`) `ChatDemo` `Roadmap` `Closing` |
| `page` (`roadmap`) | 창업 로드맵 가이드 — 7단계 체크리스트 + 로드맵 AI 코치(`category=roadmap`) | `RoadmapGuide` `AiConsult` |
| `page` (`tax`) | AI 세무 Assistant — 세무 AI 대화 + 대화방 사이드바(새 대화·이름 변경·삭제) | `TaxAssistantPage` (`AiConsult category="tax"`) |
| `page` (`gov`) | 공고지원 AI — 추천 공고 4건(목데이터 점수) · 공고 상세 모달 · 달력 · 공고 상담 AI(`category=policy`) | `AnnouncementAnalyzer` `GovDetailModal` `AiConsult` |
| `mypage` | 로그인 후 대시보드 — 로드맵 진행률 · 세무 AI/공고지원 AI 최근 질문 · 저장 공고 수 · 서버 캘린더(내 일정·세금 신고일·저장 정책 마감일). 메뉴: 사업자 정보 · 공고·정책(저장·맞춤 추천) · 서류(준비 중) · 설정(알림 토글) | `MyPage` `MpCalendar` `ProfileSettings` `SavedGov` `SavedPolicies` `MatchedGov` |

상단 햄버거(≡) → 슬라이드 메뉴에서 각 `page` 뷰와 로그인/로그아웃 진입. 로그인은 Backend 토큰 인증이며 회원가입 시 이름·업종·지역·나이를 받는다. 카카오·네이버 버튼은 데모 계정으로 로그인한다.

### 미사용 코드

렌더되지 않지만 보존 중인 코드. 되살리려면 import 해서 렌더하면 된다.

- `pages/GovExplorer.jsx`, `pages/TaxTool.jsx`
- `pages/MyPage.jsx` 의 `BizTypeDiagnosis`(사업자 유형 진단), `ExpenseTracker`(지출 분석, 추가 기능), `ChatLog`
- 호출자가 없는 `api.js` 함수: `summarizeAnnouncement`(결함 40), `stats`·`announcements`·`policies`·`policy`·`recommendations`·`calendar`·`calendarUpcoming`·`taxSchedule`·`taxDocuments`(같은 경로를 `useApi`로 직접 부르는 화면은 있음), `useBackendStatus`

## 다음 작업 (TODO)

- [x] 목/예시 데이터 → 백엔드 API 연동 (`Docs/Design/API_SPEC.md`)
- [x] AI 호출을 RAG 백엔드(`/chat/messages`)로 교체, 답변 근거(출처) 표기
- [x] 세액감면 판정 규칙 백엔드 Rule Engine(`Backend/services/tax_service.py`)으로 이전 — 이를 부르던 `TaxTool` 은 현재 미사용
- [x] 회원가입/로그인 실제 인증(토큰) + 개인정보·사업자정보 입력 폼 (소셜 로그인은 데모 계정)
- [ ] 필요 시 `react-router-dom` 도입해 URL 라우팅으로 전환
- [ ] 지출 분석(영수증 OCR) 화면 — 추가 기능(추후 개발, `Docs/README.md` 8절). `pages/MyPage.jsx`의 `ExpenseTracker`는 렌더되지 않는 미사용 컴포넌트
- [ ] 공고문 원문 붙여넣기 요약 화면 (결함 40, `Docs/STATUS.md` 2절)
- [ ] 접근성(포커스 트랩, aria) 점검 · 세무 정보 면책 문구 상시 노출
