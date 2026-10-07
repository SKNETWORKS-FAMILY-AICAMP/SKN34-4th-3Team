# AWS 배포 가이드

> 이 문서는 AWS 콘솔에서 직접 수행하는 단계별 절차. 구성 개요는 `Docs/Design/ARCHITECTURE.md` 4절. 처음에는 도메인 없이 Elastic IP + HTTP로 배포하고 HTTPS는 12절에서 적용하는 순서로 작성했다.
>
> **현재 코드 상태(2026-10-07):** 12-4절의 HTTPS 구성(`Frontend/nginx.https.conf`, `docker-compose.app.yml` frontend의 `443`·`/etc/letsencrypt` 마운트)과 PWA는 이미 `main`에 반영돼 있다. 따라서 App EC2를 새로 띄울 때는 **8절 `up` 전에 12-1~12-3절(도메인·443 보안그룹·인증서 발급)을 먼저 끝내야 한다.** 인증서가 없으면 frontend(nginx)가 기동하지 못한다.

## 구성 요약

| 구분 | App EC2 | Data EC2 |
|---|---|---|
| 서브넷 | Public (Elastic IP) | Private (NAT Gateway 경유 외부 통신) |
| compose | `docker-compose.app.yml` | `docker-compose.data.yml` |
| 컨테이너 | frontend(nginx :80/:443), backend, llm, presentation(선택), `run --rm`으로만 실행: db-migrate(배포마다), collector(수집, 9-1절) | db(startup_db), elasticsearch |
| 권장 유형 | t3.medium (4GB) + swap 2GB | t3.large (8GB) |

리전은 서울(ap-northeast-2) 기준. 아래 `<APP_EIP>`는 App EC2의 Elastic IP, `<DATA_IP>`는 Data EC2의 private IP.

## 1. VPC

VPC 콘솔 → **VPC 생성** → **VPC 등(VPC and more)**

| 항목 | 값 |
|---|---|
| 이름 태그 | `startup-on` |
| 가용 영역(AZ) 수 | 1 |
| 퍼블릭 서브넷 수 | 1 |
| 프라이빗 서브넷 수 | 1 |
| NAT 게이트웨이 | 1개의 AZ에서 |
| VPC 엔드포인트 | S3 게이트웨이 (무료. 백업 트래픽이 NAT를 거치지 않음) |

## 2. 보안그룹

EC2 콘솔 → 보안 그룹 → 생성 (VPC는 `startup-on-vpc`)

| 이름 | 인바운드 | 비고 |
|---|---|---|
| `sg-app` | TCP 80 ← `0.0.0.0/0` | 서비스 접속 |
| | TCP 443 ← `0.0.0.0/0` | HTTPS. 도메인 확보 후 추가 (12절) |
| | TCP 22 ← `0.0.0.0/0` | GitHub Actions 배포용. IP가 고정되지 않아 전체 허용, 키 인증만 사용 |
| `sg-data` | TCP 5432 ← `sg-app` | Postgres |
| | TCP 9200 ← `sg-app` | Elasticsearch |
| | TCP 22 ← `sg-app` | App EC2 경유 SSH만 허용 |

## 3. S3 버킷 + IAM 역할

1. S3 → 버킷 생성: 예) `startup-on-backup-<팀명>` (퍼블릭 액세스 차단 유지)
2. 버킷 → 관리 → **수명 주기 규칙**: 접두사 `daily/`, 30일 후 만료
3. IAM → 역할 생성 → 신뢰 대상 EC2 → 인라인 정책

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
       "Resource": ["arn:aws:s3:::<버킷>", "arn:aws:s3:::<버킷>/*"]
     }]
   }
   ```
   역할 이름 예) `startup-on-data-role`

## 4. EC2 생성

공통: AMI **Ubuntu Server 24.04 LTS (x86_64)**, 키 페어 신규 생성(`startup-on.pem`, 관리자 보관)

| 항목 | App EC2 | Data EC2 |
|---|---|---|
| 유형 | t3.medium | t3.large |
| 서브넷 | 퍼블릭 | 프라이빗 |
| 퍼블릭 IP 자동 할당 | 비활성화 (Elastic IP 연결) | 비활성화 |
| 보안그룹 | `sg-app` | `sg-data` |
| 스토리지 | 30GB gp3 (이미지 빌드 공간) | 40GB gp3 (DB·ES 데이터) |
| IAM 인스턴스 프로파일 | 없음 | `startup-on-data-role` |

생성 후 EC2 → 탄력적 IP → 할당 → App EC2에 연결.

### Docker 설치 (두 인스턴스 공통)

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit   # 재접속 후 docker 명령 사용 가능
```

