# AWS 배포 위험 이슈 보고서

작성일: 2026-10-05 · 대상: `develop`(`4f096f1`) · 상태: 정적 분석 + 재검토(2차), 테스트·빌드 실행 확인. EC2 실측·코드 수정 없음

**`develop`을 `Docs/AWS_DEPLOY_GUIDE.md` 구성으로 실배포했을 때 발생 가능한 문제 30건을 원인·해결 방안과 함께 정리했다. 장애·배포 실패로 직결되는 P0가 4건이며, 이 중 ③·④는 설정 몇 줄로 해결 가능하다. 2차 재검토에서 10건을 추가하고 2건의 등급을 낮췄다(6절).**

## 1. 점검 전제

| 항목 | 내용 |
| --- | --- |
| App EC2 | t3.medium(2 vCPU, 4GB) + swap 2GB, 디스크 30GB. frontend·backend·llm·presentation, 배포 시 이미지 직접 빌드, 수집(collector)도 여기서 실행 |
| Data EC2 | t3.large(8GB), 디스크 40GB. Postgres(pgvector)·Elasticsearch |
| 배포 | `main` push → `.github/workflows/deploy.yml` → SSH로 `git pull` → `db-migrate` → `up -d --build` |
| 수집 | `collect.yml`(매주 월 03:00 KST), `collect-retry.yml`(3시간마다) |
| 저장소 | GitHub **공개** 저장소(Actions 로그·workflow 정의 공개) |
| main 대비 주요 변경 | 영수증 OCR PP-OCRv5(paddle) 교체, 모바일 앱·`/web.html` 추가, LLM Retriever·세무 캐시 변경 |
| 방법 | 코드·compose·workflow·운영 스크립트 정적 점검 + 로컬 테스트·빌드 실행(7절). EC2 실측·장애 재현은 하지 않음 |

### 등급 기준

| 등급 | 기준 |
| --- | --- |
| P0 | 서비스 중단, 배포 실패, 데이터 유실로 직결 |
| P1 | 서비스는 동작하나 기능 오류·잘못된 데이터·장애 장기화 발생 |
| P2 | 공격·악용·설정 실수 시 보안 사고·개인정보·비용 피해 |
| P3 | 성능 저하, 운영 불편 |

## 2. 요약

| ID | 등급 | 이슈 | 영향 | 조치 난이도 |
| --- | --- | --- | --- | --- |
| 1 | P0 | App EC2 메모리 부족 | 컨테이너 강제 종료, 배포 실패 | 중 |
| 2 | P0 | 재색인 중 RAG 전체 중단 | 수집·배포마다 상담 503 → 목업 답변 | 중 |
| 3 | P0 | 동시 실행 그룹에 의한 배포 무단 취소 | main 병합 후 미배포, PR 체크 장시간 대기 | 하 |
| 4 | P0 | 백업 cron 무음 실패 | 백업 미생성, 장애 시 복구 불가 | 하 |
| 5 | P1 | App EC2 디스크 고갈 | 빌드·기동 실패 | 하 |
| 6 | P1 | 배포마다 RAG 인덱스 이중 빌드 | 중단 구간·메모리 사용 증가 | 하 |
| 7 | P1 | CI의 LLM 미검증 | 깨진 LLM 이미지가 운영 서버에서 처음 발견 | 하 |
| 8 | P1 | 영수증 OCR 지연·목업 저장 | 잘못된 지출 데이터 저장, LLM 요청 전반 지연 | 중 |
| 9 | P1 | 시간대(UTC) 어긋남 | 00~09시(KST) D-day·마감·지출일 오류 | 하 |
| 10 | P1 | 세무 답변 캐시 미갱신 | 세법 개정 미반영 답변, 질의 지연 | 중 |
| 11 | P1 | 모바일 영수증 업로드 제약 | 휴대폰 원본 사진 거부, 판정 유실 | 중 |
| 12 | P1 | 장애 감지·자동 복구 없음 | 장애 장기화, 인지 지연 | 중 |
| 13 | P1 | 프런트·Backend 타임아웃 불일치 | 성공한 작업도 실패로 표시, LLM 비용 낭비 | 하 |
| 14 | P2 | LangSmith로 개인정보 외부 전송 | 질문·프로필·영수증 이미지 국외 SaaS 저장 | 하 |
| 15 | P2 | 데모 계정 운영 노출 | 무단 로그인, 데이터 오염, LLM 비용 | 하 |
| 16 | P2 | 요청 횟수 제한 없음 | 무차별 대입, LLM 비용 폭증 | 중 |
| 17 | P2 | 약한 비밀번호 저장·가입 검증 | DB 유출 시 즉시 크래킹, 대량 가입 | 중 |
| 18 | P2 | 업로드 압축 폭탄 | LLM 메모리 고갈 → 전체 AI 기능 중단 | 중 |
| 19 | P2 | 서드파티 Action 태그 참조 | 태그 변조 시 EC2 SSH 키 유출 | 하 |
| 20 | P2 | 롤백 수단 없음 | 잘못된 배포 복구에 수십 분 | 중 |
| 21 | P2 | 토큰 폐기 불가 | 로그아웃 후에도 토큰 7일 유효 | 중 |
| 22 | P2 | 비밀값 노출 범위 과다 | 컨테이너 침해 시 피해 확대 | 하 |
| 23 | P3 | Backend DB 연결 풀 없음 | 응답 지연, 연결 수 한도 근접 | 중 |
| 24 | P3 | 빌드 비결정성 | 예고 없는 빌드 실패 | 하 |
| 25 | P3 | 무중단 배포 불가 | 배포마다 502·RAG 불가 구간 | 상 |
| 26 | P3 | Elasticsearch 미사용 상시 구동 | 자원 낭비, 문서와 실제 동작 불일치 | 하 |
| 27 | P3 | `/web.html` 캐시 헤더 누락 | Service Worker 미동작 환경에서 빈 화면 | 하 |
| 28 | P3 | nginx 압축·HTTP/2·보안 헤더 없음, 상태 API 정보 노출 | 첫 로딩 지연, 내부 주소 노출 | 하 |
| 29 | P3 | 배포 후 열린 탭의 동적 import 실패 | Excel 내보내기 실패 | 하 |
| 30 | P3 | 외부 API 시간 제한·품질 저하 감지 없음 | 응답 지연, 검색 품질 저하 무감지 | 하 |

