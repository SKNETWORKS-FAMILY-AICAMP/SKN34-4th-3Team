# 창업ON 발표자료 디자인 가이드

Slidev 발표 덱(`Presentation/slides.md`)에 적용하는 디자인 규칙. Frontend 디자인 언어를 16:9 슬라이드용으로 옮긴 기준.

- 원본: `Frontend/src/styles/01-base.css`(토큰), `03-home.css`(hero·panel·badge·eyebrow), `04-ai-chat.css`(chatbox·msg), `05-roadmap.css`(rz 스텝), `09-metrics-closing.css`(metric·closing)
- 구현: `Presentation/style.css`(토큰·공통 클래스), `layouts/cover.vue`, `global-top.vue`, `components/*.vue`

---

## 1. 원칙

| 원칙 | 적용 |
|---|---|
| 한 슬라이드 한 메시지 | 제목은 결론형 문장, 보조 설명은 1~2줄 |
| 수치 강조 | 핵심 숫자는 Space Grotesk 대형 표기, 설명은 작게 |
| 넉넉한 여백 | 콘텐츠를 채우기보다 비움. 카드 4개 이하 |
| 글래스 surface | 옅은 흰 반투명 카드 + 얇은 흰 테두리 + 부드러운 그림자 |
| 서비스와 동일한 인상 | 화면 목업은 Frontend 클래스 구조·색을 그대로 재현 |

톤: 토스증권 랜딩 참고(`Frontend/README.md`). 차분한 네이비 텍스트 + 블루/바이올렛 포인트.

## 2. 컬러 토큰

라이트 테마만 사용. 다크 토큰은 발표 덱에서 사용하지 않음.

| 토큰 | 값 | 용도 |
|---|---|---|
| `--ground` | `#f4f6fd` | 슬라이드 배경 |
| `--ground-2` | `#eaeefb` | 배경 그라데이션 하단, 섹션 구분 |
| `--surface` | `rgba(255,255,255,.74)` | 글래스 카드 |
| `--surface-solid` | `#ffffff` | 목업 창, 차트 박스 |
| `--edge` | `rgba(255,255,255,.92)` | 글래스 카드 테두리 |
| `--line` | `rgba(31,45,90,.09)` | 구분선 |
| `--line-strong` | `rgba(31,45,90,.16)` | 강조 구분선, 노드 테두리 |
| `--ink` | `#182142` | 제목·본문 |
| `--ink-soft` | `#59637f` | 보조 설명 |
| `--ink-faint` | `#8b93b2` | 캡션·출처·페이지 번호 |
| `--blue` | `#2f7bf0` | 주 포인트, eyebrow, 링크 |
| `--blue-deep` | `#2467e6` | 강조 텍스트(`em`), 아이콘 |
| `--blue-wash` | `#eef4ff` | 강조 박스 배경 |
| `--violet` | `#7c5cf0` | 보조 포인트(정책 계열) |
| `--green` | `#00925f` | 개선 수치, 성공 상태 |
| `--red` | `#dc3c42` | 문제·긴급(D-7 이하) |
| `--amber` | `#a9700d` | 주의(D-30 이하), 저장 ★ |

- 브랜드 그라데이션: `linear-gradient(135deg, var(--blue), var(--violet))` — 브랜드마크, accent 스텝, 표지 강조에만 사용
- 글로우: `--glow-blue rgba(47,123,240,.28)`, `--glow-violet rgba(150,120,255,.24)` — 표지·마무리 슬라이드 배경의 radial-gradient
- 그림자: `--shadow 0 22px 54px rgba(24,33,66,.13)`, `--shadow-sm 0 8px 24px rgba(24,33,66,.08)`
- 의미 색 고정: 세무 = blue, 정책·공고 = violet (Frontend 캘린더 `t-tax`/`t-policy`와 동일)

## 3. 타이포그래피

| 역할 | 폰트 |
|---|---|
| 본문·제목 | `'IBM Plex Sans KR', Pretendard, 'Malgun Gothic', sans-serif` |
| 숫자·eyebrow·코드성 라벨 | `'Space Grotesk'` + `font-variant-numeric: tabular-nums` |

캔버스 1280×720 기준 스케일.

| 요소 | 크기 | 굵기 | 자간 | 색 |
|---|---|---|---|---|
| 표지 제목 | 72px | 700 | -0.05em | ink |
| 슬라이드 제목 `h1` | 38~40px | 700 | -0.04em | ink |
| eyebrow | 13px | 700 | 0.2em | blue |
| 대형 수치 | 56~88px | 700 | -0.03em | ink / green |
| 카드 제목 | 20px | 700 | -0.02em | ink |
| 본문 | 18~20px | 400 | 0 | ink-soft |
| 캡션·출처 | 13~14px | 400 | 0 | ink-faint |

- 줄간격: 제목 1.3, 본문 1.7
- 줄바꿈: `word-break: keep-all` — 한글 단어 중간 줄바꿈 금지. 줄바꿈 위치가 중요하면 `<br>`로 지정
- 강조: `<em>`은 기울임 없이 `--blue-deep`

## 4. 레이아웃

- 캔버스 `1280×720`(16:9), 안전 여백 상하 56px · 좌우 72px
- 하단 36px은 `global-top.vue` 영역(브랜드마크 · 페이지 번호). 콘텐츠 침범 금지
  - global-bottom은 슬라이드 배경 뒤에 렌더링되어 가려지므로 global-top 사용
