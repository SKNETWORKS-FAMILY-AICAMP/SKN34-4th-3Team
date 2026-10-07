# 모바일 · PWA 화면 작업 가이드 (모바일 전용 CSS 파일)

> 작성일 2026-10-01 · 기준 브랜치 `feature_frontend` · 갱신 2026-10-06(진입점 통합, 1절 원칙 추가, 1-1절 신설)
> 목적: 기존 PC 화면을 건드리지 않고, 모바일 화면 디자인을 **별도 CSS 파일 하나**에서 작업한다.

---

## 1. 원칙

| 원칙 | 내용 |
| --- | --- |
| 코드는 하나 | 화면 구조(JSX)와 기능은 PC·모바일이 같이 쓴다. 모바일은 **보이는 모습만** 바꾼다 |
| 모바일 스타일은 한 파일에 | 새 파일 `Frontend/src/styles/14-mobile.css`에만 작성한다 |
| 모든 규칙은 미디어 쿼리 안에 | 파일 안의 모든 규칙을 `@media (max-width: …)` 안에 쓴다. 그래야 PC 화면에 영향이 없다 |
| 기존 파일은 그대로 | `01`~`13` 파일의 기존 반응형 규칙은 고치거나 지우지 않는다. 덮어쓸 일이 있으면 `14-mobile.css`에서 덮어쓴다 |
| 구조 변경이 꼭 필요할 때만 JSX 수정 | CSS로 해결할 수 없을 때만 JSX를 고친다. 예: 사이드바를 하단 탭으로 바꾸기. 이때는 PR에 이유를 적는다 |
| 진입점은 하나 | 모든 기기가 `/`(`index.html` → `src/web/main.jsx`)로 들어온다. 기기·폭별로 다른 진입점(HTML)이나 다른 화면 컴포넌트를 만들지 않는다 |
| 기능은 같게 | 휴대폰 폭에서 요소를 숨기거나 순서를 바꿀 수는 있지만, 조회되는 데이터와 저장 결과는 PC와 같아야 한다 |
| 저장되지 않는 동작 금지 | 화면 상태만 바뀌고 서버에 저장되지 않는 버튼(예: 새로고침하면 사라지는 판정)은 두지 않는다. 저장 API가 없으면 버튼을 만들지 않는다 |

### 1-1. 기기별 별도 화면을 만들지 않는 이유 (2026-10-06 사례)

- 상황: `/`는 휴대폰(폭 768px 이하)에서 모바일 전용 앱(`src/mobile`)을, `/web.html`은 모든 폭에서 PC 화면을 보여 줬다. 두 화면을 따로 고치다 보니 지출관리 기능이 어긋났다
  - 판정 근거·품목 추가/삭제·상호 수정·엑셀 내보내기: PC 화면(`/web.html`)에만 있음
  - 인정·불인정 버튼: 모바일 앱에만 있었고, 서버에 저장되지 않아 새로고침하면 사라짐
- 조치: `/` 하나로 통합(PC 화면 + `src/web/web.css` 반응형 배치, 휴대폰 폭 하단 탭바). `/web.html`은 nginx에서 `/`로 301. `src/mobile/*`과 `styles/15-mobile-app.css`는 연결을 끊고 코드만 보존한다(되살리지 않는다)
- 휴대폰에서만 다르게 보여야 할 때의 순서
  1. CSS로 해결: `styles/14-mobile.css`(미디어 쿼리), `src/web/web.css`(`html.is-web` 아래 규칙)
  2. CSS로 안 되면 같은 컴포넌트 안에서 `useIsMobile()`(`src/mobile/useIsMobile.js`)으로 배치만 나눈다. 기능·저장 동작은 나누지 않는다
  3. 별도 화면 컴포넌트가 꼭 필요하면 팀 합의 후 진행하고, PR에 PC 화면 대비 기능 비교표를 붙인다

---

## 2. 파일 만들기와 등록

### 2-1. 파일 위치

```
Frontend/src/
├── styles.css            ← 모든 CSS를 불러오는 목록
└── styles/
    ├── 01-base.css
    ├── …
    ├── 13-billing.css
    ├── 14-mobile.css     ← 모바일 규칙은 여기
    └── 15-mobile-app.css ← 연결 해제된 모바일 앱 전용(.m-app 범위)
```