## 3. P0 — 장애·배포 실패 직결

### ① App EC2 메모리 부족

**현상** 배포 중 또는 기동 직후 llm 컨테이너가 OOM으로 종료되거나, swap 사용으로 응답이 느려져 healthcheck 실패 → `up -d` 실패.

**원인**
- 4GB 서버에 llm(paddle 런타임 + PP-OCRv5 모델 3개 + LangGraph + 원본 문서 전체를 올린 메모리 BM25) + backend + nginx + presentation 상주
- 배포 시 같은 서버에서 LLM 이미지(약 4.8GB, paddle 포함) 빌드 → 운영 컨테이너와 메모리 경합
- 첫 HTTP 요청에서 인덱스 warm-up과 OCR 모델 로드를 동시에 시작(`LLM/src/serving/django_config/asgi.py:42-47`), 여기에 ⑥의 이중 빌드가 겹침
- 매주 월 03:00 collector 컨테이너(의존성 설치 포함)가 App EC2에서 돌고, 이어서 재색인으로 BM25를 다시 구성
- `docker-compose.app.yml`에 컨테이너별 메모리 상한 없음 → 커널이 가장 큰 프로세스(llm)부터 종료
- 부수 효과: t3 기본 unlimited 모드에서 빌드·OCR로 기준 CPU를 계속 넘으면 추가 과금

**해결 방안**
- 단기: compose에 `mem_limit` 지정(llm 우선 보호, presentation은 필요할 때만 기동), OCR warm-up을 인덱스 준비 완료 뒤 순차 실행, ⑥ 해결
- 근본: 이미지를 GitHub Actions에서 빌드해 GHCR에 올리고 EC2는 `pull`만 수행, 또는 App EC2를 t3.large로 상향. 수집은 Data EC2 또는 별도 실행 환경으로 이동 검토

**검증** 배포·수집 전후 `free -h`, `docker stats --no-stream`, `dmesg | grep -i oom` 확인.

### ② 재색인 중 RAG 전체 중단

**현상** 수집·재시도·배포 직후 일정 시간 동안 상담(세무·정책·로드맵)이 503 → Backend가 목업 답변 저장.

**원인**
- `_prepare_index`가 재색인 시작 시 `invalidate_index()`로 검색기·그래프를 먼저 비움(`LLM/src/serving/rag_routes.py:491-492`, `invalidate_index`는 같은 파일 186-191행)
- 새 인덱스 구성이 끝날 때까지 모든 RAG 요청이 `RagIndexNotReadyError`
- 발생 시점: 매주 월 03:00 수집, 재시도 대상이 있을 때 3시간마다, 관리자 재색인, 배포로 llm이 재생성될 때마다(⑥으로 2회)

**해결 방안**
- 기존 인덱스를 유지한 채 새 Dense·BM25 인덱스를 별도로 만들고, 성공 시에만 교체(실패 시 기존 유지). 무효화는 "구성 실패 + 기존 인덱스 없음"일 때만 적용
- 수집 workflow는 변경된 문서만 `documentIds`로 부분 재색인
- 단, 메모리 BM25 두 벌이 잠시 공존하므로 ①과 함께 메모리 여유 확인 필요

**검증** `docker compose exec -T llm curl -X POST localhost:8001/rag/reindex ...` 실행 중 `/api/health`의 `ragReady`와 채팅 응답 확인.

### ③ 동시 실행 그룹에 의한 배포 무단 취소

**현상** `main` 병합 후 deploy run이 `canceled`로 끝나고 운영에 반영되지 않음. 실패가 아니라서 알아채기 어려움. 수집 중에는 PR 체크도 최대 2시간 대기.

**원인**
- `deploy.yml`·`collect.yml`·`collect-retry.yml`이 같은 concurrency 그룹 `ec2-app` 사용
- GitHub Actions는 그룹당 실행 1개 + 대기 1개만 유지. 공식 문서: "By default, any existing pending job or workflow in the same concurrency group will be canceled and the new queued job or workflow will take its place." (`cancel-in-progress: false`도 대기 취소는 막지 못함)
- `deploy.yml`의 concurrency가 **workflow 단위**(`deploy.yml:14-16`)라 `pull_request` 이벤트의 테스트 run도 같은 그룹에 들어감
- 결과 시나리오
  - 수집(최대 120분) 실행 중 deploy 대기 → 3시간 주기 collect-retry가 대기열에 들어오면 deploy 취소
  - main 배포가 대기 중일 때 다른 PR에 push → PR 테스트 run이 대기열을 차지하며 deploy 취소

**해결 방안**
- concurrency를 workflow 단위에서 **deploy job 단위**로 옮겨 PR 테스트는 그룹에서 제외
- 수집 2종은 별도 그룹(예: `ec2-collect`)으로 분리하고, 서버 측 동시 실행은 배포·수집 스크립트 앞 `flock /tmp/ec2-app.lock`으로 방지
- 보조: collect-retry 실행 주기 완화(예: 6시간)

**검증** collect 수동 실행 중 deploy → collect-retry·PR push 순으로 트리거해 deploy가 취소되지 않는지 Actions에서 확인.

### ④ 백업 cron 무음 실패

**현상** S3 `daily/`에 백업이 생기지 않는데 알림이 없음. 장애 시 복구할 덤프 부재.

