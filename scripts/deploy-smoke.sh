#!/usr/bin/env bash
# Post-deploy smoke tests for a running docker-compose.prod.yml stack.
# Runs tests/deploy from a throwaway container of the app image, attached to the
# stack's network at a fixed address, talking to nginx over HTTPS.
#
# usage: scripts/deploy-smoke.sh denied   # 172.28.0.50 is NOT in ALLOWED_IPS (normal)
#        scripts/deploy-smoke.sh allowed  # 172.28.0.50 temporarily added to ALLOWED_IPS
# See docs/deploy-verification.md.
set -euo pipefail

MODE="${1:?usage: $0 denied|allowed}"
RUNNER_IP="172.28.0.50"   # outside the auto-assigned 172.28.0.128/25 range
COMPOSE="docker compose -f docker-compose.prod.yml"
IMAGE="${SMOKE_IMAGE:-jhans-app:latest}"

env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '"'"'"; }

NGINX_ID="$($COMPOSE ps -q nginx)"
[ -n "$NGINX_ID" ] || { echo "nginx is not running: $COMPOSE up -d first" >&2; exit 1; }
NETWORK="$(docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{end}}' "$NGINX_ID")"

ALLOWED="$(env_value ALLOWED_IPS)"
case ",${ALLOWED// /}," in
  *",$RUNNER_IP,"*) [ "$MODE" = allowed ] || { echo "$RUNNER_IP is in ALLOWED_IPS; use 'allowed'" >&2; exit 1; } ;;
  *)                [ "$MODE" = denied ]  || { echo "add $RUNNER_IP to ALLOWED_IPS and recreate app first" >&2; exit 1; } ;;
esac
SPOOF_IP="${ALLOWED%%,*}"   # forge headers claiming to be the first allowed IP

docker run --rm --network "$NETWORK" --ip "$RUNNER_IP" --env-file .env \
  -e RUN_DEPLOY_TESTS=1 \
  -e DEPLOY_BASE_URL=https://nginx \
  -e DEPLOY_EXPECT_ADMIN="$MODE" \
  -e DEPLOY_SPOOF_IP="${SPOOF_IP:-127.0.0.1}" \
  -e DEPLOY_APP_SECRET_KEY="$(env_value APP_SECRET_KEY)" \
  "$IMAGE" python -m pytest -q -rs -p no:cacheprovider tests/deploy