- 웹앱 전용 배치(휴대폰 하단 탭바 등)는 `src/web/web.css`에 있다. 모든 규칙이 `html.is-web`(진입점 `src/web/main.jsx`가 붙인다) 아래에서만 동작한다
- `styles/15-mobile-app.css`는 연결 해제된 모바일 전용 앱(`src/mobile`)용이라 수정하지 않는다(1-1절). `styles.css`의 import는 남아 있어 번들에는 들어가지만, 모든 규칙이 `.m-app` 안에서만 동작해 현재 화면에 영향이 없다

### 2-2. `styles.css` 맨 마지막 줄에 추가

```css
@import './styles/13-billing.css';
@import './styles/14-mobile.css';      /* 화면에 쓰이는 규칙 중 맨 마지막 */
@import './styles/15-mobile-app.css';  /* .m-app 범위 전용, 위 규칙과 겹치지 않음 */
```

- **맨 마지막에 둬야 하는 이유**: CSS는 나중에 불러온 규칙이 이깁니다(선택자 강도가 같을 때). 마지막에 두어야 모바일 규칙이 기존 규칙을 덮어씁니다. 그 뒤의 `15-mobile-app.css`는 `.m-app` 아래 규칙만 있어 순서와 무관합니다.
- `styles.css`의 기존 import 순서는 바꾸지 않습니다. 파일 상단 주석에도 같은 경고가 있습니다.

---

## 3. 화면 폭 기준 (브레이크포인트)

### 3-1. 이번 작업에서 쓸 기준 (통일)

| 이름 | 조건 | 대상 기기 |
| --- | --- | --- |
| **모바일** | `@media (max-width: 768px)` | 휴대폰 전반, 작은 태블릿 세로 |
| **작은 휴대폰** | `@media (max-width: 480px)` | iPhone SE·미니, 폭 360~390px 기기 |
| **설치 앱(PWA)** | `@media (display-mode: standalone)` | 홈 화면에 설치해 실행한 경우 |

새 규칙은 위 세 가지만 씁니다. 기준이 늘어날수록 "어느 폭에서 어떤 규칙이 적용되는지" 추적하기 어려워집니다.

### 3-2. 기존 파일에 이미 있는 기준 (참고)

기존 CSS에는 아래 기준들이 페이지마다 흩어져 있습니다. **이번 작업에서는 고치지 않습니다.**

`1100px` · `1080px` · `960px` · `900px` · `860px`(6곳) · `768px` · `767px` · `760px` · `720px` · `640px`(5곳) · `600px` · `560px`(6곳) · `540px` · `520px` · `480px` · 높이 `600px` 이하

- 768px 이하 화면에는 기존 규칙(720·640·560px 등)과 새 모바일 규칙이 **함께 적용**됩니다.
- 화면이 예상과 다르게 보이면, 브라우저 개발자 도구 **Elements → Styles**에서 어떤 파일의 어떤 규칙이 적용됐는지 먼저 확인합니다.

---

## 4. 작성 규칙

### 4-1. 기본 뼈대 (`14-mobile.css`)

```css
/* 모바일 전용 스타일. PC 화면에 영향을 주지 않도록 모든 규칙을 미디어 쿼리 안에 쓴다.
   기준: 768px(모바일) · 480px(작은 휴대폰) · display-mode: standalone(설치 앱) */

/* ===== 공통: 머리글 · 메뉴 · 떠 있는 버튼 ===== */
@media (max-width: 768px) {
}

/* ===== 메인 (.hero, .panel …) ===== */
@media (max-width: 768px) {
}

/* ===== 창업 로드맵 (.rg2, .rz) ===== */
@media (max-width: 768px) {
}

/* ===== 공고지원 AI (.az2) ===== */
@media (max-width: 768px) {
}

/* ===== AI 세무 Assistant (.cvx, .ai) ===== */
@media (max-width: 768px) {
}

/* ===== 지출관리 (.exp2, .exp-*) ===== */
@media (max-width: 768px) {
}

/* ===== 사업계획서 (.bp2) ===== */
@media (max-width: 768px) {
}

/* ===== 마이페이지 (.mp) ===== */
@media (max-width: 768px) {
}

/* ===== 작은 휴대폰 ===== */
@media (max-width: 480px) {
}

/* ===== 설치 앱(PWA)으로 실행했을 때 ===== */
@media (display-mode: standalone) {
}
```

- 페이지별로 구역을 나눠서, 여러 사람이 같은 파일을 고쳐도 Git 충돌이 덜 나게 합니다.

### 4-2. 선택자 쓰는 법