**원인**
- 가이드 4절에서 aws CLI를 snap으로 설치 → 실행 파일 `/snap/bin/aws`
- cron 기본 PATH는 `/usr/bin:/bin` → `aws: command not found`, `pipefail`로 스크립트 실패(`scripts/backup_db.sh:23-24`)
- 가이드 10절의 1회 수동 실행은 로그인 셸이라 성공 → 문제를 발견하기 어려움
- 실패 결과는 `~/backup_db.log`에만 기록

**해결 방안**
- crontab 상단에 `PATH=/snap/bin:/usr/local/bin:/usr/bin:/bin` 추가, 또는 스크립트에서 `AWS_BIN="${AWS_BIN:-/snap/bin/aws}"` 절대경로 사용
- 업로드 후 `aws s3 ls`로 객체 크기 확인, 실패 시 알림(⑫와 통합)
- 월 1회 복원 리허설

**검증** `env -i /bin/sh -c 'PATH=/usr/bin:/bin bash scripts/backup_db.sh'`로 cron 환경 재현.

## 4. P1 — 기능 오류·데이터 정확성·장애 장기화

### ⑤ App EC2 디스크 고갈

**현상** 이미지 빌드 실패(`no space left on device`), 컨테이너 기동 실패.

**원인**
- 교체된 이미지(dangling)는 매 배포 `docker image prune -f`로 정리되나, 빌드 캐시는 7일 보존(`.github/workflows/deploy.yml:63`) → `uv.lock` 변경 시마다 수 GB 의존성 레이어가 캐시에 누적
- Docker json-file 로그에 크기 제한 없음 → 장기 운영 시 로그 누적
- 1차 보고에서 P0로 분류했으나, 정리 로직이 있어 의존성 변경 빈도·운영 기간에 좌우되므로 P1로 조정

**해결 방안**
- compose 각 서비스에 `logging: { driver: json-file, options: { max-size: "10m", max-file: "3" } }`
- 배포 스크립트 끝에 `df -h /` 사용률 확인, 임계치(예: 80%) 초과 시 workflow 경고
- 빌드 캐시 보존 기간 단축(예: `until=48h`), 근본적으로는 ①의 레지스트리 pull 전환

**검증** `docker system df`, `df -h /`를 배포 전후 비교.

### ⑥ 배포마다 RAG 인덱스 이중 빌드

**현상** llm이 재생성되는 배포마다 인덱스를 두 번 구성 → ②의 중단 구간이 길어지고 ①의 메모리 피크가 커짐.

**원인**
- llm은 첫 HTTP 요청(healthcheck)에서 자체 인덱스 warm-up 시작(`LLM/src/serving/django_config/asgi.py:45-47`)
- llm이 healthy가 되면 backend가 기동하면서 `ensure_index_ready()` 실행(`Backend/config/api.py:49-53`) → warm-up이 아직 진행 중이라 미준비로 판단 → `reindex()` 호출(`Backend/core/llm_client.py:87-94`)
- `/rag/reindex`는 `allow_ready_shortcut=False`(`rag_routes.py:449-461`) → lock 대기 후 warm-up이 막 끝낸 인덱스를 다시 무효화·재구성

**해결 방안**
- 단기: Backend 워밍업을 "준비 여부 확인만" 하도록 변경하거나, 재색인 대신 `/internal/rag/index`(`create_index`, 준비 시 `already_ready` 반환) 호출
- 근본: 인덱스 준비 책임을 llm 기동 warm-up 하나로 통일

**검증** 배포 후 llm 로그에서 `LLM index warm-up` 1회 + 재색인 요청 없음 확인.

### ⑦ CI의 LLM 미검증

**현상** LLM 코드·의존성 오류가 운영 EC2 빌드·기동 단계에서 처음 발견됨.

**원인**
- `deploy.yml` test job은 Backend unittest와 Frontend 테스트·빌드만 실행. LLM pytest와 Docker 이미지 빌드는 없음
- develop의 대규모 LLM 변경(OCR 엔진 교체, graph, tax_cache, paddle 의존성)이 검증 없이 배포 대상
- 이미지 빌드 중 PP-OCR 모델을 외부에서 다운로드(`LLM/Dockerfile`의 PaddleOCR `RUN`) → 외부 장애 시 배포 실패
- 배포 순서상 `db-migrate`가 빌드보다 먼저 실행 → 빌드 실패 시 새 스키마 + 이전 코드 상태로 남음

**해결 방안**
- test job에 `LLM`: `uv run pytest` 추가(외부 키가 필요한 live 테스트는 제외 마커)
- `docker build ./LLM` 빌드 검증 추가(또는 ①의 레지스트리 빌드와 통합)
- 배포 순서를 `build` → `db-migrate` → `up -d`로 변경

**검증** PR에서 test job에 LLM 단계가 실행되고 실패 시 merge가 차단되는지 확인. 현재 LLM 테스트 상태는 7절 참고.

### ⑧ 영수증 OCR 지연·목업 저장

**현상** 영수증 업로드 응답 지연, 타임아웃 시 실제 영수증 대신 목업 값(`노트`, `펜`, 오늘 날짜)이 지출로 저장. OCR 처리 중 다른 LLM 요청도 느려짐.

**원인**
- PP-OCR 경로에 시간 제한 없음(Tesseract 경로에만 25초 예산 존재, `LLM/src/features/receipt_ocr.py:40`)
- 전역 `_paddle_lock`으로 모든 OCR 요청을 직렬 처리(`receipt_ocr.py:83`, `188`)
- lock을 기다리는 요청이 `asyncio.to_thread` 기본 스레드 풀(2 vCPU → `min(32, cpu+4)` = 6개)을 점유 → 검색·DB 등 다른 LLM 작업 대기
- OCR + LLM 정리 + (실패 시) Vision 재호출이 Backend `LLM_TIMEOUT_OCR=40s`(`Backend/core/config.py:81`)를 넘기면 목업 저장(`Backend/services/expense_service.py:315-320`)
- 성능 근거(`Docs/OCR_PPOCRV5_BENCHMARK.md`)는 개발 PC 측정, t3.medium 미측정

