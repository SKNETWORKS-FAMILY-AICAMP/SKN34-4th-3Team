# PWA 적용 계획

> 작성일 2026-09-28, develop `d35f0c4` 기준. 프론트엔드(React + Vite)를 설치 가능한 PWA로 전환하는 계획. 코드 변경 전 설계 단계 문서.
>
> 2026-09-28 로컬 구현(10절 ① 단계) 완료: `Frontend/vite.config.js`, `index.html`, `nginx.conf`, `public/` 아이콘. 병합·실기기 검증은 AWS 이후.
>
> 선행 작업은 AWS 마이그레이션(`feature/aws`, `Docs/reports/AWS_MIGRATION_PLAN.md`). AWS 이전·HTTPS 적용 후 병합하며, 병합 이후에는 `main` 기준 AWS 자동 배포에 PWA 산출물이 함께 포함되어 별도 배포 작업 없이 갱신되는 구조.

## 1. 배경과 목표

| 목표 | 내용 |
|---|---|
| 홈 화면 설치 | Android Chrome 설치 프롬프트, iOS Safari 홈 화면 추가로 앱처럼 실행(주소창 없는 `standalone`) |
| 앱 셸 빠른 로딩 | 빌드 산출물(HTML·JS·CSS·아이콘)을 Service Worker가 precache → 재방문 시 네트워크 대기 없이 화면 표시 |
| 배포 자동 반영 | `main` 병합 → AWS 재빌드 → 사용자 브라우저의 SW가 새 버전으로 자동 교체 |

범위 밖
- 오프라인 데이터 조회·작성 동기화(Background Sync)
- 푸시 알림(Web Push). 필요 시 별도 계획
- API 응답 캐시. 사용자별 데이터·로그인 토큰이 오가므로 SW 캐시 대상에서 제외(4절)

## 2. AWS 의존성과 병합 시점

| 항목 | 내용 |
|---|---|
| HTTPS 필수 | Service Worker는 보안 컨텍스트(HTTPS, localhost 예외)에서만 등록 가능 |
| AWS 1차 배포 | 도메인 미보유로 Elastic IP + HTTP (`Docs/AWS_DEPLOY_GUIDE.md` 개요) → 설치·SW 동작 불가 |
| HTTPS 적용 시점 | `Docs/AWS_DEPLOY_GUIDE.md` 12절(도메인 확보 → certbot → nginx 443). 같은 절 4단계가 "이후 PWA 적용" |
| HTTP 환경에서 병합 시 영향 | 비보안 컨텍스트에서는 `navigator.serviceWorker`가 없어 등록 코드가 실행되지 않음. manifest 링크만 남아 기존 동작에 영향 없음 |

병합 순서
1. `feature/aws` → develop → main (AWS 자동 배포 가동)
2. `feature/pwa`를 최신 develop 기준으로 rebase → develop → main
3. HTTPS 적용(AWS 12절) 후 실기기 설치 검증

PWA 코드는 프론트 한정 변경이라 AWS 작업과 병행해 localhost에서 개발·검증 가능. 실기기 검증만 HTTPS 이후 진행.

## 3. 현재 프론트 구성

| 항목 | 현황 |
|---|---|
| 빌드 | Vite 5 + React 18 (`Frontend/package.json`, `Frontend/vite.config.js`) |
| 정적 파일 | `Frontend/public/favicon.svg`만 존재. manifest·PNG 아이콘·SW 없음 |
| 진입점 | `Frontend/index.html` → `Frontend/src/main.jsx` |
| 배포 이미지 | `Frontend/Dockerfile` 2단계 빌드: `npm ci && npm run build` → nginx에 `dist` 복사 |
| nginx | `Frontend/nginx.conf`: `/api/` → backend 프록시, `/ppt/` → presentation 프록시, `/` → SPA `try_files $uri /index.html` |
| 인증 | 토큰을 `localStorage`에 저장, `Authorization: Bearer` 헤더로 전송 (`Frontend/src/api.js:18-39`). 쿠키 미사용 |
| 외부 리소스 | Google Fonts CSS·폰트 파일 (`Frontend/index.html`) |

## 4. 구현 방식

`vite-plugin-pwa`(Workbox `generateSW` 모드) devDependency 1개 추가. 빌드 시 `manifest.webmanifest`, `sw.js`, `registerSW.js`를 `dist`에 자동 생성하고 `index.html`에 등록 스크립트를 주입.