### App EC2 전용: swap 2GB (LLM 이미지 빌드 중 메모리 부족 방지)

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Data EC2 전용: aws CLI, Elasticsearch 커널 설정

```bash
sudo snap install aws-cli --classic
echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-elasticsearch.conf
sudo sysctl --system
```

## 5. 접속 방법

```bash
# App EC2
ssh -i startup-on.pem ubuntu@<APP_EIP>
# Data EC2 (App EC2 경유)
ssh -i startup-on.pem -J ubuntu@<APP_EIP> ubuntu@<DATA_IP>
```

`-J`로 경유할 때 키가 로컬에만 있으면 `ssh-add startup-on.pem` 후 `ssh -A -J ...`로 실행.

## 6. Data EC2 기동

```bash
git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-3Team.git
cd SKN34-4th-3Team
```
비공개 저장소면 GitHub 저장소 → Settings → Deploy keys에 읽기 전용 키를 등록해 SSH 주소로 clone.

`.env` 작성 (저장소 루트, `.env.example`의 해당 항목)

```
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
DATA_BIND_IP=<DATA_IP>
BACKUP_BUCKET=<버킷>
```

```bash
docker compose -f docker-compose.data.yml up -d --build
docker compose -f docker-compose.data.yml ps   # db, elasticsearch 모두 healthy 확인
```

## 7. 데이터 이전

로컬 PC(데이터가 있는 환경)에서 덤프 후 App EC2를 경유해 전달.

```bash
docker compose exec -T db pg_dump -U <user> -Fc <db> > startup_platform.dump
scp -i startup-on.pem -J ubuntu@<APP_EIP> startup_platform.dump ubuntu@<DATA_IP>:~/
```

Data EC2에서 복원

```bash
docker exec -i startup_db pg_restore -U <user> -d <db> --clean --if-exists < ~/startup_platform.dump
aws s3 cp ~/startup_platform.dump s3://<버킷>/migration/   # 원본 보관
```

복원 후 App EC2에서 스키마를 최신 `main` 기준으로 맞춤

App용 compose는 8절의 `APP_IMAGE_REGISTRY`·`APP_IMAGE_TAG`·실측한 `LLM_MEM_LIMIT`이 있어야 해석된다. migration만 실행할 때도 먼저 해당 설정을 작성한다.

```bash
# App EC2
cd ~/SKN34-4th-3Team
docker compose -f docker-compose.app.yml run --rm db-migrate
```

- DB 전체 교체(`pg_restore --clean`, `dropdb`·`createdb` 후 복원) 뒤에는 반드시 실행. 덤프 원본 DB에 없던 테이블·컬럼이 빠진 채 운영되는 것을 막음(재실행 안전)
- 덤프는 최신 `main`의 `DB/app_extras.sql`이 적용된 DB에서 생성. 로컬 DB는 덤프 전에 `docker compose up -d db-migrate`로 스키마를 갱신

## 8. App EC2 기동

```bash
git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-3Team.git
cd SKN34-4th-3Team
```

`.env` 작성: 로컬 `.env` 전체(LLM API 키, `TOKEN_SECRET` 등)를 복사하고 아래 항목 추가

```
COMPOSE_DB_HOST=<DATA_IP>
COMPOSE_DB_PORT=5432
COMPOSE_ES_PORT=9200
COMPOSE_PROFILES=presentation   # 발표자료가 필요 없으면 비움
APP_IMAGE_REGISTRY=ghcr.io/sknetworks-family-aicamp/skn34-4th-3team
APP_IMAGE_TAG=<main CI에서 게시 완료한 40자리 커밋 SHA>
LLM_MEM_LIMIT=<운영 실측으로 정한 한도, 예: 단위 m 또는 g>
ADMIN_PASSWORD=<관리자 비밀번호>   # 필수. 없으면 compose 실행 실패
LAW_API_KEY=<국가법령정보 OC>       # collector(수집)용. 9-1절
GOV24_API_KEY=<공공데이터포털 serviceKey>
ONTONG_YOUTH_API_KEY=<온통청년 API 키>
```

`ADMIN_PASSWORD`는 backend 기동 시 관리자 계정(`ADMIN_EMAIL`, 기본 `admin@demo.com`)에 적용. 기존 DB에 남은 옛 비밀번호도 이 값으로 갱신됨.

`.env`의 `ELASTICSEARCH_URL`은 `docker-compose.app.yml`이 `http://<COMPOSE_DB_HOST>:9200`으로 덮어씀.

