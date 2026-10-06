# AWS 챕터 1 이슈 해결 보고서

작성일: 2026-10-06 · 대상: 배포·LLM 영역의 P0 이슈 ID 3, ID 4, ID 1, ID 2 · 상태: 해결 조치 완료 · 검증 종료(사용자 통보 기준)

## 1. 보고서 개요

`AWS_DEPLOY_RISK_REPORT_20261005.md`에서 확인한 챕터 1의 이슈를 대상으로, 원래 문제와 제안한 해결 방안, 실제 코드에 적용한 조치를 정리한다. 처리 순서는 ID 3 → ID 4 → ID 1 → ID 2이며, 각 ID의 수정 사항은 개별 커밋으로 기록했다.

코드 변경과 로컬 테스트는 구현 과정에서 확인했다. 운영 검증은 사용자가 직접 수행하고 종료를 통보한 상태로 기록한다. 운영 로그·실측값·최종 배포 SHA는 별도로 제공되지 않았으므로, 서버 메모리 한도·최대 사용량·복원 행 수 등의 구체적인 결과값은 기재하지 않는다. 원래 보고서의 위험 시나리오를 실제 발생 장애 이력으로 바꾸어 기록하지 않는다.

| 이슈 | 제안한 해결방안 | 실제 적용된 방법 | 상태 | 수정 커밋 |
|---|---|---|---|---|
| **ID 3 — 동시 실행 그룹에 의한 배포 대기 작업 취소**<br>새 요청이 기존 배포 대기를 취소할 수 있고, PR 테스트도 수집 때문에 대기하는 문제. | concurrency를 deploy job으로 이동해 PR 테스트를 분리.<br>수집 그룹 분리와 서버 `flock` 적용 검토.<br>보조 방안으로 재시도 주기 완화. | deploy job에만 concurrency 적용.<br>배포·수집·재시도는 같은 `ec2-app` 그룹을 유지하고 `queue: max` 적용.<br>`$HOME/.ec2-app.lock` 공통 잠금과 잔존 collector 검사 추가.<br>그룹 분리·재시도 주기 변경은 미적용. | 조치 완료·검증 종료 | `9785908` |
| **ID 4 — 백업 cron 무음 실패**<br>제한된 PATH 때문에 AWS CLI 실행이 실패하고, 백업 누락을 알기 어려운 문제. | cron PATH 보완 또는 AWS CLI 절대 경로 사용.<br>S3 객체 크기 검사와 실패 알림 추가.<br>별도 DB 복원 리허설 수행. | 스크립트 PATH 보완 및 cron 설정 안내 추가.<br>임시 덤프 생성·목차 검사 후 업로드하고 `head-object`로 크기 비교.<br>성공·실패 시각 기록, SNS 실패 알림, 26시간 기준 freshness 검사 추가.<br>중복 실행 잠금·임시 파일 정리 및 별도 DB 복원 절차 문서화. | 조치 완료·검증 종료 | `2e70af5` |
| **ID 1 — App EC2 메모리 부족**<br>서버 이미지 빌드와 LLM·OCR·수집·재색인 부하가 겹쳐 OOM·지연이 발생할 수 있는 문제. | CI에서 이미지 빌드 후 EC2는 pull만 수행.<br>메모리 한도 지정 및 인덱스·OCR warm-up 순차 실행.<br>필요 시 서버 증설·수집 환경 이전, ID 6 이중 초기화 해결 검토. | Actions에서 4개 App 이미지를 빌드해 GHCR에 게시하고 EC2는 `--no-build`로 실행.<br>`LLM_MEM_LIMIT` 필수화, 다른 서비스는 한도 설정 항목 제공.<br>인덱스 warm-up 종료 후 OCR warm-up 실행.<br>커밋 SHA·설정·DB/LLM/RAG 준비 상태 검사 추가.<br>증설·수집 이전·ID 6 해결은 이번 변경에 포함하지 않음. | 조치 완료·검증 종료 | `0f26b8d` |
| **ID 2 — 재색인 중 RAG 전체 중단**<br>기존 인덱스를 먼저 무효화해 새 인덱스 준비 중 상담이 실패할 수 있는 문제. | 기존 Dense·BM25를 유지하며 새 검색기를 별도로 구성.<br>성공 시 교체하고 실패 시 기존 상태 유지.<br>수집에서 변경 문서 ID만 전달하는 부분 재색인 검토. | 후보 `RagRuntime`에서 새 검색 상태를 구성하고 `publish_index()`로 준비 성공 시 교체.<br>무거운 구성을 작업 스레드에서 수행.<br>재색인 실패 시 기존 runtime과 진행 중 요청의 검색 참조 유지.<br>기존 부분 재색인 경로에도 적용하되, 수집 workflow의 변경 ID 추적은 추가하지 않음.<br>검색 DB의 과거 버전 보존·롤백은 미포함. | 조치 완료·검증 종료 | `ffc80dd` |