- **페이지 최상위 클래스를 앞에 붙입니다.** 다른 페이지에 같은 클래스 이름이 있어도 영향을 주지 않습니다.
  ```css
  @media (max-width: 768px) {
    .bp2 .bp2__body { grid-template-columns: 1fr; }   /* O: 사업계획서에서만 */
    .bp2__body { grid-template-columns: 1fr; }        /* △: 이름이 겹치면 다른 곳도 바뀔 수 있음 */
  }
  ```
- 기존 규칙을 덮어쓰지 못하면 **선택자를 한 단계 더 구체적으로** 씁니다. `!important`는 최후의 수단으로만 쓰고, 쓸 때는 주석으로 이유를 남깁니다.

### 4-3. 색상은 변수로 (다크 모드)

- 색을 직접(`#ffffff`) 쓰지 말고 기존 변수를 씁니다. 그래야 다크 모드에서도 자동으로 바뀝니다.
  - 사이트 공통: `--ink`, `--ink-soft`, `--ink-faint`, `--surface-solid`, `--ground`, `--line`, `--line-strong`, `--blue`, `--blue-deep`, `--blue-wash`
  - 사업계획서 화면: `--bp-*` (예: `--bp-card`, `--bp-primary`)
  - 지출관리 화면: `--exp-*` (예: `--exp-accent`, `--exp-bad`)
- 정의 위치: `01-base.css`(공통), `10-tools.css`(사업계획서), `11-mypage.css`(지출관리·마이페이지)

### 4-4. 움직임

- 새 애니메이션을 넣으면 "동작 줄이기" 설정 사용자를 위해 아래 규칙도 함께 넣습니다.
  ```css
  @media (prefers-reduced-motion: reduce) { /* 애니메이션 끄기 */ }
  ```

---

## 5. 페이지별 최상위 클래스와 원래 스타일 위치

| 화면 | 최상위 클래스 | 원래 스타일 파일 | 화면 코드 |
| --- | --- | --- | --- |
| 공통 머리글·메뉴 | `.nav`, `.rmhead`, `.drawer` | `01-base`, `02-drawer-nav`, `06-page-shell` | `components/Nav.jsx`, `MenuDrawer.jsx` |
| 메인 | `.hero`, `.panel`, `.home-scale` | `03-home` | `pages/Home.jsx` |
| 창업 로드맵 | `.rg2`, `.rz` | `05-roadmap`, `08-roadmap-guide` | `pages/RoadmapGuide.jsx` |
| 공고지원 AI | `.az2`, `.gov` | `10-tools` | `pages/AnnouncementAnalyzer.jsx` |
| AI 세무 Assistant | `.cvx`, `.ai` | `04-ai-chat`, `07-cvx-sidebar` | `components/AiConsult.jsx` |
| 지출관리 | `.exp2`, `.exp-*` | `11-mypage` | `pages/ExpenseTracker.jsx` |
| 사업계획서 | `.bp2` | `10-tools` | `pages/BusinessPlanPage.jsx` |
| 마이페이지 | `.mp` | `11-mypage` | `pages/MyPage.jsx` |
| 구독·결제 | `.bill` | `13-billing` | `pages/MyPage.jsx` |
| 온보딩 가이드 | `.gt`, `.tour-fab` | `10-tools`, `06-page-shell` | `components/GuideTour.jsx`, `PageTour.jsx` |
| 다크모드 버튼 | `.theme-fab` | `06-page-shell` | `components/common.jsx` |

---

## 6. 모바일 · PWA에서 꼭 챙길 것

