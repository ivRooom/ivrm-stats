#!/usr/bin/env bash
set -Eeuo pipefail

CADDY_DIR="${CADDY_DIR:-/opt/ivrm/compose/caddy}"
REQUESTED_CADDYFILE="${CADDYFILE:-}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNIPPET="${SOURCE_DIR}/deploy/status-api/Caddyfile.stats"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
TEMP_FILE="$(mktemp)"
ACTIVE_FILE="$(mktemp)"
ADAPTED_FILE="$(mktemp)"
trap 'rm -f "$TEMP_FILE" "$ACTIVE_FILE" "$ADAPTED_FILE"' EXIT

if [[ ! -f "$SNIPPET" ]]; then
  echo "ERROR: status Caddy snippet not found: $SNIPPET" >&2
  exit 1
fi

CADDY_CONTAINER="$(docker ps --format '{{.Names}} {{.Image}}' | awk '$2 ~ /^caddy(:|@)/ {print $1; exit}')"
if [[ -z "$CADDY_CONTAINER" ]]; then
  echo "ERROR: running Caddy container was not found" >&2
  exit 1
fi

if [[ -n "$REQUESTED_CADDYFILE" ]]; then
  CADDYFILE="$REQUESTED_CADDYFILE"
else
  MOUNTED_CADDYFILE="$(docker inspect "$CADDY_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}')"
  MOUNTED_CADDYDIR="$(docker inspect "$CADDY_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy"}}{{.Source}}{{end}}{{end}}')"

  if [[ -n "$MOUNTED_CADDYFILE" ]]; then
    CADDYFILE="$MOUNTED_CADDYFILE"
  elif [[ -n "$MOUNTED_CADDYDIR" ]]; then
    CADDYFILE="${MOUNTED_CADDYDIR}/Caddyfile"
  else
    CADDYFILE="${CADDY_DIR}/Caddyfile"
    echo "WARNING: /etc/caddy/Caddyfileのホスト側マウント元を検出できませんでした。" >&2
    echo "WARNING: 既定値を使用します: $CADDYFILE" >&2
  fi
fi

if [[ ! -f "$CADDYFILE" ]]; then
  echo "ERROR: Caddyfile not found: $CADDYFILE" >&2
  exit 1
fi

BACKUP="${CADDYFILE}.status-api-backup-${TIMESTAMP}"
sudo cp -a "$CADDYFILE" "$BACKUP"

python3 - "$CADDYFILE" "$SNIPPET" "$TEMP_FILE" <<'PY'
from pathlib import Path
import sys

caddyfile = Path(sys.argv[1])
snippet = Path(sys.argv[2]).read_text(encoding="utf-8").rstrip() + "\n"
temporary = Path(sys.argv[3])
text = caddyfile.read_text(encoding="utf-8")
needle = "stats.ivrm.jp {"
start = text.find(needle)
if start < 0:
    raise SystemExit("stats.ivrm.jp block was not found")

brace_depth = 0
end = None
for index in range(start, len(text)):
    char = text[index]
    if char == "{":
        brace_depth += 1
    elif char == "}":
        brace_depth -= 1
        if brace_depth == 0:
            end = index + 1
            break
if end is None:
    raise SystemExit("stats.ivrm.jp block is not balanced")

updated = text[:start] + snippet + text[end:].lstrip("\n")
temporary.write_text(updated, encoding="utf-8")
PY
sudo install -m 0644 "$TEMP_FILE" "$CADDYFILE"

rollback() {
  echo "Caddy validation/reload failed; restoring $BACKUP" >&2
  sudo cp -a "$BACKUP" "$CADDYFILE"
  docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true
}
trap rollback ERR

docker cp "${CADDY_CONTAINER}:/etc/caddy/Caddyfile" "$ACTIVE_FILE"
if ! grep -Fq 'reverse_proxy @status_public status-api:8080' "$ACTIVE_FILE"; then
  echo "ERROR: 更新したホストCaddyfileがコンテナ内の/etc/caddy/Caddyfileへ反映されていません。" >&2
  echo "Detected host Caddyfile: $CADDYFILE" >&2
  echo "Caddy mounts:" >&2
  docker inspect "$CADDY_CONTAINER" --format '{{range .Mounts}}{{println .Type .Source "->" .Destination}}{{end}}' >&2
  false
fi

docker exec "$CADDY_CONTAINER" caddy adapt \
  --config /etc/caddy/Caddyfile \
  --adapter caddyfile \
  --pretty > "$ADAPTED_FILE"

python3 - "$ADAPTED_FILE" <<'PY'
import json
from pathlib import Path
import sys

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
serialized = json.dumps(config, ensure_ascii=False)
required = (
    "/api/internal/status-ingest",
    "/api/status.json",
    "status-api:8080",
)
missing = [value for value in required if value not in serialized]
if missing:
    raise SystemExit(f"adapted Caddy config is missing: {', '.join(missing)}")
PY

docker exec "$CADDY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile
docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile
trap - ERR

echo "Caddy status-api routes configured"
echo "Active host Caddyfile: $CADDYFILE"
echo "Backup: $BACKUP"