## 2. ID 3 — 동시 실행 그룹에 의한 배포 대기 작업 취소

### 2.1 이슈와 원인

배포·수집·재시도 workflow가 같은 `ec2-app` concurrency 그룹을 사용하면서 기본 대기열 정책에 의존했다. `cancel-in-progress: false`만으로는 기존 대기 작업이 새 요청에 의해 교체되는 상황을 막지 못했다.

수집 실행 중 배포가 대기하고 있을 때 재시도나 다른 요청이 들어오면 배포가 `Canceled`로 끝날 수 있었다. 또한 concurrency가 deploy workflow 전체에 적용되어, 운영 배포를 하지 않는 PR 테스트까지 수집 작업 때문에 대기할 수 있었다.

### 2.2 제안했던 해결 방안

- concurrency를 workflow 전체에서 실제 deploy job으로 이동해 PR 테스트를 분리한다.
- 수집 workflow의 그룹을 별도로 분리하고, 실제 서버 변경 작업은 `flock`으로 직렬 실행하는 방안을 검토한다.
- 보조 방안으로 재시도 주기를 완화한다.

### 2.3 실제 적용한 해결 방안

1. **배포 잠금 범위를 deploy job으로 이동했다.** PR 테스트와 이미지 빌드는 운영 작업의 concurrency 그룹에 포함되지 않는다.
2. **배포·수집·재시도에 동일한 `ec2-app` 그룹과 `queue: max`를 적용했다.** 그룹을 분리하는 대신 대기열을 확대하고, `cancel-in-progress: false`를 유지했다.
3. **세 workflow의 서버 작업 앞에 공통 파일 잠금을 추가했다.** `$HOME/.ec2-app.lock`에 `flock -w 300`을 사용하여 잠금 획득 후 git 갱신과 Docker 작업을 진행한다. 잠금 대기 시간이 초과되면 오류를 반환한다.
4. **이전 collector 잔존 여부를 검사했다.** SSH 작업 취소 후 collector가 남아 있으면 다음 서버 변경 작업을 중단하고 오류를 표시한다.
5. **수동 작업도 같은 잠금을 사용하도록 가이드를 보완했다.**

최종 구현에서는 수집 그룹 분리와 재시도 주기 변경을 적용하지 않았다. Actions 단계에서 운영 작업을 함께 대기시키고, 서버에서는 공통 잠금으로 중복 실행을 방지하는 구성을 선택했다.

### 2.4 변경 후 동작과 검증

- 운영 작업은 대기열에 남아 순차 실행하고, 새 요청에 의한 기존 대기 취소 위험을 줄인다.
- PR 테스트는 운영 작업의 concurrency 대기열에서 제외한다. runner 가용성에 의한 일반 대기는 별개다.
- Actions 밖에서 시작한 수동 작업도 동일 잠금을 사용하면 서버 작업과 충돌하지 않는다.
- 잔존 collector나 잠금 timeout은 명시적인 실패로 표시한다.

운영 검증 항목은 수집·배포·재시도 중첩 시 대기 유지, PR 테스트 독립 실행, 서버 잠금, 최신 배포 반영이다. 검증 종료 상태는 사용자 통보를 기준으로 기록했다.