> frontend는 항상 `nginx.https.conf`(443, `/etc/letsencrypt/live/changeup/`)로 뜬다. 인증서가 없으면 12-1~12-3절을 먼저 수행한다.

```bash
docker compose -f docker-compose.app.yml pull backend frontend llm
# COMPOSE_PROFILES=presentation이면 presentation도 먼저 pull한다.
docker compose -f docker-compose.app.yml run --rm db-migrate
docker compose -f docker-compose.app.yml up -d --no-build --wait --wait-timeout 300
docker compose -f docker-compose.app.yml ps
```

LLM이 Postgres 원본 기반 검색 상태를 준비한다. 기존 임베딩은 재사용하고 신규·변경 청크만 임베딩한다. 실제 준비 여부는 `ragReady`로 확인한다.

- App EC2에서는 이미지를 빌드하지 않는다. main CI가 Linux amd64 이미지를 GHCR에 게시한 뒤 배포한다. 최초 GHCR 이미지는 private이므로 수동 pull에는 패키지 읽기 권한으로 `docker login ghcr.io`가 필요하다. 자동 배포는 일시적인 `GITHUB_TOKEN`을 사용하고 Docker 인증 디렉터리를 종료 시 제거한다.
- `LLM_MEM_LIMIT`은 필수이며 임의의 기본값은 두지 않는다. 기존 기동/OCR/수집 사용량과 새 BM25를 만드는 재색인 피크를 측정하고 OS·다른 컨테이너 여유를 남겨 지정한다. 필요하면 App EC2 증설 또는 수집 환경 분리 후 진행한다. 다른 서비스 한도는 `.env.example`의 `*_MEM_LIMIT`으로 지정할 수 있다.
- 인덱스 warm-up 다음 OCR warm-up을 순차 실행한다. 실제 OCR 요청·Backend의 재색인과 겹치는 피크는 별도로 확인해야 한다. `docker inspect <llm-container> --format '{{.HostConfig.Memory}}'`가 0보다 크고 `docker stats` 및 호스트 메모리에 여유가 있는지 확인한다.
- `up --wait`와 HTTP 200은 RAG 정상 동작을 보장하지 않는다. `/api/health`의 `ragReady=true`, `postgres=connected`, `llm=connected`와 실제 상담·OCR를 확인한다.

## 9. GitHub 설정 (자동 배포)

1. 배포 전용 키 생성 (로컬)
   ```bash
   ssh-keygen -t ed25519 -f deploy_key -N "" -C "github-actions-deploy"
   ```
   `deploy_key.pub` 내용을 App EC2의 `~/.ssh/authorized_keys`에 추가
2. 저장소 → Settings → Secrets and variables → Actions

   | Secret | 값 |
   |---|---|
   | `EC2_HOST` | `<APP_EIP>` |
   | `EC2_USER` | `ubuntu` |
   | `EC2_SSH_KEY` | `deploy_key` 파일 내용 전체 |
   | `HEALTH_URL` | `https://<DOMAIN>/api/health` (HTTPS 전에는 `http://<APP_EIP>/api/health`) |

3. Settings → Branches → `main` 보호 규칙: PR 필수, 상태 검사 `test` 통과 필수
4. Actions → deploy → **Run workflow**로 수동 실행해 동작 확인

이후 `main` 병합 시 `.github/workflows/deploy.yml`이 테스트(서버 스크립트 `scripts/tests` `unittest`, Backend `unittest`, LLM `pytest` + 이미지 빌드, Frontend `node --test` + `npm run build`) → 4개 App 이미지 빌드·GHCR 게시 → 동일 커밋 checkout 확인 → 디스크 여유 확인(`DEPLOY_MIN_FREE_GB`, 기본 8GB 미만이면 중단) → 이미지 pull → `db-migrate` → `up --no-build --wait` → DB·LLM·RAG 준비 검사 → 현재·직전 배포 이미지만 남기고 정리(롤백용 직전 1개 보존)·빌드 캐시 정리 → 디스크 사용률 확인(80% 이상이면 경고) 순서로 자동 배포한다. 게시 job에는 `packages: write`, 배포 job에는 `packages: read` 권한이 필요하다. 서버 `.env`의 이미지 경로·태그는 배포 커밋으로 갱신된다. 이미 최신 main이 아닌 요청은 로그에 이유를 남기고 배포하지 않는다.

