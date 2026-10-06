#!/usr/bin/env bash
# CI에서 빌드한 동일 커밋 이미지를 배포한다. 호출자는 .ec2-app.lock을 보유해야 한다.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/.."
[[ "${RELEASE_SHA:-}" =~ ^[0-9a-f]{40}$ ]]
[ "$(git rev-parse HEAD)" = "$RELEASE_SHA" ]
[[ "${GHCR_REPOSITORY:-}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]
export APP_IMAGE_REGISTRY="ghcr.io/${GHCR_REPOSITORY,,}"
export APP_IMAGE_TAG="$RELEASE_SHA"

auth_dir=""
cleanup() {
  rm -f -- .env.deploy-tmp
  if [ -n "$auth_dir" ]; then rm -rf -- "$auth_dir"; fi
}
trap cleanup EXIT
if [ -n "${GHCR_TOKEN:-}" ]; then
  auth_dir=$(mktemp -d)
  export DOCKER_CONFIG="$auth_dir"
  printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "${GHCR_USERNAME:?}" --password-stdin
fi

compose=(docker compose -f docker-compose.app.yml)
# LLM_MEM_LIMIT 미설정 시 migration이나 컨테이너 변경 전에 중단한다.
"${compose[@]}" config --quiet
services=(backend frontend llm)
profiles="${COMPOSE_PROFILES:-$(sed -n 's/^COMPOSE_PROFILES=//p' .env | tr -d '\r\"'\"'\"')}"
if [[ ",$profiles," = *,presentation,* ]]; then
  services+=(presentation)
fi
"${compose[@]}" pull "${services[@]}"
# 비밀값을 로그에 출력하지 않고 기존 .env의 다른 키를 유지한다.
sed '/^APP_IMAGE_REGISTRY=/d; /^APP_IMAGE_TAG=/d' .env > .env.deploy-tmp
printf '\nAPP_IMAGE_REGISTRY=%s\nAPP_IMAGE_TAG=%s\n' "$APP_IMAGE_REGISTRY" "$APP_IMAGE_TAG" >> .env.deploy-tmp
mv -f -- .env.deploy-tmp .env
"${compose[@]}" run --rm db-migrate
"${compose[@]}" up -d --no-build --wait --wait-timeout 300

# HTTP 200만으로 RAG 준비 여부를 알 수 없으므로 응답 내용을 확인한다.
ready=false
for attempt in $(seq 1 "${DEPLOY_READY_ATTEMPTS:-60}"); do
  if "${compose[@]}" exec -T backend python -c 'import json,urllib.request; s=json.load(urllib.request.urlopen("http://localhost:8000/health",timeout=10)); assert s["ragReady"] and s["postgres"]=="connected" and s["llm"]=="connected"'; then
    ready=true
    break
  fi
  sleep "${DEPLOY_READY_INTERVAL_SECONDS:-10}"
done
[ "$ready" = true ] || { echo '::error::DB/LLM/RAG readiness check failed' >&2; exit 1; }
docker image prune -f
docker builder prune -f --filter until=168h
usage=$(df --output=pcent / | tail -1 | tr -dc '0-9')
echo "disk usage: ${usage}%"
[ "$usage" -lt 80 ] || echo "::warning::App EC2 디스크 사용률 ${usage}%"
echo "Deployment ready: $RELEASE_SHA"
