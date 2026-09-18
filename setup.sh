#!/usr/bin/env bash
#
# 청년·1인 창업 지원 플랫폼 로컬 실행 스크립트 (macOS / Linux / Windows Git Bash)
#
#   ./setup.sh                 컨테이너 기동 후 Frontend 개발 서버까지 실행
#   ./setup.sh --no-frontend   컨테이너만 기동하고 종료 (CI·헤드리스용)
#
# db·backend·llm 은 Docker Compose 로 띄우고 Frontend 만 호스트에서 돈다.
# vite.config.js 의 /api 프록시 대상이 호스트 주소라 compose 에 넣지 않았다.
#
# .env 는 만들지 않는다. 비밀키가 들어 있어 git 으로 공유되지 않으므로
# 팀에서 파일로 받아 저장소 루트에 두어야 한다.
#
# Docker Compose v2.1.1 이상이 필요하다 (--wait).

set -euo pipefail
cd "$(dirname "$0")"

die() { echo; echo "  X  $*" >&2; echo >&2; exit 1; }

FRONTEND=1
case "${1:-}" in
  "")            ;;
  --no-frontend) FRONTEND=0 ;;
  *)             die "알 수 없는 옵션: $1 (사용 가능: --no-frontend)" ;;
esac

[ -f .env ] || die ".env 가 없습니다. 팀에서 받아 $(pwd)/.env 에 두고 다시 실행하세요.
     필요 키: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB,
              OPENAI_API_KEY, LLM_MODEL, EMBEDDING_MODEL"

# 이 셋이 비면 db 의 pg_isready 헬스체크가 통과하지 못하고
# backend·llm 이 depends_on: service_healthy 에서 무한 대기한다.
for key in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB; do
  grep -q "^$key=[^[:space:]]" .env || die ".env 의 $key 가 비어 있습니다."
done
grep -q "^OPENAI_API_KEY=[^[:space:]]" .env ||
  echo "  *  OPENAI_API_KEY 미설정 — AI 답변은 목업입니다. 화면·DB·정책조회는 정상입니다."

echo "[1/4] 이미지 빌드 (최초 실행은 몇 분 걸립니다)"
docker compose build

echo "[2/4] DB 기동 및 스키마 보정"
docker compose up -d --wait db
# initdb 는 볼륨이 비어 있을 때만 돈다. 그 마운트가 추가되기 전에 만들어진
# 볼륨에는 app_extras 가 빠져 있어 backend 가 users.phone 없음으로 죽는다.
# 전 문장이 IF NOT EXISTS 라 재실행해도 안전하고 기존 행을 지우지 않는다.
# 사용자·DB명은 db 컨테이너의 환경변수를 그대로 쓴다.
docker compose exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q' < DB/app_extras.sql

echo "[3/4] Backend·LLM 기동"
docker compose up -d backend llm

echo "[4/4] 헬스체크"
RETRY="--connect-timeout 5 --retry 30 --retry-delay 2 --retry-connrefused --retry-max-time 90"
wait_http() {  # $1=url  $2=compose 서비스명
  if curl -fsS -o /dev/null $RETRY "$1"; then return 0; fi
  docker compose logs --tail=30 "$2" >&2
  die "$2 이(가) 응답하지 않습니다. 위 로그를 확인하세요."
}
wait_http http://127.0.0.1:8001/health llm
wait_http http://127.0.0.1:8000/health backend

HEALTH="$(curl -fsS http://127.0.0.1:8000/health)"
echo "  $HEALTH"
case "$HEALTH" in *'"storage":"postgres"'*) ;;
  *) echo "  *  Postgres 대신 SQLite 로 폴백했습니다. DATABASE_URL 을 확인하세요." ;;
esac
case "$HEALTH" in *'"ragReady":true'*) ;;
  *) echo "  *  RAG 인덱스가 비어 AI 답변은 목업입니다. 실답변은 POST :8001/rag/reindex (OpenAI 비용 발생)" ;;
esac

echo
echo "  Backend  http://localhost:8000/docs"
echo "  LLM      http://localhost:8001/docs"
echo "  종료     docker compose down"

if [ "$FRONTEND" = 0 ]; then exit 0; fi

cd Frontend
# npm ci 는 node_modules 를 지우고 다시 깐다. 실행 중인 Vite 가 esbuild 를
# 잠그면 EPERM 으로 실패하므로 필요할 때만 돌린다.
if [ ! -d node_modules ] || [ package-lock.json -nt node_modules ]; then
  npm ci
fi

echo
echo "  화면       http://localhost:5173  (브라우저 자동 실행)"
echo "  데모 계정  demo@demo.com / demo123    관리자  admin@demo.com / admin123"
echo "  Ctrl+C 는 Frontend 만 멈춥니다."
echo
exec npm run dev