- PR run(`pull_request` 이벤트)의 deploy job은 항상 skipped가 정상. 배포 결과는 `main` push run의 deploy job에서 확인
- PR 테스트는 운영 대기열에 들어가지 않는다. deploy job·수집·재시도는 `ec2-app` 그룹과 `queue: max`로 직렬 실행한다(대기 최대 100개).
- 서버 작업은 `$HOME/.ec2-app.lock`을 사용한다. 수동 배포·수집도 같은 잠금 아래 실행한다. SSH 취소 후 collector가 남아 있으면 다음 작업은 실패하므로, 실행 상태를 확인하고 정리한 뒤 재실행한다.
- 자동 배포 대상은 App EC2뿐. Data EC2 변경은 10-1단계로 수동 반영

## 9-1. 데이터 수집 자동화

같은 Secrets(`EC2_HOST`·`EC2_USER`·`EC2_SSH_KEY`)를 쓰는 workflow 두 개가 App EC2에서 수집을 돌린다. `schedule`은 기본 브랜치(`main`)에 있는 workflow만 실행되며, 배포와 같은 `concurrency` 그룹(`ec2-app`)이라 동시에 돌지 않는다.

| workflow | 주기 | 동작 |
|---|---|---|
| `.github/workflows/collect.yml` | 매주 월 03:00 KST (`0 18 * * 0` UTC), 수동 실행 가능 | `docker compose -f docker-compose.app.yml run --rm collector`(`DB/run_collection.py` 전체 수집) → llm 컨테이너 안에서 `POST /rag/reindex`(변경 청크만 임베딩 → pgvector → 메모리 BM25 재구성). 수집이 일부 실패해도 성공분은 재색인하고 실패는 마지막에 알림 |
| `.github/workflows/collect-retry.yml` | 3시간마다 (`0 */3 * * *` UTC) | `collection_failures`의 `transient` 중 `next_retry_at`이 지난 스크립트만 `run_collection.py --retry`로 재실행한 뒤 `POST /rag/reindex`. 재시도할 것이 없으면 종료 코드 3 → 재색인 없이 성공 처리 |

- collector는 App EC2 `.env`의 `LAW_API_KEY`·`GOV24_API_KEY`·`ONTONG_YOUTH_API_KEY`와 `COMPOSE_DB_HOST`로 Data EC2 DB에 쓴다
- `permanent` 실패는 자동 재시도하지 않는다. `collection_failures`에서 확인 후 조치(`Docs/data_collection_preprocessing.md`)

## 9-2. 장애 감지·자동 복구

| 구성 | 동작 |
|---|---|
| `.github/workflows/health-check.yml` | 6시간마다(한국 시간 3·9·15·21시 17분) `HEALTH_URL`을 호출해 `postgres=connected`·`ragReady=true` 확인. 60초 간격 5회 모두 실패하면 workflow 실패 → GitHub 실패 메일 |
| `scripts/autoheal.sh` (cron) | 5분마다 `unhealthy` 컨테이너 재시작. compose `restart: unless-stopped`는 프로세스 종료만 감지하므로 보완 |

두 EC2 모두 cron 등록

```bash
crontab -e
*/5 * * * * bash /home/ubuntu/SKN34-4th-3Team/scripts/autoheal.sh >> /home/ubuntu/autoheal.log 2>&1
```

- 실패 메일은 Actions 알림 설정(Settings → Notifications → Actions)이 켜진 사용자에게 발송. 예약 workflow는 workflow를 마지막으로 수정한 사용자에게 발송
- 예약 workflow는 `main`에서만 실행되며 저장소 활동이 60일 없으면 비활성화됨. Actions 탭에서 다시 활성화
- 동작 확인: Actions → health-check → **Run workflow** 성공 확인

## 10. 백업 cron (Data EC2)

```bash
bash ~/SKN34-4th-3Team/scripts/backup_db.sh   # 1회 수동 실행으로 확인
crontab -e
PATH=/snap/bin:/usr/local/bin:/usr/bin:/bin
# 매일 04:00 (서버 시간대 기준. UTC면 한국 13:00)
0 4 * * * bash /home/ubuntu/SKN34-4th-3Team/scripts/backup_db.sh >> /home/ubuntu/backup_db.log 2>&1
# 매시간 마지막 성공 백업이 26시간 이내인지 확인(백업 cron 자체가 실행되지 않은 경우 포함)
15 * * * * bash /home/ubuntu/SKN34-4th-3Team/scripts/backup_db.sh --check-freshness >> /home/ubuntu/backup_db.log 2>&1
```

한국 시간 기준으로 맞추려면 `sudo timedatectl set-timezone Asia/Seoul`.