| 설정 | 값 | 이유 |
|---|---|---|
| `registerType` | `'autoUpdate'` | 새 배포 감지 시 사용자 조작 없이 SW 교체 → 배포 자동 반영 요구사항 충족 |
| `injectRegister` | `'auto'` | 등록 스크립트 자동 주입. `main.jsx` 수정 불필요 |
| `workbox.globPatterns` | `**/*.{js,css,html,svg,png,ico}` | 빌드 산출물만 precache. manifest는 플러그인이 별도 등록 |
| `includeManifestIcons` | `false` | `public/` 아이콘이 globPatterns로 이미 precache되어 중복 등록 방지 |
| `workbox.navigateFallback` | `/index.html` | SPA 라우팅 유지 |
| `workbox.navigateFallbackDenylist` | `[/^\/api\//, /^\/ppt/]` | API·발표자료(Slidev) 요청에 SW가 `index.html`을 대신 응답하지 않도록 제외 |
| `/api/*` 런타임 캐시 | 설정하지 않음 (네트워크 직행) | 사용자별 데이터, 로그인 응답, 사업계획서 파일 다운로드가 캐시에 남지 않도록 보호 |
| Google Fonts 런타임 캐시 | `StaleWhileRevalidate`(CSS), `CacheFirst` + 만료(폰트 파일) | 선택 사항. 1차 구현에서는 생략 (오프라인 시 시스템 폰트로 대체) |
| `manifest` | `name: 창업ON`, `short_name: 창업ON`, `start_url: /`, `scope: /`, `display: standalone`, `lang: ko`, `theme_color: #3182F6`(파비콘 색), `background_color: #f7f8fe`(`index.html` body 배경) | 도메인 루트 배포 전제 |

## 5. 변경 파일

| 대상 | 변경 내용 |
|---|---|
| `Frontend/package.json`, `package-lock.json` | `vite-plugin-pwa` devDependency 추가 |
| `Frontend/vite.config.js` | `VitePWA({...})` 플러그인 추가, 4절 설정·manifest 정의 |
| `Frontend/index.html` | `<meta name="theme-color">`, `<link rel="apple-touch-icon">` 추가 (manifest 링크는 플러그인이 주입) |
| `Frontend/public/` | `pwa-192x192.png`, `pwa-512x512.png`, `maskable-icon-512x512.png`, `apple-touch-icon-180x180.png` 추가. `npx @vite-pwa/assets-generator --preset minimal-2023 public/favicon.svg`로 1회 생성 후 커밋 (의존성 미추가, 부산물 `pwa-64x64.png`·`favicon.ico`는 삭제) |
| `Frontend/nginx.conf` | SW·manifest 캐시 헤더 추가 (6절) |
| `Frontend/src/main.jsx` | 변경 없음 (`injectRegister: 'auto'`) |
| `.github/workflows/deploy.yml`, `docker-compose.app.yml`, `Frontend/Dockerfile` | 변경 없음 (7절) |

## 6. nginx 캐시 헤더

SW 파일이 브라우저·중간 캐시에 오래 남으면 새 배포가 반영되지 않음. 파일 성격별로 헤더 분리.

| 경로 | 헤더 | 이유 |
|---|---|---|
| `/sw.js`, `/registerSW.js`, `/manifest.webmanifest`, `/index.html` | `Cache-Control: no-cache` | 매 방문 시 서버 재검증 → 새 배포 즉시 감지 |
| `/assets/*` | `Cache-Control: public, max-age=31536000, immutable` | Vite가 파일명에 해시 부여. 내용이 바뀌면 파일명도 바뀜 |
| 그 외 `/` | 기존 `try_files` 유지 | - |

```nginx
# 기존 location / 위에 추가. SPA 경로도 try_files 로 /index.html 에 들어오므로 no-cache 적용됨
location ~ ^/(sw\.js|registerSW\.js|manifest\.webmanifest|index\.html)$ {
    root /usr/share/nginx/html;
    add_header Cache-Control "no-cache";
}
location /assets/ {
    root /usr/share/nginx/html;
    add_header Cache-Control "public, max-age=31536000, immutable";
}
```

AWS HTTPS 단계(`AWS_DEPLOY_GUIDE.md` 12절)에서 `nginx.conf`에 443 server 블록이 추가되고 80 블록은 리다이렉트 전용이 됨. 위 location은 **443 블록에 위치해야 함**. 두 작업이 같은 파일을 수정하므로 PWA 병합은 HTTPS 변경 이후 rebase해 충돌을 정리하는 순서로 진행(2절). HTTPS 적용 전 병합하는 경우 80 블록에 두고, HTTPS 작업 시 443 블록으로 함께 이동.

## 7. main 병합 → AWS 자동 반영 흐름

PWA 산출물은 `npm run build` 결과물에 포함되므로 AWS 배포 자동화(`AWS_MIGRATION_PLAN.md` 9절)를 그대로 사용. workflow·compose·Dockerfile 수정 불필요.

