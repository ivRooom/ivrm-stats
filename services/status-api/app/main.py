from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .config import Settings
from .db import ReplayConflictError, StatusRepository
from .models import IngestPayload
from .security import (
    AuthenticationError,
    RateLimitError,
    SlidingWindowRateLimiter,
    UnsupportedServiceError,
    parse_headers,
    verify_request,
)
from .service import StatusService

logger = logging.getLogger("ivrm_status_api")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, ensure_ascii=False, sort_keys=True))


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": code, "message": message})


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    repository = StatusRepository(active_settings.db_path)
    repository.initialize(active_settings.herta_stale_after_seconds)
    status_service = StatusService(active_settings, repository)
    rate_limiter = SlidingWindowRateLimiter(active_settings.rate_limit_per_minute)

    app = FastAPI(
        title="ivRooom Status API",
        version="1.0.0",
        docs_url="/docs" if active_settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if active_settings.enable_docs else None,
    )
    app.state.settings = active_settings
    app.state.repository = repository
    app.state.status_service = status_service
    app.state.rate_limiter = rate_limiter

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return _error(400, "invalid_request", "request validation failed")

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        try:
            repository.healthcheck()
        except Exception:
            _log("status_api_health_failed", reason_code="database_unavailable")
            return JSONResponse(status_code=503, content={"status": "error"})
        return JSONResponse(status_code=200, content={"status": "ok"})

    @app.get("/api/status.json")
    async def public_status() -> JSONResponse:
        response = status_service.public_status()
        return JSONResponse(
            status_code=200,
            content=json.loads(response.model_dump_json()),
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    @app.post("/api/internal/status-ingest", status_code=202)
    async def status_ingest(
        request: Request,
        x_ivrm_service_id: str | None = Header(default=None),
        x_ivrm_timestamp: str | None = Header(default=None),
        x_ivrm_request_id: str | None = Header(default=None),
        x_ivrm_body_sha256: str | None = Header(default=None),
        x_ivrm_signature: str | None = Header(default=None),
    ) -> JSONResponse:
        content_type = request.headers.get("content-type", "")
        if not content_type.lower().startswith("application/json"):
            return _error(415, "unsupported_media_type", "application/json is required")

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > active_settings.max_body_bytes:
                    return _error(413, "payload_too_large", "request body is too large")
            except ValueError:
                return _error(400, "invalid_request", "invalid content length")

        body = await request.body()
        if len(body) > active_settings.max_body_bytes:
            return _error(413, "payload_too_large", "request body is too large")

        try:
            auth_headers = parse_headers(
                x_ivrm_service_id,
                x_ivrm_timestamp,
                x_ivrm_request_id,
                x_ivrm_body_sha256,
                x_ivrm_signature,
            )
            verify_request(active_settings, auth_headers, body)
            rate_limiter.check(auth_headers.service_id)
        except UnsupportedServiceError:
            _log("status_ingest_rejected", reason_code="unauthorized_service")
            return _error(401, "unauthorized", "request authentication failed")
        except AuthenticationError:
            _log("status_ingest_rejected", reason_code="authentication_failed")
            return _error(401, "unauthorized", "request authentication failed")
        except RateLimitError:
            _log("status_ingest_rejected", service_id=x_ivrm_service_id, reason_code="rate_limited")
            return _error(429, "rate_limited", "too many requests")

        try:
            payload = IngestPayload.model_validate_json(body)
        except ValidationError:
            _log(
                "status_ingest_rejected",
                service_id=auth_headers.service_id,
                reason_code="invalid_schema",
            )
            return _error(400, "invalid_payload", "request payload is invalid")

        if payload.service.id != auth_headers.service_id:
            _log(
                "status_ingest_rejected",
                service_id=auth_headers.service_id,
                reason_code="service_id_mismatch",
            )
            return _error(400, "invalid_payload", "request payload is invalid")

        received_at = datetime.now(UTC)
        try:
            repository.save_ingest(
                payload=payload,
                request_id=auth_headers.request_id,
                received_at=received_at,
                replay_ttl_seconds=active_settings.replay_ttl_seconds,
                history_retention_days=active_settings.history_retention_days,
            )
        except ReplayConflictError:
            _log(
                "status_ingest_rejected",
                service_id=auth_headers.service_id,
                reason_code="replay_detected",
            )
            return _error(409, "replay_detected", "request has already been processed")
        except Exception:
            _log(
                "status_ingest_failed",
                service_id=auth_headers.service_id,
                reason_code="storage_failed",
            )
            return _error(500, "internal_error", "request could not be processed")

        _log(
            "status_ingest_accepted",
            service_id=payload.service.id,
            status=payload.status.value,
            received_at=received_at.isoformat(),
        )
        return JSONResponse(
            status_code=202,
            content={
                "accepted": True,
                "service_id": payload.service.id,
                "received_at": received_at.isoformat(),
            },
        )

    return app


app = create_app()
