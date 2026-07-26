#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE_TAG="${1:?usage: deploy-status-api-oci.sh <image-tag>}"
TARGET_DIR="${STATUS_API_DIR:-/opt/ivrm/compose/ivrm-status-api}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_SOURCE="${SOURCE_DIR}/deploy/status-api/docker-compose.yml"
ENV_FILE="${TARGET_DIR}/.env"
IMAGE_ENV_FILE="${TARGET_DIR}/.image.env"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DEPLOY_UID="$(id -u)"
DEPLOY_GID="$(id -g)"

if [[ ! -f "$COMPOSE_SOURCE" ]]; then
  echo "ERROR: compose file not found: $COMPOSE_SOURCE" >&2
  exit 1
fi

# 初回設定時にroot所有で作成された場合でも、デプロイユーザーが
# .envを参照し、docker composeを実行できるように親ディレクトリを整える。
sudo install -d -m 0750 -o "$DEPLOY_UID" -g "$DEPLOY_GID" "$TARGET_DIR"

if ! sudo test -f "$ENV_FILE"; then
  echo "ERROR: production secret file is missing: $ENV_FILE" >&2
  echo "Create it from deploy/status-api/.env.example before deployment." >&2
  exit 1
fi
if ! sudo grep -Eq '^HERTA_INGEST_SECRET=.{32,}$' "$ENV_FILE"; then
  echo "ERROR: HERTA_INGEST_SECRET must be configured with at least 32 characters" >&2
  exit 1
fi

CADDY_CONTAINER="$(docker ps --format '{{.Names}} {{.Image}}' | awk '$2 ~ /^caddy(:|@)/ {print $1; exit}')"
if [[ -z "$CADDY_CONTAINER" ]]; then
  echo "ERROR: running Caddy container was not found" >&2
  exit 1
fi
CADDY_NETWORK_NAME="$(docker inspect "$CADDY_CONTAINER" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{"\n"}}{{end}}' | head -n 1)"
if [[ -z "$CADDY_NETWORK_NAME" ]]; then
  echo "ERROR: Caddy network could not be detected" >&2
  exit 1
fi

sudo install -d -m 0750 -o 10001 -g 10001 "${TARGET_DIR}/data"
if [[ -f "${TARGET_DIR}/docker-compose.yml" ]]; then
  sudo cp -a "${TARGET_DIR}/docker-compose.yml" "${TARGET_DIR}/docker-compose.yml.backup-${TIMESTAMP}"
fi
sudo install -m 0644 "$COMPOSE_SOURCE" "${TARGET_DIR}/docker-compose.yml"
printf 'IMAGE_TAG=%s\nCADDY_NETWORK_NAME=%s\n' "$IMAGE_TAG" "$CADDY_NETWORK_NAME" \
  | sudo tee "$IMAGE_ENV_FILE" >/dev/null
sudo chown "$DEPLOY_UID:$DEPLOY_GID" "$TARGET_DIR" "$IMAGE_ENV_FILE" "$ENV_FILE"
sudo chmod 0750 "$TARGET_DIR"
sudo chmod 0600 "$IMAGE_ENV_FILE" "$ENV_FILE"

cd "$TARGET_DIR"
docker compose --env-file "$IMAGE_ENV_FILE" pull
docker compose --env-file "$IMAGE_ENV_FILE" up -d --no-build --remove-orphans

for attempt in {1..20}; do
  health="$(docker inspect ivrm-status-api --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
  if [[ "$health" == "healthy" ]]; then
    break
  fi
  if [[ "$health" == "unhealthy" || "$health" == "exited" ]]; then
    docker logs --tail 100 ivrm-status-api >&2 || true
    exit 1
  fi
  sleep 3
done

health="$(docker inspect ivrm-status-api --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')"
if [[ "$health" != "healthy" ]]; then
  echo "ERROR: status-api did not become healthy: $health" >&2
  exit 1
fi

bash "${SOURCE_DIR}/scripts/configure-caddy-status-api.sh"

echo "Status API deployed: ghcr.io/ivrooom/ivrm-stats-api:${IMAGE_TAG}"