### 2.5 적용 파일 및 커밋

- [.github/workflows/deploy.yml](../../.github/workflows/deploy.yml)
- [.github/workflows/collect.yml](../../.github/workflows/collect.yml)
- [.github/workflows/collect-retry.yml](../../.github/workflows/collect-retry.yml)
- [Docs/AWS_DEPLOY_GUIDE.md](../AWS_DEPLOY_GUIDE.md)

커밋: `9785908` — `fix: ID3 배포·수집 대기 취소 및 동시 실행 방지`

## 3. ID 4 — 백업 cron 무음 실패

### 3.1 이슈와 원인

AWS CLI가 `/snap/bin/aws`에 설치되어 있어도 cron의 제한된 PATH에 `/snap/bin`이 없으면 백업이 `aws: command not found`로 실패할 수 있었다. 로그인 셸에서의 수동 실행은 성공할 수 있어 문제를 놓치기 쉬웠다.

실패 결과가 서버 로그에만 남아 백업 누락을 즉시 알기 어려웠고, 업로드 파일의 기본 검증과 실제 복원 가능성 확인도 보완이 필요했다.

### 3.2 제안했던 해결 방안

- cron PATH에 AWS CLI 경로를 추가하거나 AWS CLI 절대 경로를 사용한다.
- 업로드 후 S3 객체 크기를 검사하고 실패 시 알림을 보낸다.
- 별도 DB에서 복원 리허설을 수행한다.

### 3.3 실제 적용한 해결 방안

1. **백업 스크립트 자체에 실행 경로를 보완했다.** PATH에 `/snap/bin`, `/usr/local/bin`, `/usr/bin`, `/bin`을 추가하고, 가이드의 crontab에도 PATH를 명시했다. `AWS_BIN`은 기본 `aws`를 유지하며 필요 시 지정할 수 있다.
2. **덤프를 임시 파일로 생성해 업로드 전에 검사한다.** `pg_dump -Fc`로 생성한 파일이 비어 있지 않은지 확인하고 `pg_restore --list`로 목차를 검사한다. 덤프 생성·검사가 실패하면 업로드하지 않는다.
3. **업로드 후 S3 크기를 비교한다.** `s3api head-object`의 `ContentLength`와 로컬 덤프 크기가 같아야 백업 성공으로 기록한다.
4. **성공·실패 시각을 분리해서 기록한다.** 전체 검사를 통과한 뒤에만 `last_success`를 갱신한다. 오류가 발생하면 `last_failure`를 남기며 이전 성공 시각을 성공한 것처럼 갱신하지 않는다.
5. **실패 알림을 추가했다.** `BACKUP_ALERT_TOPIC_ARN`이 설정된 경우 SNS 알림을 전송한다. 알림 미설정·전송 실패도 stderr에 표시한다.
6. **백업 누락 감지를 추가했다.** `--check-freshness`가 마지막 성공 백업의 나이를 검사한다. 기본 기준은 26시간이며, 가이드에 매시간 실행하는 cron을 추가했다. 이 검사가 실행되면 백업 cron 자체가 실행되지 않은 상황도 감지할 수 있다.
7. **백업 중복 실행과 임시 파일 처리를 보완했다.** `flock -n`으로 중복 실행을 차단하고, 종료 시 임시 덤프를 정리한다. `umask 077`을 사용한다.
8. **실제 복원 절차와 서버 수동 설정 항목을 문서화했다.** SNS 구독 확인·IAM 권한·Data EC2 스크립트 반영·cron 설정·별도 DB 복원은 운영 설정 및 검증 단계로 구분했다.
9. **셸 파일의 LF 줄바꿈 규칙을 추가했다.** Windows 환경에서 작성한 셸 스크립트의 Linux 실행을 위해 `.gitattributes`에 `scripts/*.sh text eol=lf`를 지정했다.

최종 구현에서는 AWS CLI 경로를 단일 절대 경로로 고정하는 대신 PATH를 보완했다. S3 객체 검사는 `aws s3 ls` 대신 `head-object`로 수행하고, 제안 범위에 백업 누락 검사와 성공 시각 관리까지 추가했다.