**해결 방안**
- OCR 전용 단일 스레드 executor로 분리하고 대기열 상한 초과 시 즉시 503("잠시 후 다시") 반환
- PP-OCR 입력 이미지를 긴 변 2000px로 축소(⑱ 방어 겸용), 시간 예산 초과 시 Vision 경로로 전환
- Backend는 LLM 타임아웃 시 목업 저장 대신 업로드 실패로 응답(사용자 재시도)
- t3.medium에서 1장·동시 3장 처리 시간 실측 후 타임아웃 재설정

**검증** t3.medium에서 4MB 영수증 2~3건 동시 업로드, 응답 시간과 저장된 `source` 값 확인.

### ⑨ 시간대(UTC) 어긋남

**현상** 한국 시간 00:00~09:00 사이에 마감 D-day, 마감 임박 표시, 공고 남은 일수, 지출일 기본값이 하루 어긋나고 알림 도달 판정이 9시간 늦음.

**원인**
- 컨테이너 시간대 미설정(기본 UTC), `USE_TZ=False`
- `date.today()`·`datetime.now()` 직접 사용: `Backend/services/calendar_service.py:34,98-99,109`, `policy_service.py:85,148,179`, `expense_service.py:287,317`, `notify_service.py:25`, `tax_service.py:69`
- 로컬 개발(Windows, KST)에서는 재현되지 않음

**해결 방안**
- backend·llm·collector 서비스에 `TZ: Asia/Seoul` 환경변수 지정(compose 3개 파일). 공식 `python:*-slim` 이미지는 `tzdata`를 포함하므로 Dockerfile 변경 불필요
- Postgres `now()` 기반 컬럼과 비교하는 쿼리가 있으면 DB `timezone`도 `Asia/Seoul`로 일치

**검증** `docker compose exec backend python -c "import datetime;print(datetime.datetime.now())"`가 KST인지 확인.

### ⑩ 세무 답변 캐시 미갱신

**현상** 주간 수집으로 세법이 바뀌어도 이전에 캐시된 답변을 계속 반환. 캐시가 커질수록 세무 질의 지연.

**원인**
- `tax_rag_cache`에 만료·삭제 로직 없음(negative evidence 6시간 TTL만 존재, `LLM/src/rag/tax_cache.py:30`)
- `question_embedding`에 벡터 인덱스 없음(`DB/app_extras.sql:54-61`) → 유사 질문 조회가 매번 전체 스캔

**해결 방안**
- 수집 workflow에서 세법 원본이 바뀐 경우 캐시 삭제(또는 원본 버전·해시를 캐시 키에 포함)
- `created_at` 기준 TTL(예: 30일) 적용
- `app_extras.sql`에 `CREATE INDEX IF NOT EXISTS ... USING hnsw (question_embedding vector_cosine_ops)` 추가(재실행 안전)

**검증** 세법 원본 1건 수정 → 수집·재색인 → 같은 질문의 캐시 적중 여부 확인. `EXPLAIN`으로 인덱스 사용 확인.

### ⑪ 모바일 영수증 업로드 제약

**현상** 휴대폰 카메라 원본 사진이 "4MB 이하만" 안내와 함께 거부. 모바일에서 한 인정·불인정 판정이 새로고침 후 사라짐.

**원인**
- 업로드 전 압축 없이 4MB 제한(`Frontend/src/mobile/MExpenses.jsx:80`)
- 수동 판정 저장 API 없음, 화면 상태만 변경(같은 파일 101-102행 TODO)

**해결 방안**
- 업로드 전 canvas로 긴 변 2000px JPEG 변환(OCR이 어차피 2000px로 축소하므로 인식률 영향 없음)
- 판정 저장 API(`PATCH /expenses/{id}` 등) 추가 전까지 판정 버튼 비노출 또는 "저장되지 않음" 안내

**검증** 최신 휴대폰 원본 사진(4MB 초과) 업로드 성공, 판정 후 새로고침 시 유지 확인.

### ⑫ 장애 감지·자동 복구 없음

**현상** llm이 멈추거나(예: OCR 추론 정지로 lock 영구 점유) DB 연결이 끊겨도 아무도 모른 채 장애 지속. 사용자는 목업 답변만 받음.

**원인**
- compose `restart: unless-stopped`는 **프로세스 종료** 시에만 재시작. healthcheck가 `unhealthy`여도 Docker는 재시작하지 않음
- 외부 가용성 감시(헬스 URL 주기 호출), 알림(메일·Slack), 로그 수집(CloudWatch 등) 구성이 가이드·코드에 없음
- 목업 대체(fallback)가 오류를 사용자 화면에서 가려 장애 인지가 더 늦어짐
- ④ 백업 실패, ③ 배포 취소, 수집 실패도 같은 이유로 알림 경로 없음(수집은 Actions 실패 메일만)

**해결 방안**
- 외부 헬스 체크: `/api/health`의 `ragReady`·`postgres`를 1~5분 간격 확인(UptimeRobot 등 무료 서비스 또는 CloudWatch Synthetics) → 실패 시 알림
- `unhealthy` 자동 재시작: autoheal 컨테이너 또는 cron에서 `docker ps --filter health=unhealthy` 확인 후 재시작
- CloudWatch Agent로 컨테이너 로그·메모리·디스크 수집, 임계치 알람(①·⑤와 연계)
- Backend 목업 대체 횟수를 로그 지표로 집계

**검증** llm 컨테이너를 `docker pause`로 멈춘 뒤 알림 수신·자동 복구 여부 확인.

### ⑬ 프런트·Backend 타임아웃 불일치

