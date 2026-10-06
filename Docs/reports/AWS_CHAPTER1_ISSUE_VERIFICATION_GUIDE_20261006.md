# AWS 챕터 1 운영 검증 및 병합 점검

작성일: 2026-10-06 · 대상: 챕터 1, ID 3 → ID 4 → ID 1 → ID 2

## 1. 현재 검증 범위와 준비 사항

코드 반영 및 로컬 테스트와 운영 검증 완료를 구분한다. EC2에서 배포·메모리·백업 복원 결과는 아직 확인하지 않았다. 각 ID는 아래 실행 결과와 실제 서비스 동작을 확인한 뒤 운영 완료로 판단한다.

아래 운영 명령은 SSH로 접속한 Ubuntu EC2에서 실행한다. Windows PowerShell 명령이 아니다.

```bash
cd ~/SKN34-4th-3Team
```

- App EC2: 수정 사항을 main에 반영하고 새 이미지로 배포해야 한다. 배포 전에 `.env`의 `LLM_MEM_LIMIT` 설정과 GHCR 접근 준비가 필요하다.
- Data EC2: 수정된 `scripts/backup_db.sh`를 별도로 반영해야 한다. App 자동 배포는 Data EC2 파일·cron·IAM·SNS 설정을 갱신하지 않는다.
- `.env.example`을 운영 `.env`에 통째로 덮어쓰지 않는다. 기존 키·DB 연결·관리자 설정을 유지하고 필요한 항목을 추가한다.

| 작업 | DB·서버에 미치는 영향 |
|---|---|
| health·메모리·로그 조회 | 상태 조회 |
| 백업 실행 | 운영 DB 읽기, S3에 백업 파일 생성 |
| 별도 컨테이너 복원 | 테스트 DB에만 데이터 생성 |
| 배포 실행 | 기존 배포 절차의 db-migrate 실행, App 컨테이너 교체 |
| 수집 실행 | 수집 데이터 저장·갱신 |
| 재색인 실행 | 검색용 청크·임베딩 갱신 |
| 상담·OCR 시험 | 사용 경로에 따라 상담·영수증 기록 저장 |

검증 절차 전체가 단순 조회만으로 이루어지는 것은 아니다. 실제 배포에서는 기존 `DB/app_extras.sql`이 다시 실행되고, backend 기동 시 기존 관리자 계정에도 `ADMIN_PASSWORD`가 적용된다.

## 2. ID 3 — 배포 대기 작업의 자동 취소

### 2.1 확인 목적

1. 배포·수집·재시도 작업이 대기 중 새 작업 때문에 취소되지 않는지 확인한다.
2. 실제 EC2 작업이 한 번에 하나씩 실행되는지 확인한다.
3. PR 테스트가 운영 작업의 대기열에 묶이지 않는지 확인한다.

### 2.2 GitHub Actions에서 작업을 겹쳐 확인

수집이 실행 중인 시점에 다음 작업을 실행하거나 관찰한다.

- collect-data: 실행 중.
- deploy: main 기준 실행.
- collect-data-retry: 실행 요청.
- 새 PR의 테스트: 실행.

수동 수집도 실제 데이터를 갱신하므로 가능하면 예정된 수집 실행 시점에 맞춰 확인한다.

| 확인 대상 | 정상 상태 |
|---|---|
| 먼저 시작한 수집 | 계속 실행 |
| 이후 배포의 deploy job | 대기 후 실행 |
| 이후 재시도 | 대기 후 실행 |
| PR 테스트 | 운영 작업의 잠금 때문에 대기하지 않음 |
| 먼저 대기하던 운영 작업 | 새 작업 요청 때문에 Canceled로 바뀌지 않음 |

배포 workflow 전체 상태와 deploy job 상태를 구분한다. 테스트·이미지 빌드는 수집과 동시에 실행될 수 있고, EC2에 접속하는 deploy job이 대기하는 것이 정상이다. 일반적인 runner 대기는 운영 concurrency 대기와 구분한다.

