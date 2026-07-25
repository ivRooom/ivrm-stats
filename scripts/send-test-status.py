#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from uuid import uuid4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a signed Herta status payload")
    parser.add_argument(
        "--url",
        default="https://stats.ivrm.jp/api/internal/status-ingest",
    )
    parser.add_argument(
        "--status",
        choices=["operational", "maintenance", "degraded", "outage", "unknown"],
        default="operational",
    )
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--summary", default="正常に稼働しています")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    secret = os.getenv("HERTA_INGEST_SECRET")
    if not secret:
        raise SystemExit("HERTA_INGEST_SECRET is required")

    payload = {
        "schema_version": "1.0",
        "service": {
            "id": "herta-discord-bot",
            "name": "Herta",
            "group": "Discordサービス",
            "type": "discord_bot",
        },
        "status": args.status,
        "checked_at": datetime.now(UTC).isoformat(),
        "version": args.version,
        "summary": args.summary,
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body_hash = hashlib.sha256(body).hexdigest()
    timestamp = int(time.time())
    request_id = str(uuid4())
    canonical = "\n".join(
        [
            "POST",
            "/api/internal/status-ingest",
            str(timestamp),
            request_id,
            "herta-discord-bot",
            body_hash,
        ]
    )
    signature = hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    request = urllib.request.Request(
        args.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-IVRM-Service-Id": "herta-discord-bot",
            "X-IVRM-Timestamp": str(timestamp),
            "X-IVRM-Request-Id": request_id,
            "X-IVRM-Body-SHA256": body_hash,
            "X-IVRM-Signature": f"v1={signature}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(response.status)
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.code)
        print(exc.read().decode("utf-8"))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