**현상** 사업계획서 진단·정리·양식 검사·출력에서 프런트는 실패로 표시하지만 서버는 작업을 계속해 LLM 비용만 소모. 재시도 시 중복 호출.

**원인**

| 기능 | 프런트 제한 | Backend → LLM 제한 |
| --- | --- | --- |
| 사업계획서 evaluate·refine·template-inspect·render | 70초(`Frontend/src/api.js:375-379`) | 120초(`LLM_TIMEOUT_BIZPLAN`, `Backend/core/config.py:76`) |
| 공고 원문 요약(POST) | 30초(기본값, `api.js:361`) | 45초(`LLM_TIMEOUT_SUMMARIZE`, `config.py:75`) |
| 창업 감면 확인 | 30초(기본값, `api.js:338`) | 30초(`LLM_TIMEOUT_LEGAL_BASIS`, `config.py:73`) + DB 처리 |

- 기존 주석(`config.py:77-80`)이 경고한 문제("프런트가 먼저 포기") 원칙이 OCR에만 적용되고 다른 기능에는 미적용
- ⑧·①로 서버가 느려지는 AWS 환경에서 경계 구간 진입 빈도 증가

**해결 방안**
- 원칙 통일: 프런트 제한 = Backend → LLM 제한 + 여유(10초 이상)
- 사업계획서 계열은 프런트 130초 또는 Backend 60초 중 실측 기반으로 한쪽에 맞춤
- 장시간 작업은 비동기 작업(작업 ID 발급 → 상태 조회) 전환 검토

**검증** LLM 응답을 인위적으로 지연(테스트 더블)시켜 프런트 표시와 서버 처리 결과가 일치하는지 확인.

## 5. P2 — 보안·개인정보·비용

### ⑭ LangSmith로 개인정보 외부 전송

**현상** 사용자 질문, 나이·지역·업종 등 프로필, 사업계획서 내용, 영수증 이미지가 외부 SaaS(LangSmith)에 trace로 저장.

**원인**
- 로컬 `.env`가 `LANGSMITH_TRACING=true`, `LANGSMITH_HIDE_INPUTS=false`, `LANGSMITH_HIDE_OUTPUTS=false`(값 존재 여부만 확인)
- 가이드 8절은 "로컬 `.env` 전체를 복사"하도록 안내 → 운영에서도 그대로 추적 활성화
- Vision 대체 경로는 영수증 원본을 base64 data URL로 LLM에 전달(`LLM/src/rag/backend_tasks.py:895-929`) → trace에 이미지 포함
- 이용약관·개인정보 처리방침에 국외 이전·제3자 처리 고지 없음

**해결 방안**
- 운영 `.env`는 `LANGSMITH_TRACING=false`가 기본. 디버깅으로 켜야 하면 `LANGSMITH_HIDE_INPUTS/OUTPUTS=true`
- 가이드 8절을 "로컬 `.env` 복사" 대신 운영용 키 목록(`.env.example` 기준) 작성으로 변경
- 이미 전송된 trace는 LangSmith 프로젝트에서 삭제

**검증** 운영 llm 컨테이너에서 `env | grep LANGSMITH_TRACING`이 `false`, LangSmith 프로젝트에 신규 trace 없음 확인.

### ⑮ 데모 계정 운영 노출

**현상** 누구나 `demo@demo.com / demo123`으로 로그인해 데이터 열람·수정, LLM 기능 사용. 공개 저장소에도 계정 정보가 그대로 있음.

**원인**
- Backend 기동마다 데모 계정이 없으면 생성(`Backend/core/db.py:209`)
- 공개 Swagger(`/api/docs`) 설명에 계정 정보 노출(`Backend/core/config.py:32`)

**해결 방안**
- `SEED_DEMO` 환경변수로 시드 제어, AWS `.env`는 비활성화
- 운영 DB의 기존 데모 계정 `status='suspended'` 처리
- 운영에서 `/api/docs` 비공개(nginx 차단 또는 `docs_url` 조건부)

**검증** 운영에서 데모 계정 로그인 403, `/api/docs` 접근 차단 확인.

### ⑯ 요청 횟수 제한 없음

**현상** 관리자·사용자 계정 무차별 대입 가능. 가입만 하면 LLM 기능을 무제한 호출해 OpenAI·Cohere 비용 폭증.

**원인**
- nginx `limit_req` 없음(`Frontend/nginx-locations.conf`), Backend 로그인 실패 횟수 제한 없음
- 관리자 이메일 기본값 `admin@demo.com`(`Backend/core/config.py:59`)이 공개 저장소에 노출되어 대상 계정 추측 불필요

**해결 방안**
- nginx `limit_req_zone`: `/api/auth/`·`/api/admin/auth/` 엄격, `/api/chat/`·`/api/bizplan/`·`/api/expenses/receipts` 중간
- 운영 `ADMIN_EMAIL`은 추측하기 어려운 값으로 지정
- 사용자별 일일 LLM 호출 상한(구독 플랜과 연계 가능)
- OpenAI·Cohere 콘솔 월 사용 한도·알림 설정

**검증** 로그인 연속 요청 시 429 확인.

### ⑰ 약한 비밀번호 저장·가입 검증

**현상** DB 덤프·백업 유출 시 레인보우 테이블로 다수 비밀번호 즉시 복원. 가짜 이메일로 계정 대량 생성 가능.

**원인**
- `hashlib.sha256(password)` 단일 해시, 솔트 없음(`Backend/core/security.py:10-15`)
- 가입 비밀번호 최소 4자, 이메일 형식 검증·본인 인증 없음(`Backend/schemas/auth.py:4-8`)

**해결 방안**
- 표준 라이브러리 `hashlib.pbkdf2_hmac`(솔트 + 반복) 또는 argon2로 교체, 해시 문자열에 알고리즘 접두사 포함
- 로그인 성공 시 구 해시를 새 방식으로 재저장해 점진 이전
- 비밀번호 최소 8자, 이메일 형식 검증. 이메일 인증은 ⑯의 요청 제한과 함께 검토

