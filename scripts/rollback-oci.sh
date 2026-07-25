#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /opt/ivrm/www/stats.ui-backup-YYYYMMDD-HHMMSS" >&2
  exit 1
fi

BACKUP_DIR="$1"
TARGET_DIR="${TARGET_DIR:-/opt/ivrm/www/stats}"

if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "ERROR: backup directory not found: $BACKUP_DIR" >&2
  exit 1
fi

sudo rsync -a --delete --exclude 'api/' "$BACKUP_DIR/" "$TARGET_DIR/"
sudo chown -R opc:opc "$TARGET_DIR"

echo "Rolled back IVRM Stats UI from: $BACKUP_DIR"
echo "Runtime API preserved at: $TARGET_DIR/api"