### 3.4 변경 후 동작과 검증

- 제한된 cron 환경에서도 AWS CLI를 찾을 수 있다.
- 덤프 생성·목차 검사·업로드·크기 검사 중 하나라도 실패하면 성공 기록을 갱신하지 않는다.
- 실패 또는 마지막 성공 백업의 지연을 외부 알림으로 전달할 수 있다.
- `backup verified`와 실제 복원 성공은 구분한다. 목차·크기 검사가 데이터 전체의 복원 가능성을 대신하지 않는다.

로컬에서는 fake Docker·AWS를 사용한 백업 회귀 테스트 6개가 통과했다. 성공 처리 순서, 덤프·업로드·크기 검사 실패 시 성공 기록 보존, freshness 판정·알림 경로를 확인했다.

운영 검증 항목은 제한된 PATH에서의 백업, freshness 검사, 누락 시험 알림, S3 덤프의 별도 DB 복원, cron 자동 실행이다. 검증 종료 상태는 사용자 통보를 기준으로 기록했다.

### 3.5 적용 범위와 파일

스크립트·가이드 변경과 실제 SNS·IAM·cron 설정은 구분한다. App 배포만으로 Data EC2의 설정이 자동 반영되는 구조는 추가하지 않았다. 서버 설정의 개별 값은 본 보고서에 제공되지 않았다.

- [scripts/backup_db.sh](../../scripts/backup_db.sh)
- [scripts/tests/test_backup_db.py](../../scripts/tests/test_backup_db.py)
- [.env.example](../../.env.example)
- [.gitattributes](../../.gitattributes)
- [Docs/AWS_DEPLOY_GUIDE.md](../AWS_DEPLOY_GUIDE.md)

커밋: `2e70af5` — `fix: ID4 백업 cron 경로 및 덤프 검증·실패 알림 보완`

## 4. ID 1 — App EC2 메모리 부족

### 4.1 이슈와 원인

보고서 기준 App EC2는 4GB 메모리 환경에서 LLM·backend·frontend·presentation을 함께 실행하고, 수집과 재색인도 수행하는 구성이었다. LLM에는 OCR 모델과 메모리 BM25 검색기가 포함되어 있었다.

EC2에서 직접 Docker 이미지를 빌드하면 운영 서비스와 빌드가 자원을 경쟁한다. 기동 시 검색 인덱스 준비와 OCR 모델 로드가 동시에 시작되면 메모리 피크가 겹칠 수 있었다. 재색인과 수집도 부하를 추가하며 LLM 메모리 제한이 없어 OOM·강제 종료·swap 지연으로 이어질 위험이 있었다.

### 4.2 제안했던 해결 방안

- 이미지를 GitHub Actions에서 빌드하고 EC2는 레지스트리에서 pull한다.
- LLM 중심으로 메모리 한도를 지정한다.
- 인덱스와 OCR warm-up을 순차 실행한다.
- 필요하면 App EC2를 증설하거나 수집을 다른 실행 환경으로 이동한다.
- 관련 ID 6의 이중 초기화를 후속 해결 대상으로 검토한다.

### 4.3 실제 적용한 해결 방안

