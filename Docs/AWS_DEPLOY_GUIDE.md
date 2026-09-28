# AWS 배포 가이드 (1차: HTTP)

> 설계 근거는 `Docs/reports/AWS_MIGRATION_PLAN.md`. 이 문서는 AWS 콘솔에서 직접 수행하는 단계별 절차. 도메인이 없어 1차는 Elastic IP + HTTP로 배포하고, HTTPS는 11단계에서 도메인 확보 후 적용.

## 구성 요약

| 구분 | App EC2 | Data EC2 |
|---|---|---|
| 서브넷 | Public (Elastic IP) | Private (NAT Gateway 경유 외부 통신) |
| compose | `docker-compose.app.yml` | `docker-compose.data.yml` |
| 컨테이너 | frontend(nginx :80), backend, llm, db-migrate(배포 시 1회), presentation(선택) | db(startup_db), elasticsearch |
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
```

`.env`의 `ELASTICSEARCH_URL`은 `docker-compose.app.yml`이 `http://<COMPOSE_DB_HOST>:9200`으로 덮어씀.

```bash
docker compose -f docker-compose.app.yml run --rm db-migrate
docker compose -f docker-compose.app.yml up -d --build
docker compose -f docker-compose.app.yml ps
```

backend가 healthy가 되면서 ES 인덱스를 Postgres 원본으로 자동 재생성함. 임베딩은 `rag_documents`의 기존 값을 재사용하므로 추가 비용 없음.

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

3. Settings → Branches → `main` 보호 규칙: PR 필수, 상태 검사 `test` 통과 필수
4. Actions → deploy → **Run workflow**로 수동 실행해 동작 확인

이후 `main` 병합 시 `.github/workflows/deploy.yml`이 테스트 → `git pull` → `db-migrate` → `up -d --build` 순서로 자동 배포.

## 10. 백업 cron (Data EC2)

```bash
bash ~/SKN34-4th-3Team/scripts/backup_db.sh   # 1회 수동 실행으로 확인
crontab -e
# 매일 04:00 (서버 시간대 기준. UTC면 한국 13:00)
0 4 * * * bash /home/ubuntu/SKN34-4th-3Team/scripts/backup_db.sh >> /home/ubuntu/backup_db.log 2>&1
```

한국 시간 기준으로 맞추려면 `sudo timedatectl set-timezone Asia/Seoul`.

## 11. 검증

- [ ] `http://<APP_EIP>/` 화면 표시
- [ ] `http://<APP_EIP>/api/health` → `ragReady=true`, `ragChunks=10,523`
- [ ] 로그인, 정책 검색, 세무 질의, 사업계획서 생성, 영수증 업로드
- [ ] 로컬에서 `curl -m 5 http://<APP_EIP>:8000/health` 실패 (8000·8001 미노출)
- [ ] Data EC2에 퍼블릭 IP 없음 (5432·9200 외부 접근 불가)
- [ ] deploy workflow 수동 실행 성공
- [ ] S3 `daily/`에 백업 파일 생성

## 12. HTTPS (도메인 확보 후)

1. Route 53(또는 외부 등록 기관)에서 도메인 확보 → A 레코드 → `<APP_EIP>`
2. `sg-app`에 TCP 443 ← `0.0.0.0/0` 추가
3. certbot으로 인증서 발급, `Frontend/nginx.conf`에 443 server 블록과 80 → 443 리다이렉트 추가, 인증서 경로를 frontend 컨테이너에 마운트
4. 이후 PWA 적용 (`Docs/reports/AWS_MIGRATION_PLAN.md` 2절)

## 비용 주의

- NAT Gateway는 인스턴스를 중지해도 시간당 과금됨. 시연 기간이 아니면 NAT Gateway를 삭제하고 Data EC2 업데이트가 필요할 때 다시 생성하는 방식으로 절감 가능. S3 백업은 게이트웨이 엔드포인트를 쓰므로 NAT 없이도 동작
- Elastic IP와 퍼블릭 IPv4 주소는 사용 중에도 과금됨
- 금액은 [AWS 요금 계산기](https://calculator.aws/)로 산정