- 슬라이드는 세로 flex. 출처(`.source`)는 `margin-top:auto`로 본문 아래 흐름 배치(absolute 금지)
- 텍스트 밀도: 제목 1줄, 카드 본문 2줄 이내
- 슬라이드 상단 구조: `eyebrow` → `h1` → 본문 (제목 아래 설명문 없음). 제목–본문 간격은 `h1` 하단 여백 48px로 통일하고 본문 첫 요소에 margin-top을 주지 않음
- 그리드
  - 2단: `1.08fr : 0.92fr`(Frontend hero 비율), 설명 + 목업
  - 3·4단 카드: gap 20px
- radius: 카드 22px, 작은 칩·버튼 11px, pill 999px

## 5. 컴포넌트

`style.css` 클래스명 기준.

| 클래스 / 컴포넌트 | 설명 | 원본 |
|---|---|---|
| `.eyebrow` | 섹션 라벨. 대문자 영문 또는 짧은 한글 | `.eyebrow` |
| `.lead` | 표지·Q&A 부제 전용, ink-soft | `.lede` |
| `.badge` + `.badge__dot` | pill 라벨 + green 점 | `.badge` |
| `.card` | 글래스 카드(surface·edge·radius 22·shadow-sm) | `.panel`, `.step` |
| `.card--wash` | blue-wash 배경 강조 카드 | `.closing` |
| `.chip` | 태그 pill(12~13px) | `.chat__tag` |
| `.btn--primary` / `.btn--ghost` | 목업 내 버튼 | `.btn` |
| `<Metric>` | 라벨 + before → after + 변화량(green) | `.metric` |
| `<FlowStep>` | 72px 아이콘 박스 + phase + 제목 + 설명, `accent`는 그라데이션 | `.rz__step` |
| `.mock` | 목업 창(surface-solid·line·radius 20·shadow), `.mock__bar` 상단 바 | `.cal`, `.chatbox` |
| `.msg--user` / `.msg--ai` | 대화 말풍선 | `.msg` |
| `.dl-row` | D-day(tone) + 제목/메타 + ★ | `.deadline` |
| `.node` / `.arrow` | 아키텍처·파이프라인 노드와 연결선 | — |

- 아이콘: Frontend `roadmapIcons.jsx`와 같은 24px viewBox, stroke 1.8 선 아이콘. 이모지 아이콘 금지

## 6. 데이터 표기

- 전후 비교: `64.3% → 74.6%` 형식, 변화량은 `+10.3%p`로 green
- 시간 감소도 개선이므로 green: `17.69s → 12.46s  −29.6%`
- 모든 수치 슬라이드 하단에 출처 캡션: `출처: Docs/reports/04_FINAL_REPORT.md`
- 평가 한계 명시: holdout 반복 사용, 세금 통과율은 자동 채점 기준
- 화면 목업 내 공고·점수 등 목데이터는 사실 수치로 인용하지 않음

## 7. 모션

- 슬라이드 전환: `fade`만 사용
- 클릭 순차 등장(`v-click`) 사용 안 함. 모든 항목은 슬라이드 진입 시 표시
- Frontend의 blur·drift 애니메이션은 표지 글로우에만 정적으로 사용

## 8. 화면 컨트롤

- 이전/다음 버튼만 표시(`global-top.vue` 하단 우측), 키보드 ←/→/Space 탐색 유지
- Slidev 기본 내비 바 숨김, 카메라·녹화·그리기·발표자 모드·내보내기·에디터·컨텍스트 메뉴 비활성(`slides.md` headmatter)
- 슬라이드 배율은 항상 자동 맞춤(`slidev-scale` = 0 고정)

## 9. 슬라이드 타입

| 타입 | 레이아웃 | 사용 슬라이드 |
|---|---|---|
| cover | `layout: cover` — 세로 중앙, 글로우 배경, 브랜드마크, 페이지 번호 숨김 | 표지(좌측 정렬), Q&A(중앙 정렬) |
| agenda | default + 번호 리스트 | 목차 |
| cards | default + 3·4단 `.card` | 문제 정의, 기술 스택, 한계 |
| flow | default + `<FlowStep>` 가로 배치 | 서비스 흐름, 로드맵 |
| showcase | default + 2단(설명 : `.mock`) | 기능 소개 |
| diagram | default + `.node` / `.arrow` | 아키텍처, 파이프라인 |
| metrics | default + `<Metric>` 4단 | 평가 결과, 캐시 개선 |
| list | default + cause → fix 행 | 트러블슈팅 |

## 10. Do / Don't

| Do | Don't |
|---|---|
| 라이트 배경 `--ground` 유지 | 다크 배경·원색 풀배경 |
| 토큰 변수로만 색 지정 | 임의 hex 추가 |
| 텍스트 6줄 이하, 카드 4개 이하(계층 비교는 5단 허용) | 문서 문단 그대로 붙여넣기 |
| 수치마다 출처 캡션 | 출처 없는 성능 수치 |
| 선 아이콘(SVG) | 이모지 아이콘 |
| 목업은 Frontend 구조 재현 | 서비스에 없는 기능을 목업에 표시 |