- 스크립트는 임시 덤프 생성·목차 검사 후 업로드하고 S3 객체 크기까지 확인한다. Data EC2에는 덤프 1개를 저장할 여유 공간이 필요하다. 임시 파일은 종료 시 삭제되고 마지막 성공 시각은 `~/.local/state/startup-on-backup/last_success`에 기록된다.
- AWS CLI 경로는 스크립트에서도 `/snap/bin`을 포함한다. 실패/백업 누락 알림은 SNS topic과 확인된 이메일 구독을 만들고 `.env`에 `BACKUP_ALERT_TOPIC_ARN`을 지정한다. Data EC2 역할에 해당 topic의 `sns:Publish` 권한을 추가한다. 미설정이면 stderr에 알림 미설정 경고만 남으므로 운영에서 반드시 설정한다.
- 업로드 성공·목차 검사는 실제 복원 성공을 보장하지 않는다. S3 덤프를 내려받아 **운영 DB와 분리된 테스트 DB**에 `pg_restore --exit-on-error`로 복원하고 테이블·행 수·대표 조회를 확인한다. 최초 적용 및 이후 월 1회 수행한다.
- Data EC2 스크립트와 crontab·IAM·SNS 설정은 App EC2 자동 배포로 반영되지 않는다. 10-1절에 따라 수동 적용하고 제한된 PATH로 스크립트 실행 및 `--check-freshness` 실패 알림을 확인한다.

## 10-1. Data EC2 수동 반영

자동 배포는 App EC2만 갱신. 아래 파일이 바뀐 `main` 병합 후에는 수동 반영 필요.

| 변경 대상 | 자동 반영 | 조치 |
|---|---|---|
| `DB/app_extras.sql` | O (배포마다 db-migrate) | 없음 |
| `DB/01_schema.sql` | X (빈 볼륨 최초 생성 시에만 적용) | 같은 변경을 `DB/app_extras.sql`에 재실행 안전한 문장으로 추가 |
| `elasticsearch/`, `docker-compose.data.yml` | X | 아래 절차 |
| Data EC2 `.env` | X | 아래 절차 |

스키마 변경 규칙: 기존 DB에 반영돼야 하는 변경은 반드시 `DB/app_extras.sql`에 `ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`처럼 여러 번 실행해도 안전한 형태로 추가. `01_schema.sql`에만 넣으면 운영 DB에 반영되지 않음.

Data EC2 반영 절차

```bash
ssh -i startup-on.pem -J ubuntu@<APP_EIP> ubuntu@<DATA_IP>
cd ~/SKN34-4th-3Team
git pull --ff-only origin main
docker compose -f docker-compose.data.yml up -d --build
docker compose -f docker-compose.data.yml ps   # db, elasticsearch 모두 healthy 확인
```

- 볼륨(`db_data`, `elasticsearch_data`)은 유지되므로 데이터 손실 없음
- DB 컨테이너가 재생성되면 App EC2의 backend·llm 연결이 잠시 끊김. 시연 중에는 반영 금지
- `elasticsearch/`(분석기·플러그인) 변경 시 인덱스 재생성 필요. App EC2에서 `docker compose -f docker-compose.app.yml restart llm backend` 실행(llm 기동 시 자체 warm-up으로 인덱스 구성, 10분 내 준비되지 않으면 backend가 재색인 요청) 후 `http://<APP_EIP>/api/health`의 `ragReady=true` 확인

## 11. 검증

- [ ] `http://<APP_EIP>/` 화면 표시
- [ ] `http://<APP_EIP>/api/health` → `ragReady=true`, `ragChunks`가 이전 원본 DB의 `rag_documents` 건수와 같음
- [ ] 로그인, 정책 검색, 세무 질의, 사업계획서 생성, 영수증 업로드
- [ ] 로컬에서 `curl -m 5 http://<APP_EIP>:8000/health` 실패 (8000·8001 미노출)
- [ ] Data EC2에 퍼블릭 IP 없음 (5432·9200 외부 접근 불가)
- [ ] deploy workflow 수동 실행 성공
- [ ] collect workflow 수동 실행 성공(9-1절)
- [ ] S3 `daily/`에 백업 파일 생성

### 11-1. 챕터 1 운영 완료 기준 (ID 3·4·1·2)

코드/로컬 테스트와 운영 완료를 구분한다. 먼저 `main`에 반영하고 App `.env`의 실측한 `LLM_MEM_LIMIT`, GHCR 접근, Data의 백업 스크립트·SNS·cron을 준비한다. 운영 SSH 없이 수행한 검증으로 아래 항목을 완료 처리하지 않는다.

