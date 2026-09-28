#!/usr/bin/env bash
# Data EC2 에서 Postgres 를 덤프해 S3 로 올린다. cron 으로 매일 실행한다.
#   0 4 * * * bash /home/ubuntu/SKN34-4th-3Team/scripts/backup_db.sh >> /home/ubuntu/backup_db.log 2>&1
# 필요: 저장소 루트 .env 의 POSTGRES_USER·POSTGRES_DB·BACKUP_BUCKET, 인스턴스 역할의 S3 쓰기 권한, aws CLI
# 오래된 백업 삭제는 S3 수명주기 규칙이 맡는다.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# .env 에는 공백이 든 값(OUT_OF_SCOPE_ANSWER 등)이 있어 source 하지 않고 필요한 키만 읽는다.
env_value() {
  grep -E "^$1=" "$ROOT_DIR/.env" | tail -n 1 | cut -d= -f2- | tr -d '\r"'"'"
}

POSTGRES_USER="$(env_value POSTGRES_USER)"
POSTGRES_DB="$(env_value POSTGRES_DB)"
BACKUP_BUCKET="$(env_value BACKUP_BUCKET)"
: "${POSTGRES_USER:?POSTGRES_USER 가 .env 에 필요하다}"
: "${POSTGRES_DB:?POSTGRES_DB 가 .env 에 필요하다}"
: "${BACKUP_BUCKET:?BACKUP_BUCKET 이 .env 에 필요하다}"

key="daily/startup_platform_$(date +%Y%m%d_%H%M%S).dump"
docker exec startup_db pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" \
  | aws s3 cp - "s3://$BACKUP_BUCKET/$key"
echo "$(date '+%F %T') backup uploaded: s3://$BACKUP_BUCKET/$key"