**검증** 기존 계정 로그인 성공 + 로그인 후 DB 해시 형식 변경 확인, 단위 테스트 추가.

### ⑱ 업로드 압축 폭탄

**현상** 로그인 사용자가 작은 파일 하나로 llm 컨테이너 메모리를 고갈시켜 상담·OCR·사업계획서 전체 중단(①과 결합 시 OOM).

**원인**
- 영수증: 크기는 4MB만 검사. 단색 PNG는 4MB 이하로도 1억 픽셀 이상 가능하며, PIL 기본 한도는 약 1.79억 픽셀 초과에서만 차단 → 디코딩 RGB 수백 MB + PP-OCR 경로의 BGR 사본(`receipt_ocr.py:187`)까지 축소 없이 생성
- 사업계획서 양식: HWPX(zip)는 압축 상태 크기 4MB만 검사(`LLM/src/features/business_plan_documents.py:34,150`), 압축 해제 크기 제한 없음

**해결 방안**
- 이미지: 디코딩 전 `Image.open` 후 `width*height` 상한(예: 4000만 픽셀) 검사, PP-OCR 전 긴 변 2000px 축소(⑧과 동일 조치)
- HWPX: `zipfile.ZipFile.infolist()`로 항목 수·해제 크기 합계 상한(예: 50MB) 검사 후 파싱
- ① 컨테이너 `mem_limit`로 피해를 llm 한 곳에 한정

**검증** 고해상도 단색 PNG(4MB 이하)·압축률 높은 HWPX 업로드 시 4xx 반환, 메모리 사용량 변화 없음 확인.

### ⑲ 서드파티 Action 태그 참조

**현상** 서드파티 Action의 태그가 변조되면 EC2 SSH 키가 유출되어 서버 장악 가능(docker 그룹 = root 동등 권한).

**원인**
- `deploy.yml`·`collect.yml`·`collect-retry.yml`이 `appleboy/ssh-action@v1`(이동 가능한 태그)에 `EC2_SSH_KEY`를 전달
- 저장소가 공개 상태라 사용 Action·서버 접근 방식이 외부에 공개
- SSH 22 포트가 `0.0.0.0/0`으로 열려 있어(가이드 2절) 키만 있으면 어디서든 접속

**해결 방안**
- 서드파티 Action은 커밋 SHA로 고정(`appleboy/ssh-action@<sha>`), Dependabot으로 갱신
- 배포 키를 `authorized_keys`에서 `command=`(배포 스크립트만 실행)·`from=`(GitHub Actions IP 대역) 옵션으로 제한
- 장기적으로 SSM Run Command 등 SSH 없는 배포로 전환

**검증** workflow 파일에 `@v`·`@main` 형태의 서드파티 참조가 없는지 확인.

### ⑳ 롤백 수단 없음

**현상** 배포 후 기능 오류 발견 시 이전 버전으로 즉시 되돌릴 수 없음. revert PR + CI + 재빌드까지 수십 분 장애 지속.

**원인**
- `up -d --build`로 같은 이미지 이름을 덮어쓰고, 이전 이미지는 `docker image prune -f`로 삭제(`deploy.yml:60-61`)
- 이미지에 커밋 태그가 없어 특정 버전 지정 불가
- `db-migrate`는 전진 전용(되돌리는 스크립트 없음)

**해결 방안**
- 이미지에 커밋 SHA 태그 부여(①의 레지스트리 빌드와 통합), 직전 N개 태그 보존
- 롤백 workflow(`workflow_dispatch`, 입력: 태그) 추가 → `pull` 후 `up -d`
- 스키마 변경은 "추가만 하고 삭제는 다음 배포" 원칙(구 코드와 호환) 문서화

**검증** 롤백 workflow로 직전 태그 복귀 후 `/api/health` 정상 확인.

### ㉑ 토큰 폐기 불가

**현상** 로그아웃해도 기존 토큰이 7일간 유효. 토큰 탈취 시 차단 수단 없음(계정 정지 제외).

**원인** 서명 토큰만 검증, `/auth/logout`이 빈 응답만 반환(`Backend/api/auth.py:21-23`), TTL 7일(`Backend/core/config.py:51`). 토큰은 브라우저 `localStorage`에 저장(`Frontend/src/api.js:27-30`).

**해결 방안**
- `users.token_version` 컬럼 추가 → 토큰에 포함, 로그아웃·비밀번호 변경 시 증가해 기존 토큰 무효화
- TTL 단축(예: 1일)

**검증** 로그아웃 후 이전 토큰으로 API 호출 시 401 확인.

### ㉒ 비밀값 노출 범위 과다

**현상** llm 컨테이너 침해 시 Backend 토큰 서명키·관리자 비밀번호까지 유출.

**원인** llm 서비스에 `.env` 전체 주입(`docker-compose.app.yml:57-58`) → `TOKEN_SECRET`·`ADMIN_PASSWORD`·수집 API 키 포함.

**해결 방안** llm은 필요한 키(OpenAI·Cohere·LangSmith·RAG 설정)만 `environment`로 전달하거나 LLM 전용 env 파일 분리.

**검증** `docker compose exec llm env | grep -E 'TOKEN_SECRET|ADMIN_PASSWORD'` 결과 없음 확인.

## 6. P3 — 성능·운영 품질

### ㉓ Backend DB 연결 풀 없음

**현상** API 응답마다 수~수십 ms 추가 지연, 동시 접속 증가 시 Postgres 연결 수 한도(기본 100)에 근접.

**원인**
- 쿼리마다 `psycopg.connect`로 Data EC2에 새 TCP 연결(`Backend/core/db.py:41-59`, `127-139`)
- `/health` 1회에 DB 연결 2~3개 + LLM 호출 2회, healthcheck가 10초마다 호출

