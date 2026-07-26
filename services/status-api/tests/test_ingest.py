from __future__ import annotations

import hashlib
import time

from fastapi.testclient import TestClient

from conftest import payload, signed_request


def test_accepts_valid_hmac_payload(client: TestClient) -> None:
    body, headers = signed_request(payload())
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 202
    assert response.json()["accepted"] is True


def test_rejects_invalid_signature(client: TestClient) -> None:
    body, headers = signed_request(payload(), secret="wrong-secret")
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_rejects_modified_body(client: TestClient) -> None:
    body, headers = signed_request(payload())
    modified = body.replace(b"operational", b"degraded")
    response = client.post("/api/internal/status-ingest", content=modified, headers=headers)
    assert response.status_code == 401


def test_rejects_expired_timestamp(client: TestClient) -> None:
    body, headers = signed_request(payload(), timestamp=int(time.time()) - 121)
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 401


def test_rejects_future_timestamp(client: TestClient) -> None:
    body, headers = signed_request(payload(), timestamp=int(time.time()) + 121)
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 401


def test_rejects_replayed_request_id(client: TestClient) -> None:
    request_id = "11111111-1111-4111-8111-111111111111"
    body, headers = signed_request(payload(), request_id=request_id)
    assert client.post("/api/internal/status-ingest", content=body, headers=headers).status_code == 202
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 409


def test_rejects_unknown_service(client: TestClient) -> None:
    body, headers = signed_request(payload(), service_id="unknown-service")
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 401


def test_rejects_service_id_mismatch(client: TestClient) -> None:
    data = payload()
    data["service"] = {
        "id": "another-service",
        "name": "Herta",
        "group": "Discordサービス",
        "type": "discord_bot",
    }
    body, headers = signed_request(data)
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 400


def test_rejects_extra_fields(client: TestClient) -> None:
    data = payload()
    data["checks"] = {"database": {"status": "ok"}}
    body, headers = signed_request(data)
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 400


def test_rejects_invalid_status(client: TestClient) -> None:
    body, headers = signed_request(payload(status="healthy"))
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 400


def test_rejects_naive_datetime(client: TestClient) -> None:
    body, headers = signed_request(payload(checked_at="2026-07-25T03:00:00"))
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 400


def test_rejects_non_json_content_type(client: TestClient) -> None:
    body, headers = signed_request(payload())
    headers["Content-Type"] = "text/plain"
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 415


def test_rejects_oversized_body(client: TestClient) -> None:
    body, headers = signed_request(payload())
    headers["Content-Length"] = "999999"
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 413


def test_rejects_body_hash_header_tampering(client: TestClient) -> None:
    body, headers = signed_request(payload())
    headers["X-IVRM-Body-SHA256"] = hashlib.sha256(b"different").hexdigest()
    response = client.post("/api/internal/status-ingest", content=body, headers=headers)
    assert response.status_code == 401
