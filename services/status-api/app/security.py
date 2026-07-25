from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from uuid import UUID

from .config import Settings

_SIGNATURE_RE = re.compile(r"^v1=([0-9a-f]{64})$")
_BODY_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class AuthHeaders:
    service_id: str
    timestamp: int
    request_id: str
    body_sha256: str
    signature: str


class AuthenticationError(RuntimeError):
    pass


class UnsupportedServiceError(AuthenticationError):
    pass


class RateLimitError(RuntimeError):
    pass


class SlidingWindowRateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self.limit = limit_per_minute
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, service_id: str, now: float | None = None) -> None:
        current = now if now is not None else time.time()
        cutoff = current - 60
        with self._lock:
            events = self._events[service_id]
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= self.limit:
                raise RateLimitError(service_id)
            events.append(current)


def parse_headers(
    service_id: str | None,
    timestamp: str | None,
    request_id: str | None,
    body_sha256: str | None,
    signature: str | None,
) -> AuthHeaders:
    if not all([service_id, timestamp, request_id, body_sha256, signature]):
        raise AuthenticationError("missing authentication headers")

    try:
        parsed_timestamp = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("invalid timestamp") from exc

    try:
        parsed_request_id = str(UUID(request_id))
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("invalid request id") from exc

    if not _BODY_HASH_RE.fullmatch(body_sha256):
        raise AuthenticationError("invalid body hash")
    if not _SIGNATURE_RE.fullmatch(signature):
        raise AuthenticationError("invalid signature")

    return AuthHeaders(
        service_id=service_id,
        timestamp=parsed_timestamp,
        request_id=parsed_request_id,
        body_sha256=body_sha256,
        signature=signature,
    )


def canonical_string(headers: AuthHeaders) -> str:
    return "\n".join(
        [
            "POST",
            "/api/internal/status-ingest",
            str(headers.timestamp),
            headers.request_id,
            headers.service_id,
            headers.body_sha256,
        ]
    )


def verify_request(
    settings: Settings,
    headers: AuthHeaders,
    body: bytes,
    now_epoch: int | None = None,
) -> None:
    secret = settings.secret_for(headers.service_id)
    if secret is None:
        raise UnsupportedServiceError(headers.service_id)

    current = int(time.time()) if now_epoch is None else now_epoch
    if abs(current - headers.timestamp) > settings.max_clock_skew_seconds:
        raise AuthenticationError("timestamp outside accepted window")

    actual_body_hash = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(actual_body_hash, headers.body_sha256):
        raise AuthenticationError("body hash mismatch")

    expected = hmac.new(
        secret.encode("utf-8"),
        canonical_string(headers).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    supplied = headers.signature.removeprefix("v1=")
    if not hmac.compare_digest(expected, supplied):
        raise AuthenticationError("signature mismatch")