**해결 방안** LLM이 이미 쓰는 `psycopg_pool.ConnectionPool` 방식(`LLM/src/core/database.py`)을 Backend `connection()`에 재사용.

**검증** `SELECT count(*) FROM pg_stat_activity`를 부하 전후 비교, API 응답 시간 비교.

### ㉔ 빌드 비결정성

**현상** 코드 변경 없이도 어느 날 빌드 실패 또는 동작 변화.

**원인** `COPY --from=ghcr.io/astral-sh/uv:latest`(Backend·LLM `Dockerfile`) 태그 미고정.

**해결 방안** uv 이미지 태그를 특정 버전으로 고정, 갱신은 PR로 진행.

**검증** Dockerfile에 `:latest` 미사용 확인.

### ㉕ 무중단 배포 불가

**현상** 배포마다 수십 초~수 분간 502 또는 RAG 미준비.

**원인** 단일 인스턴스에서 `up -d --build`로 컨테이너 재생성 + llm 기동 후 인덱스 재구성(②·⑥).

**해결 방안**
- ②(인덱스 교체 방식)·⑥(이중 빌드 제거)·①(레지스트리 pull)로 중단 구간 단축
- 시연·사용 시간대를 피한 배포 원칙, 근본적으로는 2대 이상 + 로드밸런서 구성(비용 증가)

**검증** 배포 중 1초 간격 `/api/health` 호출로 중단 시간 측정.

### ㉖ Elasticsearch 미사용 상시 구동

**현상** Data EC2에서 ES가 heap 1GB를 상시 점유하나 서비스 검색에는 쓰이지 않음. 문서·workflow 주석은 ES 재색인을 전제로 서술.

**원인**
- 서빙 검색은 Postgres Dense + 메모리 `BM25Search`(`LLM/src/serving/rag_routes.py:214-244`). `load_elasticsearch_source_documents`도 Postgres만 조회
- ES는 평가 스크립트(`LLM/evaluation/`)에서만 사용
- `collect.yml` 주석, 가이드 8절·10-1절은 ES 재색인 전제

**해결 방안**
- ES 유지 여부 결정. 미사용 시 `docker-compose.data.yml`에서 profile로 분리해 기본 기동 제외
- `collect.yml` 주석, `Docs/AWS_DEPLOY_GUIDE.md`, `Docs/Design/ARCHITECTURE.md`의 ES 서술 정정

**검증** ES 중지 상태에서 `/api/health`의 `ragReady=true`, 상담 정상 동작 확인.

### ㉗ `/web.html` 캐시 헤더 누락

**현상** Service Worker가 동작하지 않는 환경(일부 인앱 브라우저, SW 차단 설정 등)에서 배포 후 웹앱 빈 화면. 강력 새로고침 시 정상.

**원인**
- nginx 재검증(`no-cache`) 대상에 `index.html`만 포함(`Frontend/nginx-locations.conf:26`) → `web.html`은 브라우저 휴리스틱 캐시
- 1차 보고에서 P1로 분류했으나, HTTPS에서는 SW가 revision을 붙인 precache로 `web.html`과 asset을 일관되게 제공하므로 영향 범위가 SW 미동작 환경으로 한정 → P3로 조정

**해결 방안** 정규식에 `web\.html` 추가: `^/(sw\.js|registerSW\.js|manifest\.webmanifest|index\.html|web\.html)$`

**검증** `curl -I https://<DOMAIN>/web.html` 응답에 `Cache-Control: no-cache` 확인.

### ㉘ nginx 압축·HTTP/2·보안 헤더 없음, 상태 API 정보 노출

**현상** 모바일 첫 로딩과 PWA 갱신이 느림. 공개 상태 API로 내부 구성 정보 노출.

**원인**
- `nginx:1.29-alpine` 기본 설정은 gzip 비활성, 저장소 설정에도 `gzip` 지시어 없음. 7절 빌드 결과 기준 메인 JS 383KB(gzip 시 131KB), CSS 174KB(gzip 시 32KB)를 무압축 전송. SW precache 1.6MB(사용하지 않는 exceljs 939KB 포함)도 배포마다 무압축 다운로드
- `listen 443 ssl`만 있고 `http2 on` 없음, HSTS·`X-Content-Type-Options` 등 보안 헤더 없음(`Frontend/nginx.https.conf`)
- 인증 없는 `/api/health`가 Data EC2 주소·포트·DB명(`dbPath`), LLM URL, 정책 수를 반환(`Backend/config/api.py:56-78`)

**해결 방안**
- `gzip on; gzip_types text/css application/javascript application/json image/svg+xml;`, `http2 on;`
- `add_header Strict-Transport-Security "max-age=31536000" always;` 등 기본 보안 헤더
- 공개 `/health`는 `status`·`ragReady`만, 상세는 관리자 모니터링 API로 이동
- exceljs를 precache 대상에서 제외(`globIgnores`)하고 사용할 때만 다운로드

**검증** `curl -sI -H 'Accept-Encoding: gzip' https://<DOMAIN>/assets/<main>.js`에 `Content-Encoding: gzip`, `/api/health` 응답에 내부 주소 없음 확인.

### ㉙ 배포 후 열린 탭의 동적 import 실패

**현상** 배포 전부터 열어 둔 탭·설치 앱에서 지출 Excel 내보내기 실패("Failed to fetch dynamically imported module"). 새로고침하면 정상.

**원인**
- Excel 내보내기만 동적 import 사용(`Frontend/src/pages/ExpenseTracker.jsx:10-12`)
- 새 이미지에는 이전 해시 chunk가 없고, `/assets/`는 `try_files` 없이 404(`nginx-locations.conf:32-35`). 새 SW 활성화(autoUpdate) 시 이전 precache도 정리됨

**해결 방안** 동적 import 실패 시 1회 자동 새로고침(또는 "새 버전이 있습니다" 안내) 처리.