| ID | 실행/확인 | 완료 출력·상태 |
|---|---|---|
| 3 | 수집 실행 중 main 배포·재시도·PR 테스트 실행 | 수집만 실행, 배포/재시도는 대기 후 실행, PR 테스트는 독립 실행. 운영 대기 작업이 `canceled`로 교체되지 않음 |
| 4 | Data EC2에서 제한된 PATH로 백업 및 freshness 검사 | `backup verified: s3://...`, `backup freshness OK (age=...s)`, 둘 다 exit 0. S3에서 내려받은 덤프의 별도 DB 복원 성공 |
| 1 | 배포 로그, `docker stats`, 호스트 메모리, OOM/재시작 상태 확인 | EC2 build 로그 없음. GHCR pull 후 `Deployment ready: <SHA>`. LLM 메모리 한도 > 0, 기동/OCR/수집/재색인 동안 OOM·재시작 없음, OS 메모리 여유 유지 |
| 2 | 준비 상태 조회를 반복하면서 전체 재색인과 상담 실행 | 재색인 중 `index_ready=true` 유지, 기존 상담 정상. 재색인 응답 성공 후 새 문서 반영. 실패 응답 때도 기존 runtime 유지 |

Data EC2 백업 검사(운영 설정을 출력하지 않음):

```bash
env -i HOME="$HOME" PATH=/usr/bin:/bin bash scripts/backup_db.sh
echo "backup exit=$?"
bash scripts/backup_db.sh --check-freshness
echo "freshness exit=$?"
# 빈 별도 상태 디렉터리로 백업 누락 알림을 시험한다. 운영 성공 기록은 건드리지 않는다.
test_state=$(mktemp -d)
BACKUP_STATE_DIR="$test_state" bash scripts/backup_db.sh --check-freshness
echo "missing-backup check exit=$?"
```

마지막 명령은 **0이 아닌 종료값**과 `backup failed`가 정상 시험 결과이며 SNS 알림이 실제 도착해야 한다. 목차/크기 검사만으로 복원 성공을 대신하지 않는다. `main`의 Data 파일은 10-1절에 따라 수동 갱신한다.

App EC2 메모리/상태 확인:

```bash
docker compose -f docker-compose.app.yml ps
llm_id=$(docker compose -f docker-compose.app.yml ps -q llm)
docker inspect "$llm_id" --format 'limit={{.HostConfig.Memory}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}'
free -h
docker stats --no-stream
sudo journalctl -k --since '30 minutes ago' | grep -Ei 'out of memory|oom-kill' || true
```

기동·OCR·수집·재색인 전후를 비교한다. `oom=false`, 재시작 횟수 증가 없음, 관련 커널 OOM 기록 없음이 필요하다. 단일 시점의 `stats`만으로 피크를 검증하지 말고 처리 중에도 반복 관찰한다. 한도에 근접하거나 swap/지연이 계속 증가하면 한도만 올리지 말고 호스트 여유·증설을 검토한다.

재색인 검증은 App EC2의 두 터미널에서 실행한다.

```bash
# 터미널 A: 완료까지 준비 상태를 반복 관찰
watch -n 1 'docker compose -f docker-compose.app.yml exec -T llm curl -fsS http://localhost:8001/rag/ready'
# 터미널 B: 전체 재색인. force=false로 변경된 청크만 임베딩한다.
docker compose -f docker-compose.app.yml exec -T llm curl -fsS --max-time 1800 \
  -X POST http://localhost:8001/rag/reindex -H 'Content-Type: application/json' \
  -d '{"documentIds":[],"force":false}'
```

처리 중 웹 상담도 실행해 미준비 오류나 목업 대체가 없는지 확인한다. `ready`/`already_ready`는 정상 재색인 결과다. 초기 기동에는 인덱스가 없어 준비 전 `index_ready=false`가 정상이며, 최초 준비 실패는 기존처럼 오류를 반환한다. 새 Dense 검색기·BM25는 별도로 준비해 교체하고 실패 시 기존 runtime을 유지한다. **DB 원본/pgvector 데이터의 과거 버전 복원은 보장하지 않는다.** 해당 버전 일치가 필요하면 staging/version 관리가 추가로 필요하다. 실패 경로는 로컬 회귀 테스트로 검증하며 운영 DB를 중지하거나 삭제해 시험하지 않는다.

## 12. HTTPS (도메인 확보 후)