1. **이미지 빌드를 GitHub Actions로 이동했다.** backend·frontend·llm·presentation을 `linux/amd64` 이미지로 빌드하고 GHCR에 게시한다. 이미지 태그는 배포 대상 커밋의 SHA를 사용한다.
2. **App compose를 이미지 실행 방식으로 변경했다.** App 서비스의 `build` 설정을 제거하고 `APP_IMAGE_REGISTRY`·`APP_IMAGE_TAG`로 이미지를 지정한다. EC2는 이미지를 pull하고 `up --no-build --wait`로 실행한다.
3. **배포 스크립트를 추가했다.** `scripts/deploy_app.sh`에서 커밋 일치·설정 검증, 이미지 pull, 기존 DB migration, 컨테이너 실행, 준비 상태 검사를 순서대로 수행한다. 최신 main이 아닌 배포 요청은 건너뛰고, 실제 배포 시 checkout SHA와 이미지 SHA가 일치하는지 확인한다.
4. **LLM 메모리 한도를 필수 설정으로 만들었다.** `LLM_MEM_LIMIT`이 없으면 migration이나 컨테이너 교체 전에 compose 검사에서 중단한다. 운영 실측으로 값을 정하도록 했으며 임의의 기본 한도는 넣지 않았다.
5. **다른 서비스에도 메모리 설정 항목을 제공했다.** backend·frontend·presentation·collector의 한도는 설정 가능하며 기본값 0은 제한 없음이다. 모든 서비스에 양수 한도를 자동 지정한 것은 아니다.
6. **기동 warm-up 순서를 변경했다.** 하나의 `_warm_up_all()` 작업이 인덱스 준비 작업 종료를 기다린 뒤 OCR warm-up을 시작한다. 기존의 두 warm-up 작업을 동시에 시작하는 흐름을 제거했다. 인덱스 준비 실패는 로그에 남기며 OCR 준비는 이후 진행될 수 있다.
7. **배포 성공 판정을 강화했다.** HTTP 200만 확인하지 않고 backend health 응답의 `postgres=connected`, `llm=connected`, `ragReady=true`까지 검사한다. 준비 실패는 명시적인 배포 실패로 처리한다.
8. **배포 인증 정보를 임시로 관리했다.** GHCR 인증은 임시 Docker 설정 디렉터리에서 사용하고 종료 시 정리한다. 배포 토큰을 운영 `.env`에 저장하지 않는다.

### 4.4 최초 제안과 실제 적용 범위

| 방안 | 이번 변경의 적용 여부 |
|---|---|
| CI 빌드·GHCR pull 배포 | 적용 |
| LLM 메모리 한도 필수화 | 적용, 실제 운영 값은 별도 설정 |
| 인덱스·OCR warm-up 순차 실행 | 적용 |
| 다른 서비스 메모리 한도 | 설정 항목 제공, 기본 제한 없음 |
| presentation 필요 시 실행 | 기존 profile 방식 유지 |
| App EC2 증설 | 이번 코드 변경에 포함하지 않음 |
| 수집 실행 환경 이전 | 이번 코드 변경에 포함하지 않음 |
| ID 6 이중 초기화 해결 | 후속 챕터 범위 |

운영 인스턴스 변경 여부·최종 메모리 설정값은 별도 내역이 제공되지 않아 기록하지 않는다.

### 4.5 변경 후 동작과 검증

- App 이미지 빌드가 EC2에서 제거되어 빌드와 운영 서비스 간 자원 경쟁을 줄인다.
- 자동 warm-up의 인덱스 구성과 OCR 로드가 동시에 시작되지 않는다.
- LLM의 메모리 한도를 운영 설정에서 관리한다.
- 컨테이너 시작뿐 아니라 DB·LLM·RAG 준비까지 확인한 뒤 배포 성공을 출력한다.

로컬에서는 배포 스크립트 회귀 테스트 5개가 통과했다. 설정·pull 실패 시 migration 이전 중단, SHA 불일치, migration 실패, 서비스 실행 순서, readiness 실패 경로를 확인했다. warm-up 순서 회귀 테스트와 Linux LLM 이미지 빌드·Django check·OCR 준비도 검증했다.

운영 검증 항목은 배포 이미지·SHA, 메모리 한도, 기동·OCR·수집·재색인 중 사용량, OOM·재시작, 실제 응답이다. 검증 종료 상태는 사용자 통보를 기준으로 기록했다. 현재 부하 조건에서의 확인이 향후 데이터 증가·동시 요청 증가까지 보장하는 것은 아니다.

### 4.6 적용 파일 및 커밋

