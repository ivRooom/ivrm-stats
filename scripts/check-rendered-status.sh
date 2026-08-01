#!/usr/bin/env bash
set -Eeuo pipefail

URL="${1:-https://status.ivrm.jp/}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/ivrm-status-browser}"
mkdir -p "$OUTPUT_DIR"

if command -v google-chrome >/dev/null 2>&1; then
  BROWSER="$(command -v google-chrome)"
elif command -v chromium >/dev/null 2>&1; then
  BROWSER="$(command -v chromium)"
elif command -v chromium-browser >/dev/null 2>&1; then
  BROWSER="$(command -v chromium-browser)"
else
  echo "ERROR: Chrome/Chromium was not found" >&2
  exit 1
fi

echo "Browser: $($BROWSER --version)"
echo "Target: $URL"

curl --fail --silent --show-error --max-time 20 -D "$OUTPUT_DIR/headers.txt" \
  "${URL}?render_check=$(date +%s)" -o "$OUTPUT_DIR/source.html"
curl --fail --silent --show-error --max-time 20 \
  "${URL%/}/api/status.json?render_check=$(date +%s)" -o "$OUTPUT_DIR/status.json"
python3 - "$OUTPUT_DIR/status.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert isinstance(payload.get("services"), list)
print(f"API services: {len(payload['services'])}")
print(f"API overall_status: {payload.get('overall_status')}")
PY

USER_DATA_DIR="$(mktemp -d)"
trap 'rm -rf "$USER_DATA_DIR"' EXIT

set +e
"$BROWSER" \
  --headless=new \
  --no-sandbox \
  --disable-gpu \
  --disable-dev-shm-usage \
  --disable-background-networking \
  --disable-default-apps \
  --disable-extensions \
  --disable-sync \
  --no-first-run \
  --user-data-dir="$USER_DATA_DIR" \
  --window-size=390,844 \
  --virtual-time-budget=15000 \
  --screenshot="$OUTPUT_DIR/mobile.png" \
  --enable-logging=stderr \
  --log-level=0 \
  --dump-dom \
  "${URL}?render_check=$(date +%s)" \
  >"$OUTPUT_DIR/rendered.html" \
  2>"$OUTPUT_DIR/browser.log"
BROWSER_EXIT=$?
set -e

if [[ $BROWSER_EXIT -ne 0 ]]; then
  echo "ERROR: headless browser failed with exit code $BROWSER_EXIT" >&2
  cat "$OUTPUT_DIR/browser.log" >&2
  exit 1
fi

python3 - "$OUTPUT_DIR/rendered.html" <<'PY'
from html.parser import HTMLParser
from pathlib import Path
import sys

class Inspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.target = None
        self.values = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        element_id = values.get("id")
        if element_id in {
            "overallTitle",
            "overallEyebrow",
            "overallMessage",
            "serviceCount",
            "operationalCount",
            "activeIncidentCount",
            "freshnessText",
        }:
            self.target = element_id

    def handle_endtag(self, _tag):
        self.target = None

    def handle_data(self, data):
        if self.target:
            self.values[self.target] = self.values.get(self.target, "") + data

html = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
inspector = Inspector()
inspector.feed(html)
values = {key: value.strip() for key, value in inspector.values.items()}
for key, value in values.items():
    print(f"{key}: {value}")

service_count = values.get("serviceCount", "")
overall_title = values.get("overallTitle", "")
if not service_count.isdigit():
    raise SystemExit(f"rendered serviceCount is not numeric: {service_count!r}")
if overall_title == "サービス状況を確認しています" or not overall_title:
    raise SystemExit(f"rendered overallTitle did not leave loading state: {overall_title!r}")
PY

echo "Rendered UI check passed"