**검증** 탭을 연 상태로 재배포 후 Excel 내보내기 동작 확인.

### ㉚ 외부 API 시간 제한·품질 저하 감지 없음

**현상** OpenAI 지연 시 LLM 요청이 오래 붙잡힘. Cohere 한도 초과·장애 시 검색 품질이 조용히 떨어짐.

**원인**
- `ChatOpenAI`·`OpenAIEmbeddings`에 `timeout` 미지정(`LLM/src/models/factory.py:33-36,85-88`) → SDK 기본값(수 분) 적용
- Cohere 재정렬 실패 시 RRF 결과로 대체하고 경고 로그만 남김(`LLM/src/rag/graph.py:896-900`). 성능 보고서 수치는 재정렬 성공 전제
- `RAG_TROUBLESHOOTING_FIX_REPORT_20261002.md`에서 Cohere 429 문제를 범위 제외로 남겨 둠

**해결 방안**
- 모델 생성 시 `timeout`(예: 60초)·`max_retries` 명시
- 재정렬 대체 횟수를 지표로 집계해 ⑫ 알림에 연결, 운영용 Cohere 키 한도 확인

**검증** 재정렬 대체 로그 건수를 일 단위로 확인.

## 7. 실행 검증 결과

로컬(Windows)에서 CI와 같은 명령으로 실행. 빌드 산출물은 저장소 밖에 생성.

| 대상 | 명령 | 결과 |
| --- | --- | --- |
| Backend | `uv run python -m unittest discover tests` | 134개 통과(skip 5) |
| Frontend 테스트 | `node --test "tests/*.test.mjs"` | 9개 통과 |
| Frontend 빌드 | `vite build` | 성공. 메인 JS 383KB(gzip 131KB), CSS 174KB(gzip 32KB), exceljs 939KB, SW precache 16개 1.6MB |
| LLM | `uv run pytest` | 514개 통과 |

- 현재 `develop`은 세 영역 테스트가 모두 통과한다. ⑦은 "지금 실패한다"가 아니라 "CI가 LLM 테스트·이미지 빌드를 돌리지 않아 이후 회귀를 막지 못한다"는 의미다
- Docker 이미지 빌드(paddle 설치·PP-OCR 모델 다운로드), t3.medium 메모리·시간 실측은 로컬 Docker 미구동으로 확인하지 못했다

## 8. 확인 후 제외한 항목

| 의심 항목 | 제외 근거 |
| --- | --- |
| Backend sync 뷰가 단일 스레드로 전역 직렬화 | Django ASGI가 요청마다 `ThreadSensitiveContext` 생성(`django/core/handlers/asgi.py`) → 요청별 스레드 |
| paddlepaddle 3.2.2의 Python 3.13 휠 부재 | `LLM/uv.lock`에 `cp313` manylinux 휠 존재 |
| Elasticsearch 장애 시 RAG 전체 중단 | 서빙 경로가 ES를 쓰지 않음(㉖) |
| 수집 로그(Actions, 공개)에 API 키 노출 | 공통 `request()`가 예외 메시지에서 URL을 빼고 예외 종류만 기록(`DB/scripts/collect_common.py:76-106`) |
| 저장소 이력의 비밀값 커밋 | `.env` 커밋 이력·키 패턴 없음 |
| 프런트 XSS(LLM 답변 렌더링) | Markdown을 React 요소로 렌더, `dangerouslySetInnerHTML` 없음(`Frontend/src/components/Markdown.jsx`) |
| 다른 사용자 리소스 접근(IDOR) | 지출·영수증·사업계획서 API가 `request.auth["id"]`로 소유자 검사 |
| 알림 발송 로직 | GET `/notifications`가 전체 사용자 알림을 동기 처리·중복 발송 가능하고 SMTP도 미설정이나, 프런트에서 호출하지 않아 현재 영향 없음. 화면 연결 시 스케줄러 분리 필요 |
| 상담 목업 답변 오인 | 목업 답변에 "근거 문서를 확인하지 못한 참고 안내" 문구와 `llmUsed=false` 표시(`Backend/services/chat_service.py:305-324`) |

## 9. 재검토(2차) 변경 사항

| 구분 | 내용 |
| --- | --- |
| 신규 | ⑥ 인덱스 이중 빌드, ⑫ 장애 감지 없음, ⑬ 타임아웃 불일치, ⑭ LangSmith 외부 전송, ⑱ 압축 폭탄, ⑲ Action 태그 참조, ⑳ 롤백 없음, ㉘ nginx 압축·헤더·정보 노출, ㉙ 동적 import, ㉚ 외부 API |
| 등급 조정 | ⑤ 디스크 P0 → P1(정리 로직 존재), ㉗ `/web.html` P1 → P3(SW precache가 완화) |
| 보강 | ③ PR 테스트 run도 같은 그룹(공식 문서 인용), ① 수집 동시 실행·CPU 과금, ⑨ slim 이미지 tzdata 포함 확인, ⑯·⑰ 관리자 기본 이메일·가입 검증 |
| 철회(1차) | Elasticsearch 단일 장애점 |

## 10. 권장 처리 순서

| 순서 | 대상 | 이유 |
| --- | --- | --- |
| 1 | ③ ④ ⑨ ⑭ ⑮ | 설정 몇 줄 수준, 영향 큼 |
| 2 | ① ⑤ ⑥ ⑦ ⑫ ⑳ | 배포 안정화. 레지스트리 빌드 전환으로 ①·⑤·⑦·⑳ 함께 해결 가능 |
| 3 | ② ⑧ ⑩ ⑪ ⑬ | 기능 정확성, 코드 변경 필요 |
| 4 | ⑯ ⑰ ⑱ ⑲ ㉑ ㉒ | 보안 강화 |
| 5 | ㉓~㉚ | 성능·정리 |