> 도메인 구매만으로는 HTTPS 미적용. 인증서(Let's Encrypt, 무료) 발급과 nginx 443 설정이 별도로 필요. PWA(Service Worker)도 HTTPS 전제라 이 절 완료 후 동작. 12-4절 코드 변경과 PWA(`Frontend/vite.config.js`의 `VitePWA`)는 이미 `main`에 반영됐다.

아래 `<DOMAIN>`은 구매한 도메인.

### 12-1. DNS 연결

1. 도메인 등록 기관(또는 Route 53 호스팅 영역) DNS 설정에 레코드 추가

   | 유형 | 이름 | 값 |
   |---|---|---|
   | A | `@` (루트) | `<APP_EIP>` |
   | A | `www` (선택) | `<APP_EIP>` |

2. 전파 확인. 결과가 `<APP_EIP>`가 될 때까지 대기(수 분~수 시간)
   ```bash
   nslookup <DOMAIN>
   ```
3. `http://<DOMAIN>/` 접속 시 기존 화면 표시 확인

### 12-2. 보안그룹

`sg-app` 인바운드에 TCP 443 ← `0.0.0.0/0` 추가

### 12-3. 인증서 최초 발급 (App EC2, 1회)

최초 발급은 certbot이 80 포트를 직접 사용(standalone)하므로 frontend를 잠시 중지(수십 초 중단).

```bash
sudo snap install --classic certbot
sudo ln -sf /snap/bin/certbot /usr/bin/certbot
cd ~/SKN34-4th-3Team
docker compose -f docker-compose.app.yml stop frontend
sudo certbot certonly --standalone --cert-name changeup -d <DOMAIN>   # www 사용 시 -d www.<DOMAIN> 추가
docker compose -f docker-compose.app.yml start frontend
sudo mkdir -p /var/www/certbot   # 이후 갱신용 webroot
```

- `--cert-name changeup` → 인증서 경로를 `/etc/letsencrypt/live/changeup/`로 고정. 저장소에 도메인 하드코딩 불필요
- **HTTPS 설정이 포함된 코드를 main에 병합하기 전에 완료 필수.** 인증서 없이 443 설정이 배포되면 frontend(nginx) 기동 실패

### 12-4. nginx·compose 구성 (코드 변경, 반영 완료)

> 아래 변경은 이미 저장소에 들어가 있다. 기록용으로 남긴다.

로컬 `docker-compose.yml`도 같은 `Frontend/nginx.conf`를 사용 → 이 파일에 443 블록을 넣으면 인증서가 없는 로컬 환경이 깨짐. 공통 location을 분리하고 AWS 전용 설정 파일을 compose에서 덮어쓰는 방식.

| 파일 | 내용 |
|---|---|
| `Frontend/nginx-locations.conf` (신규) | 공통 location(`/api/`, `/ppt`, `/ppt/`, `/`, PWA 캐시 헤더). 이미지 내 `/etc/nginx/snippets/app-locations.conf`로 복사 |
| `Frontend/nginx.conf` | 로컬용. `listen 80` + `include /etc/nginx/snippets/app-locations.conf;` (기존 동작 동일) |
| `Frontend/nginx.https.conf` (신규) | AWS용. 80: `/.well-known/acme-challenge/` → `/var/www/certbot`, 그 외 `301 https://$host$request_uri` / 443: `ssl_certificate /etc/letsencrypt/live/changeup/fullchain.pem`, `ssl_certificate_key /etc/letsencrypt/live/changeup/privkey.pem` + 같은 include |
| `Frontend/Dockerfile` | `nginx-locations.conf` 복사 1줄 추가 |
| `docker-compose.app.yml` frontend | `ports`에 `"443:443"`, `volumes`에 `./Frontend/nginx.https.conf:/etc/nginx/conf.d/default.conf:ro`, `/etc/letsencrypt:/etc/letsencrypt:ro`, `/var/www/certbot:/var/www/certbot:ro` |

- Backend 변경 불필요: `ALLOWED_HOSTS=["*"]`, `CORS_ALLOW_ALL_ORIGINS=True`, 프론트는 같은 출처 상대 경로 `/api` 사용
- `.github/workflows/deploy.yml` 변경 불필요. `EC2_HOST`는 Elastic IP 그대로 사용 가능

### 12-5. 인증서 자동 갱신 전환 (HTTPS 배포 직후, 1회)

최초 발급 방식(standalone)은 갱신 때도 80 포트를 요구 → 실행 중인 nginx가 challenge 파일을 서빙하는 webroot 방식으로 전환. 갱신 후 nginx reload.

```bash
sudo certbot reconfigure --cert-name changeup --webroot -w /var/www/certbot \
  --deploy-hook "docker compose -f /home/ubuntu/SKN34-4th-3Team/docker-compose.app.yml exec -T frontend nginx -s reload"
sudo certbot renew --dry-run   # 성공 확인
```

- 갱신은 snap certbot 타이머가 자동 수행(만료 30일 전). 무중단

### 12-6. 검증

- [ ] `curl -I http://<DOMAIN>` → `301`, `Location: https://<DOMAIN>/`
- [ ] `curl -fsS https://<DOMAIN>/api/health` → `ragReady=true`
- [ ] 브라우저 `https://<DOMAIN>/` 자물쇠 표시, 로그인·정책 검색 정상
- [ ] `https://<DOMAIN>/ppt/` 발표자료 표시 (presentation 프로필 사용 시)
- [ ] `sudo certbot renew --dry-run` 성공
- [ ] PWA: Android Chrome 설치 프롬프트 표시·설치 후 `standalone` 실행, iOS Safari 홈 화면 추가 후 실행
- [ ] `curl -I https://<DOMAIN>/sw.js` 응답에 `Cache-Control: no-cache`
- [ ] `http://` 접속 시 `https://` 리다이렉트 후 Service Worker 정상 등록, `/ppt/`를 Service Worker가 가로채지 않음
- [ ] 화면 변경을 `main`에 병합 → deploy 성공 → 설치된 앱 재실행 시 변경 반영

## 비용 주의

> 서울 리전(ap-northeast-2) 온디맨드 단가 기준. AWS Price List API 2026-09-25 게시분으로 2026-09-28에 확인. 단가는 바뀔 수 있으므로 적용 전 [AWS 요금 계산기](https://calculator.aws/)로 재확인 필요. 신규 계정 크레딧·프리 티어는 계정마다 달라 반영하지 않음.

### 고정 비용 (전부 켜 둔 상태)

| 항목 | 단가 | 시간당 |
|---|---|---|
| App EC2 t3.medium | $0.052/h | $0.052 |
| Data EC2 t3.large | $0.104/h | $0.104 |
| NAT Gateway | $0.059/h | $0.059 |
| 퍼블릭 IPv4 2개 (App Elastic IP, NAT Gateway용 IP) | $0.005/h × 2 | $0.010 |
| EBS gp3 70GB (App 30 + Data 40) | $0.0912/GB-월 | $0.009 |
| **합계** | | **약 $0.234/h** |

- 하루: 약 $5.6
- 한 달(730시간): 약 $171
- 비중이 가장 큰 항목: Data EC2(44%), NAT Gateway(25%)

### 사용량에 따라 추가되는 비용

| 항목 | 단가 | 비고 |
|---|---|---|
| NAT 데이터 처리 | $0.059/GB | Data EC2의 이미지 pull·clone 시에만 발생, 설치 시 수 GB 수준. S3 백업은 게이트웨이 엔드포인트를 거쳐 NAT 비용 없음 |
| 인터넷 송신 트래픽 | 월 100GB 무료, 초과분 $0.126/GB | 시연 규모에서는 거의 발생하지 않음 |
| S3 백업 보관 | $0.025/GB-월 | 덤프 1GB × 30일 보관 시 월 약 $0.75 |
| t3 CPU 크레딧 | $0.05/vCPU-h | t3 기본 unlimited 모드에서 기준 CPU 사용률을 계속 넘을 때만 발생. 빌드 같은 순간 사용은 적립 크레딧으로 처리 |

### 미사용 시 절감

| 상태 | 남는 과금 | 시간당 | 하루 |
|---|---|---|---|
| 전부 켜 둠 | 위 고정 비용 전체 | $0.234 | $5.6 |
| EC2 2대만 중지 | NAT, IPv4 2개, EBS | $0.078 | $1.9 |
| EC2 중지 + NAT Gateway 삭제(해당 IP 해제) | App Elastic IP, EBS | $0.014 | $0.33 |

- NAT Gateway는 EC2를 중지해도 계속 과금됨 → 시연 기간이 아니면 삭제가 가장 효과적. 다시 필요할 때 새로 만들고 Private 서브넷 라우팅 테이블의 `0.0.0.0/0` 대상을 새 NAT Gateway로 교체
- S3 백업은 게이트웨이 엔드포인트를 쓰므로 NAT가 없어도 동작
- 결제 콘솔 → Budgets에서 월 예산 알림(예: $50) 설정 권장