PR 실행에서 build-images 및 deploy job은 Skipped가 정상이다. 재시도 대상이 없는 collect-data-retry가 재색인 없이 성공 종료하는 것도 정상이다.

### 2.3 App EC2의 실제 잠금 확인

수집 또는 배포가 SSH로 서버 작업을 수행하는 동안 다른 터미널에서 실행한다.

```bash
flock -n "$HOME/.ec2-app.lock" -c 'echo lock-free'
echo "lock check exit=$?"
```

작업 중 정상 결과:

```text
lock check exit=1
```

`lock-free`는 출력되지 않아야 한다. 모든 운영 작업이 끝난 후에는 다음 결과가 정상이다.

```text
lock-free
lock check exit=0
```

이미지 빌드 중이나 Actions 대기 중에는 아직 서버 잠금이 없을 수 있다. 반드시 서버 작업 구간에서 확인한다.

### 2.4 최종 배포 반영 확인

최종 배포 로그에 다음 출력이 있어야 한다.

```text
Deployment ready: <배포 커밋 SHA>
```

최신 main이 아닌 배포 요청은 이유를 남기고 건너뛴다. Actions가 초록색이라는 이유만으로 해당 요청이 실제 배포되었다고 판단하지 않는다.

### 2.5 완료·실패 기준

- 완료: 대기 자동 취소 없음, PR 테스트 독립 실행, 서버 잠금으로 직렬 실행, 최신 배포 완료.
- 실패: 새 요청 때문에 기존 대기가 취소되거나 서버 변경 작업이 겹쳐 실행됨.
- 수집 API 오류·재색인 실패는 별도 원인이다. 작업 자체의 성공 여부와 대기열·잠금 동작을 구분한다.

## 3. ID 4 — 백업 cron 및 복원 가능성

수동 백업 → 실패 알림 → 실제 복원 → cron 자동 실행 순서로 확인한다.

### 3.1 Data EC2에서 제한된 PATH로 백업

cron과 비슷하게 환경변수가 적은 상태로 실행한다.

```bash
env -i HOME="$HOME" PATH=/usr/bin:/bin bash scripts/backup_db.sh
echo "backup exit=$?"
```

정상 출력 예시:

```text
2026-... backup verified: s3://<버킷>/daily/startup_platform_<시각>.dump
backup exit=0
```

이 출력은 덤프 생성, 비어 있지 않은 덤프, pg_restore 목차 검사, S3 업로드, 원본·S3 객체 크기 일치를 통과했다는 의미다. 실제 복원 성공까지 보장하는 출력은 아니다.

`backup failed` 또는 0이 아닌 종료값이면 실패다.

### 3.2 최근 백업 성공 기록 확인

```bash
bash scripts/backup_db.sh --check-freshness
echo "freshness exit=$?"
```

정상 출력:

```text
backup freshness OK (age=123s)
freshness exit=0
```

age는 마지막 성공 백업 이후 지난 시간이다. 기본 허용 시간은 26시간, 93,600초다.

### 3.3 백업 누락 시 실제 알림 확인

운영 성공 기록을 수정하지 않고 별도의 빈 상태 디렉터리로 시험한다.

```bash
test_state=$(mktemp -d)
BACKUP_STATE_DIR="$test_state" bash scripts/backup_db.sh --check-freshness
echo "missing-backup check exit=$?"
```

이 시험에서는 다음 실패 결과가 정상이다.

```text
... backup failed ...
missing-backup check exit=<0이 아닌 값>
```

SNS 구독 대상에 다음 제목의 알림이 실제 도착해야 한다.

```text
Postgres backup failed or overdue
```

다음 출력은 알림 설정 미완료 또는 알림 전송 실패다.

```text
BACKUP_ALERT_TOPIC_ARN is unset ...
SNS backup alert failed
```

