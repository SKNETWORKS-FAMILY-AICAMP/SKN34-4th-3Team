#!/usr/bin/env bash
# Data EC2: 검증된 Postgres 덤프만 S3에 업로드한다.
# --check-freshness는 별도 cron에서 마지막 성공 백업의 나이를 검사한다.
set -Eeuo pipefail
umask 077
export PATH="$PATH:/snap/bin:/usr/local/bin:/usr/bin:/bin"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${BACKUP_ENV_FILE:-$ROOT_DIR/.env}"
STATE_DIR="${BACKUP_STATE_DIR:-$HOME/.local/state/startup-on-backup}"
AWS_BIN="${AWS_BIN:-aws}"
mode="${1:-backup}"
dump_file=""

# .env 에는 공백이 든 값(OUT_OF_SCOPE_ANSWER 등)이 있어 source 하지 않고 필요한 키만 읽는다.
env_value() {
  grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d '\r"'"'"
}

mkdir -p "$STATE_DIR"
BACKUP_ALERT_TOPIC_ARN="${BACKUP_ALERT_TOPIC_ARN:-$(env_value BACKUP_ALERT_TOPIC_ARN || true)}"
cleanup() { [ -z "$dump_file" ] || rm -f -- "$dump_file"; }
failed() {
  local rc="$1"
  trap - ERR
  printf '%s\n' "$(date -u +%s)" > "$STATE_DIR/last_failure"
  echo "$(date -u '+%FT%TZ') backup failed (exit=$rc, mode=$mode); see stderr" >&2
  if [ -n "$BACKUP_ALERT_TOPIC_ARN" ]; then
    "$AWS_BIN" sns publish --topic-arn "$BACKUP_ALERT_TOPIC_ARN" \
      --subject 'Postgres backup failed or overdue' \
      --message "Postgres backup/check failed on $(hostname), exit=$rc. Check backup_db.log and last_success." \
      >/dev/null || echo 'SNS backup alert failed' >&2
  else
    echo 'BACKUP_ALERT_TOPIC_ARN is unset; external backup alerts are not configured' >&2
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'failed "$?"' ERR

command -v "$AWS_BIN" >/dev/null
if [ "$mode" = '--check-freshness' ]; then
  last_success=$(cat "$STATE_DIR/last_success")
  max_age="${BACKUP_MAX_AGE_SECONDS:-93600}" # 매일 백업에 2시간 여유를 둔 26시간
  [[ "$last_success" =~ ^[0-9]+$ && "$max_age" =~ ^[0-9]+$ ]]
  age=$(( $(date -u +%s) - last_success ))
  (( age >= 0 && age <= max_age ))
  echo "backup freshness OK (age=${age}s)"
  exit 0
fi
[ "$#" -eq 0 ] || { echo 'Usage: backup_db.sh [--check-freshness]' >&2; exit 2; }
command -v docker >/dev/null
command -v flock >/dev/null
exec 9>"$STATE_DIR/backup.lock"
flock -n 9

POSTGRES_USER="$(env_value POSTGRES_USER)"
POSTGRES_DB="$(env_value POSTGRES_DB)"
BACKUP_BUCKET="$(env_value BACKUP_BUCKET)"
for required in POSTGRES_USER POSTGRES_DB BACKUP_BUCKET; do
  if [ -z "${!required}" ]; then
    echo "$required 가 .env 에 필요하다" >&2
    false
  fi
done

dump_file=$(mktemp "$STATE_DIR/dump.XXXXXXXX")
docker exec startup_db pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$dump_file"
[ -s "$dump_file" ]
# 목차 검사는 기본 형식 검증이다. 별도 DB에 실제 복원하는 리허설도 필요하다.
docker exec -i startup_db pg_restore --list < "$dump_file" > /dev/null
key="daily/startup_platform_$(date -u +%Y%m%d_%H%M%S).dump"
"$AWS_BIN" s3 cp "$dump_file" "s3://$BACKUP_BUCKET/$key" --only-show-errors
remote_size=$("$AWS_BIN" s3api head-object --bucket "$BACKUP_BUCKET" --key "$key" \
  --query ContentLength --output text)
[ "$remote_size" = "$(wc -c < "$dump_file" | tr -d '[:space:]')" ]
printf '%s\n' "$(date -u +%s)" > "$STATE_DIR/last_success.tmp"
mv -f -- "$STATE_DIR/last_success.tmp" "$STATE_DIR/last_success"
echo "$(date -u '+%FT%TZ') backup verified: s3://$BACKUP_BUCKET/$key"
