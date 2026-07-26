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

# Caddyfileは単一ファイルとしてbind mountされているため、installやrenameで
# 宛先inodeを置き換えると、起動中コンテナが古いinodeを参照し続ける。
# 内容を同じinodeへ上書きし、コンテナ側へ即時反映させる。
write_caddyfile_in_place() {
  local source_file="$1"
  local target_file="$2"

  sudo sh -c 'cat "$1" > "$2"' sh "$source_file" "$target_file"
  sudo chmod 0644 "$target_file"
}

# docker cpはbind mount元の現在内容を参照し、実行中コンテナのmount namespaceが
# 保持している古いinodeとの差異を見逃す場合がある。必ずコンテナ内プロセスから
# catして、Caddyが実際に参照できる内容を取得する。
copy_active_caddyfile() {
  : > "$ACTIVE_FILE"
  if ! docker exec "$CADDY_CONTAINER" cat /etc/caddy/Caddyfile > "$ACTIVE_FILE"; then
    echo "ERROR: Caddyコンテナ内の実行時Caddyfileを読み取れません。" >&2
    return 1
  fi
}

print_caddy_mount_diagnostics() {
  echo "Detected host Caddyfile: $CADDYFILE" >&2
  echo "Host SHA-256: $(sha256sum "$CADDYFILE" | awk '{print $1}')" >&2
  echo "Runtime SHA-256: $(sha256sum "$ACTIVE_FILE" | awk '{print $1}')" >&2
  echo "Caddy mounts:" >&2
  docker inspect "$CADDY_CONTAINER" --format '{{range .Mounts}}{{println .Type .Source "->" .Destination}}{{end}}' >&2
}

recreate_caddy_for_stale_bind_mount() {
  local compose_workdir compose_service
  compose_workdir="$(docker inspect "$CADDY_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')"
  compose_service="$(docker inspect "$CADDY_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.service"}}')"

  if [[ -z "$compose_workdir" || -z "$compose_service" ]]; then
    echo "ERROR: CaddyのCompose作業ディレクトリまたはサービス名を検出できません。" >&2
    return 1
  fi
  if [[ ! -d "$compose_workdir" ]]; then
    echo "ERROR: CaddyのCompose作業ディレクトリが存在しません: $compose_workdir" >&2
    return 1
  fi

  echo "WARNING: Caddyが置換前のCaddyfile inodeを参照しています。" >&2
  echo "WARNING: bind mountを現在のホストファイルへ付け直すため、Caddyコンテナを一度だけ再作成します。" >&2
  echo "Compose workdir: $compose_workdir" >&2
  echo "Compose service: $compose_service" >&2

  (
    cd "$compose_workdir"
    docker compose up -d --no-deps --force-recreate "$compose_service"
  )

  for _attempt in {1..20}; do
    if [[ "$(docker inspect "$CADDY_CONTAINER" --format '{{.State.Running}}' 2>/dev/null || true)" == "true" ]] \
      && docker exec "$CADDY_CONTAINER" test -r /etc/caddy/Caddyfile >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "ERROR: 再作成後のCaddyコンテナが起動状態になりませんでした。" >&2
  return 1
}

write_caddyfile_in_place "$TEMP_FILE" "$CADDYFILE"

rollback() {
  echo "Caddy validation/reload failed; restoring $BACKUP" >&2
  write_caddyfile_in_place "$BACKUP" "$CADDYFILE"
  docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true
}
trap rollback ERR

copy_active_caddyfile
if ! cmp -s "$CADDYFILE" "$ACTIVE_FILE"; then
  print_caddy_mount_diagnostics
  recreate_caddy_for_stale_bind_mount
  copy_active_caddyfile
fi

if ! cmp -s "$CADDYFILE" "$ACTIVE_FILE"; then
  echo "ERROR: Caddy再作成後もホストとコンテナの実行時Caddyfile内容が一致しません。" >&2
  print_caddy_mount_diagnostics
  false
fi
if ! grep -Fq 'reverse_proxy @status_public status-api:8080' "$ACTIVE_FILE"; then
  echo "ERROR: 実行時CaddyfileにStatus APIルートがありません。" >&2
  echo "Detected host Caddyfile: $CADDYFILE" >&2
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