SNS 이메일 구독 확인과 EC2 역할의 해당 topic에 대한 sns:Publish 권한이 필요하다. 참고: [AWS SNS 구독](https://docs.aws.amazon.com/us_en/sns/latest/dg/sns-create-subscribe-endpoint-to-topic.html), [SNS IAM 정책](https://docs.aws.amazon.com/sns/latest/dg/sns-using-identity-based-policies.html).

### 3.4 S3 백업을 별도 DB에 실제 복원

backup verified에 출력된 정확한 버킷·객체 경로를 사용한다. 운영 DB 볼륨이나 포트를 연결하지 않는 별도 컨테이너로 복원한다. Data EC2에서 실행하면 메모리·디스크를 추가 사용하므로 여유를 확인한다. 다른 Docker 서버에서 수행해도 된다.

```bash
backup_bucket='<실제 버킷 이름>'
backup_key='daily/<backup verified에 나온 파일 이름>'
umask 077
verify_dir=$(mktemp -d)
aws s3 cp "s3://$backup_bucket/$backup_key" "$verify_dir/backup.dump"
echo "download exit=$?"
```

다운로드 종료값이 0일 때만 진행한다.

```bash
restore_name="ch1-restore-$(date +%Y%m%d%H%M%S)"
docker run -d --rm \
  --name "$restore_name" \
  --network none \
  -e POSTGRES_PASSWORD=verify-only-password \
  pgvector/pgvector:pg16
```

테스트 컨테이너 실행이 성공하면 기동 완료를 확인한다.

```bash
docker exec "$restore_name" pg_isready -h 127.0.0.1 -U postgres
```

다음 출력까지 잠시 기다렸다가 다시 확인한다.

```text
127.0.0.1:5432 - accepting connections
```

테스트 DB 생성:

```bash
docker exec "$restore_name" createdb -U postgres -T template0 ch1_verify
echo "create database exit=$?"
```

생성 종료값이 0일 때만 복원한다.

```bash
docker exec -i "$restore_name" \
  pg_restore --exit-on-error --no-owner --no-privileges \
  -U postgres -d ch1_verify < "$verify_dir/backup.dump"
echo "restore exit=$?"
```

정상 결과는 restore exit=0이다. --exit-on-error는 SQL 복원 오류 시 중단한다. 소유자·권한 옵션은 별도 테스트 DB와 원본 역할의 차이를 피하기 위한 것이다. 이 시험은 실제 운영 복구 시 역할·권한 재구성까지 검증하는 절차는 아니다. 참고: [PostgreSQL pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html).

복원 테이블과 행 수 확인:

```bash
docker exec "$restore_name" psql -U postgres -d ch1_verify -c '\dt public.*'
docker exec "$restore_name" psql -U postgres -d ch1_verify -c "
  SELECT 'users' AS table_name, COUNT(*) AS rows FROM users
  UNION ALL
  SELECT 'policies', COUNT(*) FROM policies
  UNION ALL
  SELECT 'rag_documents', COUNT(*) FROM rag_documents;
"
```

정상 기준:

- 원본 테이블들이 존재한다.
- 백업 당시 데이터가 있던 테이블에 데이터가 존재한다.
- 대표 정책·검색 문서 조회가 정상 수행된다.
- 백업 시점의 예상 데이터 규모·행 수와 일치한다.

정확한 행 수는 운영 데이터에 따라 다르다. 백업 후 수집이 진행됐다면 현재 운영 DB와 달라질 수 있으므로 백업 시점 기준으로 비교한다. 행 수 조회만으로 모든 데이터 내용의 동일성을 증명하는 것은 아니므로 대표 문서 내용도 확인한다.

확인 후 생성한 테스트 컨테이너만 종료한다.

```bash
docker stop "$restore_name"
```

`$verify_dir`에는 개인정보를 포함할 수 있는 다운로드 덤프가 남는다. 결과 확인 후 실제 경로를 확인하고 해당 테스트 파일을 정리한다.

### 3.5 cron 자동 실행 확인

```bash
crontab -l
timedatectl
```

Ubuntu 사용자와 경로가 가이드와 같다면 다음 설정이 필요하다. 다른 사용자라면 실제 절대 경로를 사용한다.

```cron
PATH=/snap/bin:/usr/local/bin:/usr/bin:/bin
0 4 * * * bash /home/ubuntu/SKN34-4th-3Team/scripts/backup_db.sh >> /home/ubuntu/backup_db.log 2>&1
15 * * * * bash /home/ubuntu/SKN34-4th-3Team/scripts/backup_db.sh --check-freshness >> /home/ubuntu/backup_db.log 2>&1
```

서버 UTC의 04:00은 한국 시간 13:00이다. 서버가 한국 시간이면 한국 시간 04:00에 실행한다.

예정 실행 시각 이후 확인:

```bash
tail -n 50 ~/backup_db.log
```

수동 실행 이후의 새 시각으로 backup verified가 남고 새로운 S3 객체가 생성되어야 한다. 매시간 freshness 로그도 남아야 한다.

### 3.6 완료·실패 기준

- 제한된 환경에서 백업 exit=0.
- freshness exit=0.
- 누락 시험은 실패하고 실제 알림 도착.
- S3 백업을 별도 DB에 복원하고 데이터 조회 성공.
- cron 자동 백업 실행 확인.

수동 실행만 성공하면 cron 자동 실행 검증은 남아 있다. 목차·업로드 검사만 성공하면 복원 검증도 남아 있다.

## 4. ID 1 — App EC2 메모리 부족

배포 방식 변경과 실제 부하 중 메모리를 모두 확인한다.

### 4.1 Actions 및 EC2 배포 로그

정상 흐름:

```text
GitHub Actions에서 이미지 빌드·GHCR push
→ EC2에서 이미지 pull
→ db-migrate
→ 컨테이너 기동
→ 준비 상태 검사
→ Deployment ready: <SHA>
```

- build-images job에서 이미지 빌드·게시가 수행된다.
- EC2 배포 구간에서는 App 이미지 docker build를 실행하지 않는다.
- EC2 기동은 --no-build로 수행한다.
- 마지막 Deployment ready 출력과 배포 SHA를 확인한다.

### 4.2 실행 이미지·메모리 한도·준비 상태

```bash
docker compose -f docker-compose.app.yml ps
llm_id=$(docker compose -f docker-compose.app.yml ps -q llm)
docker inspect "$llm_id" \
  --format 'image={{.Config.Image}} limit={{.HostConfig.Memory}} oom={{.State.OOMKilled}} restarts={{.RestartCount}} started={{.State.StartedAt}}'
```

정상 기준:

- backend·llm healthy, frontend 정상 실행.
- presentation은 profile 사용 시 확인.
- 실행 이미지 태그가 배포 SHA와 일치.
- limit > 0. 단위는 byte.
- oom=false.
- restarts가 관찰 중 증가하지 않음.

```bash
docker compose -f docker-compose.app.yml exec -T backend \
  python -c 'import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen("http://localhost:8000/health", timeout=10)), ensure_ascii=False, indent=2))'
```

핵심 기대 값:

```json
{
  "postgres": "connected",
  "llm": "connected",
  "ragReady": true
}
```

HTTP 200 또는 컨테이너 healthy만으로 RAG 준비 완료를 판단하지 않는다.

### 4.3 부하 전부터 연속 관찰

별도 터미널들에서 다음 명령을 실행한다.

```bash
docker stats
```

```bash
watch -n 2 free -h
```

```bash
vmstat 1
```

- docker stats: LLM·backend·collector 등 전체 사용량.
- free: available.
- vmstat: si/so, swap 입출력. 첫 행은 기동 이후 평균이므로 이후 반복 출력도 확인한다.

### 4.4 실제 작업 구간 확인

| 구간 | 확인할 행동 |
|---|---|
| 배포·최초 기동 | 이미지 교체부터 RAG/OCR 준비 완료까지 관찰 |
| OCR | 실제 영수증 처리와 예상 동시 요청 수로 확인 |
| 수집 | collector 실행 및 이후 재색인까지 관찰 |
| 재색인 | 기존·새 검색기가 함께 존재하는 구간 관찰 |
| 상담 | 위 작업 중 실제 상담 응답 확인 |

OCR·상담은 테스트 계정을 사용하면 기록을 구분하기 좋다.

정상 기준:

- 컨테이너 종료·예기치 않은 재시작 없음.
- 호스트 메모리 고갈 없음.
- 메모리 제한에 반복적으로 부딪히지 않음.
- 지속적인 swap 입출력과 함께 지연·timeout이 발생하지 않음.
- 작업 완료 후에도 서비스 정상.

swap 사용량 > 0만으로 실패는 아니다. 지속적인 swap 입출력과 서비스 지연을 함께 판단한다.

### 4.5 종료 후 OOM·재시작 확인

```bash
sudo journalctl -k --since '1 hour ago' \
  | grep -Ei 'out of memory|oom-kill|killed process' || true
llm_id=$(docker compose -f docker-compose.app.yml ps -q llm)
docker inspect "$llm_id" \
  --format 'oom={{.State.OOMKilled}} restarts={{.RestartCount}} started={{.State.StartedAt}}'
```

관찰 시작 시점과 비교한다. 관련 OOM 기록, 재시작 횟수 증가, 의도하지 않은 컨테이너 교체가 없어야 한다. 컨테이너 재생성 시 재시작 횟수가 초기화될 수 있으므로 마지막 restarts=0 하나로 판단하지 않는다. 시험이 한 시간보다 길었다면 커널 로그 조회 시작 시각을 실제 시험 시작으로 변경한다. 로그 조회 권한 오류는 'OOM 없음'이 아니다.

### 4.6 완료 기준

- EC2에서 App 이미지 빌드 없음.
- 실행 이미지가 배포 SHA와 일치.
- LLM 메모리 제한 적용.
- 기동·OCR·수집·재색인 중 OOM·예기치 않은 재시작 없음.
- 예상 부하에서 메모리 여유와 정상 응답 확보.

현재 용량으로 충족하지 못하면 코드가 반영되었어도 ID 1은 미완료다. 한도·동시 처리량 조정 또는 서버 증설이 필요하다. 로컬의 작은 OCR 입력에서 측정한 메모리로 운영 한도를 확정하지 않는다. 후속 챕터의 이중 초기화 등 미해결 이슈도 부하에 영향을 줄 수 있다.

## 5. ID 2 — 재색인 중 기존 RAG 중단

처음부터 검색 준비가 완료된 상태에서 시험한다. 새 컨테이너의 초기 준비 시간은 별개다.

### 5.1 재색인 전 상태·상담 기준 결과

```bash
docker compose -f docker-compose.app.yml exec -T llm \
  curl -fsS http://localhost:8001/rag/ready
```

핵심 기대 값:

```json
{
  "status": "ready",
  "index_ready": true,
  "llm_configured": true,
  "embedding_configured": true
}
```

웹에서 정책·세무 근거를 실제 조회하는 상담을 실행하고 정상 응답·출처를 확인한다. 단순 인사는 검색 검증에 적합하지 않다.

### 5.2 터미널 A — 준비 상태 관찰

```bash
watch -n 1 \
  'docker compose -f docker-compose.app.yml exec -T llm curl -fsS http://localhost:8001/rag/ready'
```

### 5.3 터미널 B — 재색인 실행

```bash
docker compose -f docker-compose.app.yml exec -T llm \
  curl -fsS --max-time 1800 \
  -X POST http://localhost:8001/rag/reindex \
  -H 'Content-Type: application/json' \
  -d '{"documentIds":[],"force":false}'
echo "reindex exit=$?"
```

force=false는 기존 임베딩을 재사용하고 필요한 변경을 반영한다. 재색인은 검색용 DB 데이터에 쓰기가 발생할 수 있다.

### 5.4 처리 중 실제 상담

재색인이 끝나기 전에 웹에서 상담한다.

- index_ready=true 유지.
- 정책·세무 상담 응답 성공.
- 재색인으로 인한 미준비 오류·503 없음.
- 목업 대체 없음.
- 검색 근거·출처 정상.

브라우저 Network에서 실제 응답을 확인한다. 해당 응답에 llmUsed가 있으면 정상 상담에서 true인지 함께 확인한다. 화면에 문장이 표시되는 것만으로 성공을 판단하지 않는다.

재색인이 너무 빨리 끝나 상담할 시간이 없었다면 동시 처리 검증은 미실시다. 수집 후 충분한 처리 시간이 있는 재색인 구간에서 확인한다. 1초 간격 상태 관찰은 모든 순간을 증명하지 않으므로 실제 상담 결과·오류 로그도 함께 확인한다.

### 5.5 완료 후 결과

- reindex exit=0.
- 응답 status는 ready 또는 already_ready.
- 완료 후 index_ready=true 유지.
- 상담 정상.
- 신규·변경 문서가 있었다면 해당 문서 검색에 변경 내용 반영.

변경 문서가 없으면 서비스 유지 동작은 확인할 수 있지만 신규 문서 반영까지 확인한 것은 아니다.

### 5.6 재색인 실패 시 기존 검색 유지

성공한 재색인 한 번으로 실패 경로를 증명할 수 없다. 현재 코드의 실패 시 기존 runtime 유지 경로는 로컬 회귀 테스트로 검증했다.

운영 환경과 같은 조건의 추가 확인은 별도 테스트 환경에서 인덱스 구성 실패를 유발해 수행한다.

- 재색인 요청은 오류 반환.
- 기존 인덱스가 있다면 index_ready=true 유지.
- 기존 문서를 사용하는 상담 성공.

운영 DB를 중지하거나 데이터를 삭제해 시험하지 않는다. 처음부터 기존 인덱스가 없고 최초 준비가 실패하면 not_ready가 정상이다.

이번 변경은 기존 검색 runtime의 사용 가능 상태를 유지한다. 이미 갱신한 DB 청크·임베딩을 과거 버전으로 되돌리는 기능은 포함하지 않는다.

### 5.7 완료 기준

- 재색인 전 준비 완료.
- 재색인 중 준비 상태와 실제 검색 상담 유지.
- 완료 후 정상 상담·변경 문서 반영.
- 실패 경로 검증.

실패 경로를 로컬 테스트로만 확인했다면 그 사실을 결과 기록에 구분해 남긴다.

## 6. develop → main 병합 전 점검

### 6.1 2026-10-06 원격 확인 결과

git fetch origin 후 확인한 상태다. 이후 다른 push가 있으면 다시 확인해야 한다.

- 작업 브랜치: feature/LLM-patch, HEAD ffc80dd.
- origin/develop: 0bcfb2c.
- origin/main: 39f79eb.
- develop과 main의 파일 내용은 동일하다. main에 병합 커밋 1개가 더 있다.
- 작업 브랜치에는 ID 3·4·1·2 수정 커밋 4개가 있다.
- 작업 브랜치와 develop의 3-way 병합 미리보기에서 충돌 표시는 없었다.
- 실제 병합은 수행하지 않았다. 이 문서는 로컬에 저장한 신규 파일이며 커밋·푸시 전에는 PR에 포함되지 않는다.

수정 커밋:

| ID | 커밋 | 메시지 |
|---|---|---|
| 3 | 9785908 | fix: ID3 배포·수집 대기 취소 및 동시 실행 방지 |
| 4 | 2e70af5 | fix: ID4 백업 cron 경로 및 덤프 검증·실패 알림 보완 |
| 1 | 0f26b8d | fix: ID1 EC2 빌드 제거 및 LLM 메모리 피크 완화 |
| 2 | ffc80dd | fix: ID2 재색인 중 기존 RAG 검색 상태 유지 |

### 6.2 feature/LLM-patch → develop

1. 이 문서를 병합에 포함하려면 작업 브랜치에 문서를 커밋·푸시한다. 문서 추가에는 docs: 메시지를 사용하고 기존 ID 수정 커밋 메시지는 유지한다.
2. 최신 원격 기준으로 PR의 변경 파일과 충돌 여부를 확인한다.
3. ID별 커밋 이력을 유지하려면 merge commit 방식을 사용한다. Squash merge는 여러 ID 수정 커밋을 하나로 합친다.
4. develop에 병합된 최종 코드로 LLM·셸 회귀 테스트를 실행한다.
5. develop 대상 PR과 develop push에는 현재 deploy.yml이 자동 실행되지 않는다. 해당 브랜치 병합이 초록색 또는 CI 없음으로 보이는 것만으로 테스트 통과를 대신하지 않는다.

로컬 PowerShell에서 기존 LLM 가상환경을 사용할 경우:

```powershell
Set-Location LLM
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
Set-Location ..
.\LLM\.venv\Scripts\python.exe -m unittest discover -s scripts/tests -p "test_*.py"
```

LLM 테스트는 LLM 디렉터리에서 실행한다. 셸 테스트에는 Git Bash 또는 Linux Bash가 필요하다. Bash가 없어 skipped가 나왔다면 테스트 성공으로 처리하지 않는다. 기존 검증에서는 LLM 518개 및 셸 테스트 11개가 통과했다. 이후 테스트가 추가되면 개수는 달라질 수 있으며 최종 병합 코드의 오류·실패·skip 이유를 확인한다.

### 6.3 develop → main PR

1. 최신 main과 develop 사이의 최종 변경 범위를 확인한다. 다른 작업이 develop에 추가되었다면 함께 배포될 변경을 검수한다.
2. main 대상 PR의 test job에서 Backend 테스트, Frontend 테스트·빌드가 통과해야 한다.
3. 현재 PR CI에는 LLM 및 scripts/tests 회귀 테스트가 없다. develop 단계의 별도 실행 결과를 확인한다.
4. PR에서는 build-images·deploy가 Skipped가 정상이다. PR 통과만으로 GHCR 게시·실제 이미지 pull을 확인한 것은 아니다.
5. 현재 workflow는 main push에 반응한다. main 병합은 자동 배포를 시작하므로 다음 준비를 병합 전에 완료한다.

### 6.4 main 병합 전에 필요한 운영 준비

| 대상 | 준비 사항 | 미준비 시 영향 |
|---|---|---|
| App 메모리 | 기존 부하와 새 재색인 피크를 고려한 LLM_MEM_LIMIT 설정 | compose 검사 단계에서 배포 중단 또는 부하 중 OOM |
| GitHub/GHCR | GITHUB_TOKEN의 packages:write/read 허용 및 패키지 접근 | 이미지 게시·pull 실패 |
| App SSH | 기존 EC2_HOST·EC2_USER·EC2_SSH_KEY 유효 | 서버 접속 실패 |
| App checkout | 서버 브랜치 main, tracked 변경 없음, main과 분기 없음 | git pull --ff-only 실패 |
| 서버 작업 | 진행 중 수집·수동 작업 확인, 수동 작업도 공통 잠금 사용 | 충돌·잠금 timeout 또는 잔존 collector 검사 실패 |
| 디스크 | 이미지 pull 및 기존 이미지 공존 공간 확보 | pull 실패·배포 실패 |
| HTTPS | /etc/letsencrypt/live/changeup 인증서·개인키 유효 | frontend 기동 실패 |
| DB 연결 | Data EC2 DB 가동, App에서 접근 가능, 기존 연결 설정 유지 | migration 또는 준비 검사 실패 |
| DB 백업 | 병합 전에 최신 백업 확보, 가능한 범위에서 복원 확인 | 배포 후 문제 발생 시 복구 준비 부족 |
| Data 백업 | 스크립트 수동 반영 계획, SNS·IAM·cron 준비 | App 배포 성공해도 ID 4 운영 해결 미완료 |
| 복구 준비 | 직전 정상 커밋·실행 이미지·설정 기록, rollback 방법 확보 | 배포 실패 후 복구 지연 |

LLM_MEM_LIMIT은 빈 값으로 병합하지 않으며 임의 예시를 운영 검증 완료 값으로 취급하지 않는다. APP_IMAGE_REGISTRY·APP_IMAGE_TAG는 자동 배포 스크립트가 새 커밋으로 설정하고 .env에 저장한다. 수동 compose 실행에서는 둘 다 필요하다.

App EC2 사전 확인 예시:

```bash
cd ~/SKN34-4th-3Team
git status --short
git branch --show-current
df -h
free -h
docker ps --filter label=com.docker.compose.service=collector
sudo test -s /etc/letsencrypt/live/changeup/fullchain.pem
echo "certificate file exit=$?"
sudo test -s /etc/letsencrypt/live/changeup/privkey.pem
echo "private key file exit=$?"
```

tracked 파일 변경이 없어야 하며 서버 브랜치는 main이어야 한다. 추적하지 않는 운영 파일이 출력되면 내용을 판단한다. 인증서 파일 검사 exit=0은 존재·비어 있지 않음을 뜻할 뿐 만료·유효성 검사까지 대신하지 않는다.

현행 배포에는 자동 rollback이 없다. readiness 실패 시 일부 새 컨테이너나 변경된 .env가 남을 수 있다. 직전 정상 이미지로 돌아갈 경우 그 이미지가 GHCR에 남아 있어야 하며 기존 migration 결과·설정과도 호환되어야 한다. Git revert와 DB 복원은 같은 작업이 아니다.

### 6.5 main 병합 후

1. main push run에서 test → build-images 4개 → deploy 성공 확인.
2. Deployment ready의 SHA가 최종 main 커밋과 일치하는지 확인. PR의 feature HEAD SHA와 같을 필요는 없다.
3. App 실제 실행 이미지 태그도 해당 SHA와 일치하는지 확인.
4. health·웹 접속·상담·OCR의 기본 동작 확인.
5. Data EC2에 백업 스크립트·설정을 별도로 반영하고 ID 4 검증 수행.
6. 이 문서의 ID별 부하·동시 처리 검증 수행.
7. cron 자동 실행은 예정된 실행 이후에 최종 완료 기록.

main 병합 또는 Actions 성공과 챕터 1 운영 완료는 구분한다. 챕터 1 수정이 이후 챕터의 미해결 이슈까지 해결한 것은 아니다.

## 7. 최종 증거 및 결과 기록

| ID | 완료 판단에 필요한 증거 |
|---|---|
| 3 | 겹친 Actions의 대기·실행 결과, 취소 없음, 서버 잠금, 최종 배포 SHA |
| 4 | 백업·freshness 로그, 실제 알림, 별도 DB 복원·조회 결과, cron 자동 실행 로그 |
| 1 | 배포 로그, 실행 SHA, 메모리 한도·부하 중 사용량, OOM·재시작 기록, 실제 응답 |
| 2 | 재색인 전·중·후 상태, 진행 중 상담, 변경 문서 반영, 실패 경로 검증 |

| ID | 상태: 대기/진행/완료 | 실행 시각 | 결과·증거 위치 | 남은 항목 |
|---|---|---|---|---|
| 3 | 대기 | | | 운영 검증 |
| 4 | 대기 | | | 운영 백업·알림·복원·cron |
| 1 | 대기 | | | 운영 부하·메모리 실측 |
| 2 | 대기 | | | 운영 동시 상담·문서 반영 |

관련 문서: [AWS 배포 가이드](../AWS_DEPLOY_GUIDE.md), [배포 위험 보고서](AWS_DEPLOY_RISK_REPORT_20261005.md).