- [.github/workflows/deploy.yml](../../.github/workflows/deploy.yml)
- [docker-compose.app.yml](../../docker-compose.app.yml)
- [scripts/deploy_app.sh](../../scripts/deploy_app.sh)
- [scripts/tests/test_deploy_app.py](../../scripts/tests/test_deploy_app.py)
- [LLM/src/serving/django_config/asgi.py](../../LLM/src/serving/django_config/asgi.py)
- [LLM/tests/test_django_serving.py](../../LLM/tests/test_django_serving.py)
- [.env.example](../../.env.example)
- [Docs/AWS_DEPLOY_GUIDE.md](../AWS_DEPLOY_GUIDE.md)

커밋: `0f26b8d` — `fix: ID1 EC2 빌드 제거 및 LLM 메모리 피크 완화`

## 5. ID 2 — 재색인 중 RAG 전체 중단

### 5.1 이슈와 원인

기존 `_prepare_index()`는 재색인을 시작하면서 운영 runtime의 인덱스를 먼저 무효화했다. 새 검색기가 준비될 때까지 상담은 `RagIndexNotReadyError`로 실패할 수 있었다.

수집·재시도·관리자 재색인 중 검색을 사용하는 정책·세무·로드맵 상담이 중단되고, backend가 오류 응답을 목업 답변으로 처리할 위험이 있었다. 무거운 BM25 구성이 요청 처리 흐름을 막는 문제도 함께 고려해야 했다.

### 5.2 제안했던 해결 방안

- 기존 Dense·BM25 검색기를 유지하면서 새 검색기를 별도로 준비한다.
- 준비 성공 시에만 운영 검색 상태를 교체한다.
- 준비 실패 시 기존 검색 상태를 유지한다.
- 수집에서 변경 문서 ID만 전달하는 부분 재색인을 검토한다.
- 기존·새 BM25가 잠시 공존하는 메모리 피크를 ID 1과 함께 확인한다.

### 5.3 실제 적용한 해결 방안

1. **재색인 시작 시 기존 인덱스를 무효화하는 동작을 제거했다.** 새 인덱스 준비 중에도 기존 runtime을 사용할 수 있게 했다.
2. **별도의 후보 `RagRuntime`에서 새 검색 상태를 구성한다.** Dense 검색기·Hybrid/BM25 검색기·문서 수·청크 수·검색 설정을 후보 runtime에 준비한다.
3. **무거운 구성을 작업 스레드에서 수행한다.** 인덱스 로드·DB 검색기 생성·BM25 구성 등을 `asyncio.to_thread()`로 실행해 서버 이벤트 루프를 오래 점유하지 않도록 했다.
4. **`publish_index()`로 준비된 상태를 교체한다.** 후보가 준비되었는지 확인하고 짧은 cache lock 구간에서 운영 검색 참조와 관련 메타데이터를 함께 교체한다.
5. **진행 중인 요청은 확보한 기존 그래프·검색기를 계속 사용한다.** 교체 후 새로운 요청은 새 검색 상태로 그래프를 구성한다.
6. **실패 시 기존 runtime을 보존한다.** 재색인 요청 자체는 오류를 반환한다. 기존 인덱스가 없는 최초 준비 실패는 미준비 상태로 유지한다.
7. **기존 부분 재색인 경로에도 같은 준비·교체 방식을 적용했다.** 양수 documentIds를 사용하는 PostgreSQL 부분 재색인과 전체 재색인 모두 후보 상태를 준비한 후 반영한다.
8. **실패·동시 처리 회귀 테스트를 보완했다.** 지연된 BM25 구성 중 기존 검색 상태 유지, 성공 후 교체, 재색인 실패 후 상담, 초기 실패 상태를 확인한다.

### 5.4 최초 제안과 실제 적용 범위

수집 workflow가 변경된 문서 ID를 새로 추적해서 전달하는 구조는 추가하지 않았다. 수집 workflow는 기존의 `documentIds=[]`, `force=false` 호출을 유지한다. 이 호출은 기존 임베딩을 재사용하고 신규·변경 청크를 반영하는 흐름이다. 특정 ID를 전달하는 부분 재색인 기능 자체는 기존에 있었으며, 이번에는 해당 경로의 runtime 교체도 보완했다.