```
develop → main PR 병합
      ↓ push 이벤트
GitHub Actions (.github/workflows/deploy.yml)
  test job: npm ci → node --test → npm run build   ← PWA 산출물 생성까지 검증
      ↓ 통과 시에만 진행
  deploy job: SSH → App EC2
      git pull --ff-only origin main
      docker compose -f docker-compose.app.yml up -d --build
        → frontend 이미지 재빌드 (sw.js, precache 목록, manifest 새로 생성)
      ↓
사용자 브라우저
  페이지 방문 시 sw.js 재검사 (no-cache)
  → precache 목록 변경 감지 → 새 SW 설치·활성화 (autoUpdate)
  → 페이지 자동 새로고침 후 새 버전 표시
```

### 자동 반영 대상과 수동 대상

| 대상 | 반영 | 방식 |
|---|---|---|
| 화면 코드, SW, precache 목록 | 자동 | main 병합 → frontend 재빌드 → autoUpdate |
| manifest(앱 이름·색상), 아이콘 | 자동 | 재빌드 시 반영. 이미 설치된 앱의 아이콘·이름 갱신은 OS·브라우저 주기에 따라 지연 가능 |
| nginx 캐시 헤더 | 자동 | `nginx.conf`가 frontend 이미지에 포함 |
| 도메인, HTTPS 인증서 | **수동** | AWS 12절. 인증서 갱신은 certbot 자동 갱신 |

## 8. 주의점

- `start_url`·`scope`는 `/` 전제. 도메인·경로가 바뀌면 기존 설치 앱은 다른 출처로 취급 → 재설치 필요. **도메인 확정 후 HTTPS·PWA 검증** 순서 유지
- Elastic IP(HTTP)로 접속한 기록이 있는 브라우저는 SW 미등록 상태라 도메인 전환 영향 없음
- 배포 직후 열려 있던 탭은 autoUpdate로 자동 새로고침됨. 사업계획서 작성 등 입력 중 새로고침 위험 → 작성 중 초안은 이미 `localStorage`에 저장(`Frontend/src/pages/BusinessPlanPage.jsx`의 `DRAFT_KEY`)되어 손실 범위 제한. 문제가 되면 `registerType: 'prompt'`로 전환해 "새 버전 적용" 버튼 방식 사용
- iOS Safari는 설치 프롬프트 없음. 공유 → "홈 화면에 추가" 안내 필요
- `/ppt/`(Slidev)는 별도 컨테이너 정적 사이트 → SW 범위(`navigateFallbackDenylist`)에서 제외
- 개발 서버(`npm run dev`)에서는 SW 비활성(`devOptions.enabled: false` 기본값) → 개발 중 캐시 혼선 없음. 검증은 `npm run build && npm run preview`

## 9. 롤백

| 상황 | 방법 |
|---|---|
| 일반 버그 | 문제 커밋 revert → main 병합 → 자동 재배포 (AWS 9절과 동일) |
| PWA 완전 제거 | `VitePWA({ selfDestroying: true })`로 1회 배포 → 사용자 브라우저의 기존 SW·캐시 해제 확인 후 플러그인 제거. 플러그인만 바로 제거하면 기존 SW가 구버전 캐시를 계속 응답할 수 있음 |

## 10. 작업 순서

| 단계 | 작업 | 환경 |
|---|---|---|
| ① | 5절 파일 변경, 아이콘 생성, 11절 localhost 항목 검증 | localhost (AWS 작업과 병행 가능) |
| ② | AWS 병합 완료 후 `feature/pwa` rebase, `nginx.conf` 충돌 정리 → develop → main | AWS (HTTP 또는 HTTPS) |
| ③ | HTTPS 적용 후 실기기 설치·자동 갱신 검증 | AWS (HTTPS) |

## 11. 검증 항목

localhost (`npm run build && npm run preview`)
- [ ] `node --test "tests/*.test.mjs"`, `npm run build` 통과
- [ ] DevTools Application 탭에서 manifest 인식, 아이콘·이름 표시
- [ ] Service Worker 등록·활성화, precache 목록에 `/api/` 경로 없음
- [ ] Lighthouse에서 설치 가능(installable) 판정
- [ ] 오프라인 전환 후 새로고침 시 앱 셸 표시 (API 호출은 실패 메시지 정상 표시)
- [ ] 로그인·정책 검색·사업계획서 다운로드·엑셀 다운로드 정상 동작

AWS (HTTPS)
- [ ] `https://<도메인>`에서 Android Chrome 설치 프롬프트 표시·설치 후 `standalone` 실행
- [ ] iOS Safari 홈 화면 추가 후 실행
- [ ] `curl -I https://<도메인>/sw.js` 응답에 `Cache-Control: no-cache`
- [ ] 화면 문구 변경 커밋을 main에 병합 → deploy workflow 성공 → 설치된 앱 재실행 시 변경 반영
- [ ] `/ppt/` 접근 시 발표자료 정상 표시 (SW가 `index.html`로 가로채지 않음)
- [ ] `http://` 접속 시 `https://` 리다이렉트 후 SW 정상 등록
