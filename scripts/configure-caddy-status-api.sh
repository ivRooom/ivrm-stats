#!/usr/bin/env bash
set -Eeuo pipefail

CADDY_DIR="${CADDY_DIR:-/opt/ivrm/compose/caddy}"
CADDYFILE="${CADDYFILE:-${CADDY_DIR}/Caddyfile}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNIPPET="${SOURCE_DIR}/deploy/status-api/Caddyfile.stats"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${CADDYFILE}.status-api-backup-${TIMESTAMP}"
TEMP_FILE="$(mktemp)"
trap 'rm -f "$TEMP_FILE"' EXIT

if [[ ! -f "$CADDYFILE" ]]; then
  echo "ERROR: Caddyfile not found: $CADDYFILE" >&2
  exit 1
fi
if [[ ! -f "$SNIPPET" ]]; then
  echo "ERROR: status Caddy snippet not found: $SNIPPET" >&2
  exit 1
fi

CADDY_CONTAINER="$(docker ps --format '{{.Names}} {{.Image}}' | awk '$2 ~ /^caddy(:|@)/ {print $1; exit}')"
if [[ -z "$CADDY_CONTAINER" ]]; then
  echo "ERROR: running Caddy container was not found" >&2
  exit 1
fi

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

docker exec "$CADDY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile
docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile
trap - ERR

echo "Caddy status-api routes configured"
echo "Backup: $BACKUP"
