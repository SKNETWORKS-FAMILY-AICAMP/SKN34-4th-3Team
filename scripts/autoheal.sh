#!/usr/bin/env bash
# healthcheck 가 unhealthy 인 컨테이너를 재시작한다.
# compose 의 restart 정책은 프로세스가 종료될 때만 동작해, 멈춘(응답 없는) 컨테이너는 그대로 남는다.
# cron(App·Data EC2 공통): */5 * * * * bash /home/ubuntu/SKN34-4th-3Team/scripts/autoheal.sh >> /home/ubuntu/autoheal.log 2>&1
set -euo pipefail

for name in $(docker ps --filter health=unhealthy --format '{{.Names}}'); do
  echo "$(date '+%F %T') restart $name"
  docker restart "$name"
done
