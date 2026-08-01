#!/usr/bin/env bash
set -Eeuo pipefail

TARGET_DIR="${TARGET_DIR:-/opt/ivrm/www/stats}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
ASSET_VERSION="${ASSET_VERSION:-$TIMESTAMP}"
BACKUP_DIR="${TARGET_DIR}.ui-backup-${TIMESTAMP}"
RELEASE_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$RELEASE_DIR"
}
trap cleanup EXIT

for item in index.html history assets; do
  if [[ ! -e "${SOURCE_DIR}/${item}" ]]; then
    echo "ERROR: missing ${SOURCE_DIR}/${item}" >&2
    exit 1
  fi
done

python3 "${SOURCE_DIR}/scripts/validate.py"

mkdir -p "$RELEASE_DIR"
cp -a "${SOURCE_DIR}/index.html" "$RELEASE_DIR/"
cp -a "${SOURCE_DIR}/history" "$RELEASE_DIR/"
cp -a "${SOURCE_DIR}/assets" "$RELEASE_DIR/"

python3 - "$RELEASE_DIR/index.html" "$RELEASE_DIR/history/index.html" "$ASSET_VERSION" <<'PY'
from pathlib import Path
import re
import sys

*html_files, asset_version = sys.argv[1:]
for raw_path in html_files:
    path = Path(raw_path)
    text = path.read_text(encoding="utf-8")
    updated = re.sub(r"([?&]v=)[^\"'&<>\s]+", rf"\g<1>{asset_version}", text)
    path.write_text(updated, encoding="utf-8")
PY

sudo mkdir -p "$TARGET_DIR"
sudo mkdir -p "$BACKUP_DIR"

if [[ -d "$TARGET_DIR" ]]; then
  sudo rsync -a --exclude 'api/' "$TARGET_DIR/" "$BACKUP_DIR/"
fi

sudo rsync -a --delete --exclude 'api/' "$RELEASE_DIR/" "$TARGET_DIR/"
sudo chown -R opc:opc "$TARGET_DIR"
sudo find "$TARGET_DIR" -type d -exec chmod 755 {} +
sudo find "$TARGET_DIR" -type f -exec chmod 644 {} +

echo "Deployed IVRM Stats UI to: $TARGET_DIR"
echo "UI backup created at: $BACKUP_DIR"
echo "Static asset version: $ASSET_VERSION"
echo "Runtime API preserved at: $TARGET_DIR/api"