이번 변경은 검색 runtime의 가용성을 유지한다. PostgreSQL 원본·rag_documents·pgvector 데이터를 이전 버전으로 보존하거나 롤백하는 기능은 추가하지 않았다. DB 변경 후 후속 검색기 구성이 실패하는 경우까지 검색 데이터의 버전 일치를 보장하려면 별도 staging/version 관리가 필요하다.

### 5.5 변경 후 동작과 검증

- 기존 인덱스가 준비된 상태라면 재색인 중에도 검색 요청을 처리한다.
- 새 검색 상태가 준비된 후 교체하므로 준비 공백을 만들지 않는다.
- 재색인 실패는 요청 오류로 드러내면서 기존 검색 runtime을 유지한다.
- 새 컨테이너의 최초 인덱스 준비 시간이나 컨테이너 교체 중 중단을 없애는 무중단 배포 기능은 포함하지 않는다.

최종 LLM 회귀 테스트는 518개가 통과했다. 지연된 구성 중 기존 상태 유지, 성공 시 교체, 초기 실패, 재색인 실패 후 기존 상담 성공을 테스트에 반영했다.

운영 검증 항목은 재색인 전·중·후 준비 상태, 처리 중 실제 검색 상담, 완료 후 변경 문서 반영이다. 실패 경로는 로컬 회귀 테스트에서 확인했으며, 운영 실패 주입의 개별 실행 내역은 제공되지 않았다. 검증 종료 상태는 사용자 통보를 기준으로 기록했다.

### 5.6 적용 파일 및 커밋

- [LLM/src/serving/rag_routes.py](../../LLM/src/serving/rag_routes.py)
- [LLM/tests/test_index_publication.py](../../LLM/tests/test_index_publication.py)
- [LLM/tests/test_rag_api.py](../../LLM/tests/test_rag_api.py)
- [LLM/tests/test_django_serving.py](../../LLM/tests/test_django_serving.py)
- [Docs/AWS_DEPLOY_GUIDE.md](../AWS_DEPLOY_GUIDE.md)

커밋: `ffc80dd` — `fix: ID2 재색인 중 기존 RAG 검색 상태 유지`

## 6. 검증 및 해결 범위 정리

| 구분 | 기록된 결과 또는 확인 방식 |
|---|---|
| 백업 스크립트 로컬 회귀 테스트 | 6개 통과, 실제 Docker·AWS 호출 대신 fake 사용 |
| 배포 스크립트 로컬 회귀 테스트 | 5개 통과, 실제 운영 배포 대신 fake 사용 |
| 최종 LLM 회귀 테스트 | 518개 통과, warm-up·재색인 테스트 포함 |
| Linux LLM 이미지 | 빌드 및 Django check 확인, OCR 준비 검증 |
| 운영 검증 | 사용자가 직접 수행하고 종료 통보 |
| 운영 상세 수치·원시 로그 | 본 보고서에 제공되지 않아 수치 기재 생략 |

챕터 1은 배포 작업의 취소·충돌 방지, 백업 실패·누락 감지, EC2 빌드 제거와 메모리 피크 완화, 재색인 중 검색 runtime 유지에 대한 조치를 완료했다.

자동 rollback, 검색 데이터의 버전 보존, 무중단 배포, ID 6 등 후속 챕터 이슈는 이번 해결 범위에 포함하지 않는다. 기존 migration SQL을 새로 수정한 것은 아니지만 실제 배포에서는 기존 migration이 실행되며, 재색인도 검색용 DB 데이터를 갱신할 수 있다.

## 7. 관련 문서

- [원래 AWS 배포 위험 보고서](AWS_DEPLOY_RISK_REPORT_20261005.md)
- [챕터 1 운영 검증 및 병합 점검](AWS_CHAPTER1_OPERATIONAL_VERIFICATION_20261006.md)
- [AWS 배포 가이드](../AWS_DEPLOY_GUIDE.md)

운영 검증 문서의 '대기' 표기는 작성 당시 상태다. 이후 사용자 검증 종료 통보에 따른 상태는 본 해결 보고서를 기준으로 한다.