| 항목 | 내용 |
| --- | --- |
| **화면 높이** | 앱 화면(`.slim-shell`, `12-misc.css`)은 `height: 100vh` + `overflow: hidden`으로 한 화면에 고정돼 있다. 휴대폰 브라우저는 주소창 때문에 `100vh`가 실제 화면보다 커서 아래가 잘릴 수 있다 → 모바일에서는 `height: 100dvh`로 덮어쓴다 |
| **입력칸 확대 방지** | iOS Safari는 글자 크기 16px 미만 입력칸을 누르면 화면을 확대한다 → 모바일 `input`·`textarea`·`select`는 `font-size: 16px` 이상 |
| **터치 영역** | 버튼·링크는 최소 44×44px |
| **가로 스크롤 금지** | 표·긴 텍스트는 그 영역 안에서만 가로 스크롤하게 한다(`overflow-x: auto`). 페이지 전체가 옆으로 밀리면 안 된다 |
| **떠 있는 버튼** | 오른쪽 아래 `?`(`.tour-fab`)와 다크모드(`.theme-fab`) 버튼이 내용과 겹치지 않는지 확인 |
| **메인 축소 배율** | 메인 본문은 `.home-scale { zoom: 0.9 }`로 90% 축소돼 있다. 모바일에서 글자가 너무 작으면 `zoom: 1`로 덮어쓴다 |
| **노치·홈 바 영역** | 설치 앱에서 화면 끝까지 쓰려면 `padding-bottom: env(safe-area-inset-bottom)` 등을 쓴다. 단, `index.html`의 viewport에 `viewport-fit=cover`를 추가해야 동작한다(현재 없음, CSS 파일 밖 수정이라 PR에 명시) |
| **설치 앱 전용 스타일** | 브라우저와 설치 앱의 모습을 다르게 하려면 `@media (display-mode: standalone)` 안에 쓴다. 데스크톱 설치 앱의 타이틀바 규칙(`display-mode: window-controls-overlay`, `01-base.css`)은 이미 있으니 건드리지 않는다 |
| **이미 모바일 대응된 것** | 온보딩 안내 카드는 640px 이하에서 하단 시트로 바뀐다(`10-tools.css`). 중복으로 고치지 않는다 |

---

## 7. 화면 확인 방법

### 7-1. 실행 중인 서버

| 주소 | 용도 |
| --- | --- |
| `http://localhost:5173` | **디자인 작업용**. CSS를 저장하면 바로 반영 |
| `http://localhost:4173` | **PWA 설치 확인용** 빌드본. 코드를 고친 뒤 확인하려면 다시 빌드해야 함 |

### 7-2. PC에서 모바일 화면 보기

1. 크롬에서 `localhost:5173` 열기
2. `F12` → `Ctrl + Shift + M`(기기 모드)
3. 아래 폭에서 모두 확인

| 폭 | 대표 기기 |
| --- | --- |
| 360px | Galaxy S 시리즈(작은 화면) |
| 390px | iPhone 14·15 |
| 430px | iPhone Pro Max |
| 768px | 태블릿 세로(경계값) |
| 1280px 이상 | **PC 화면이 그대로인지** 반드시 확인 |

### 7-3. 실제 휴대폰에서 보기

- 휴대폰을 PC와 **같은 와이파이**에 연결하고 `http://<PC의 IP>:5173` 접속(PC에서 `ipconfig`로 IPv4 주소 확인)
- Windows 방화벽이 막으면 접속되지 않을 수 있음
- 휴대폰에서는 HTTPS가 아니어서 **앱 설치는 안 되고 화면 확인만** 가능. 휴대폰 설치 확인은 배포된 HTTPS 사이트에서 한다

### 7-4. 확인 체크리스트

- [ ] 360 / 390 / 430 / 768px에서 가로 스크롤이 생기지 않는다
- [ ] 1280px 이상 PC 화면이 작업 전과 같다
- [ ] 라이트·다크 모드 모두 글자가 잘 보인다
- [ ] 입력칸을 눌러도 화면이 확대되지 않는다(iOS)
- [ ] 화면 아래쪽이 주소창·홈 바에 가려 잘리지 않는다
- [ ] `?`·다크모드 버튼이 주요 버튼을 가리지 않는다
- [ ] 페이지별 온보딩 안내가 모바일에서 정상 표시된다
- [ ] 휴대폰 폭과 PC 폭에서 같은 기능을 쓸 수 있고, 저장한 결과가 새로고침 후에도 같다
- [ ] 화면 상태만 바꾸고 서버에 저장하지 않는 버튼이 없다
- [ ] 빌드가 통과한다: `docker compose -f docker-compose.yml -f docker-compose.dev.yml exec frontend-dev npx vite build --outDir /tmp/dist-check`

---

## 8. Git 작업 흐름

1. 브랜치 만들기: `git checkout -b feature/pwa-mobile`
2. `14-mobile.css` 작성 + `styles.css`에 import 한 줄 추가
3. 체크리스트 확인 후 커밋
4. `develop ← feature/pwa-mobile` PR 생성. PR에 모바일 캡처(360·390px)와 PC 화면이 그대로라는 캡처를 첨부한다
5. CSS 파일 밖을 수정했다면(JSX, `index.html` 등) PR 본문에 따로 적는다
