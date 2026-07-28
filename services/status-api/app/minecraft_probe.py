from __future__ import annotations

import json
import socket
import struct
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class MinecraftProbeResult:
    reachable: bool | None
    checked_at: datetime
    latency_ms: int | None = None
    players_online: int | None = None
    players_max: int | None = None
    version_name: str | None = None
    reason_code: str | None = None


class MinecraftStatusProbe:
    def __init__(
        self,
        *,
        connect_host: str,
        server_address: str,
        port: int,
        timeout_seconds: float,
        cache_seconds: int,
    ) -> None:
        self.connect_host = connect_host
        self.server_address = server_address
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._cached_result: MinecraftProbeResult | None = None
        self._cached_until = 0.0

    def check(self) -> MinecraftProbeResult:
        now_monotonic = time.monotonic()
        with self._lock:
            if self._cached_result is not None and now_monotonic < self._cached_until:
                return self._cached_result

            result = self._perform_probe()
            self._cached_result = result
            self._cached_until = time.monotonic() + self.cache_seconds
            return result

    def _perform_probe(self) -> MinecraftProbeResult:
        checked_at = datetime.now(UTC)
        started = time.perf_counter()

        try:
            with socket.create_connection(
                (self.connect_host, self.port),
                timeout=self.timeout_seconds,
            ) as connection:
                connection.settimeout(self.timeout_seconds)
                self._send_status_request(connection)
                payload = self._read_status_response(connection)
        except socket.gaierror:
            return MinecraftProbeResult(
                reachable=None,
                checked_at=checked_at,
                reason_code="name_resolution_failed",
            )
        except (TimeoutError, ConnectionRefusedError, socket.timeout):
            return MinecraftProbeResult(
                reachable=False,
                checked_at=checked_at,
                reason_code="connection_failed",
            )
        except (OSError, ValueError, json.JSONDecodeError):
            return MinecraftProbeResult(
                reachable=False,
                checked_at=checked_at,
                reason_code="invalid_minecraft_response",
            )

        players = payload.get("players") if isinstance(payload.get("players"), dict) else {}
        version = payload.get("version") if isinstance(payload.get("version"), dict) else {}
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))

        return MinecraftProbeResult(
            reachable=True,
            checked_at=checked_at,
            latency_ms=latency_ms,
            players_online=self._optional_int(players.get("online")),
            players_max=self._optional_int(players.get("max")),
            version_name=self._optional_text(version.get("name")),
        )

    def _send_status_request(self, connection: socket.socket) -> None:
        address = self.server_address.encode("utf-8")
        handshake = b"".join(
            (
                self._encode_varint(0),
                self._encode_varint(47),
                self._encode_varint(len(address)),
                address,
                struct.pack(">H", self.port),
                self._encode_varint(1),
            )
        )
        connection.sendall(self._encode_varint(len(handshake)) + handshake)
        connection.sendall(b"\x01\x00")

    def _read_status_response(self, connection: socket.socket) -> dict[str, Any]:
        packet_length = self._read_varint(connection)
        if packet_length <= 0 or packet_length > 1_048_576:
            raise ValueError("invalid packet length")

        packet_id = self._read_varint(connection)
        if packet_id != 0:
            raise ValueError("unexpected packet id")

        json_length = self._read_varint(connection)
        if json_length <= 0 or json_length > packet_length:
            raise ValueError("invalid json length")

        raw = self._recv_exact(connection, json_length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("status payload must be an object")
        if not isinstance(payload.get("players"), dict):
            raise ValueError("status payload is missing players")
        if not isinstance(payload.get("version"), dict):
            raise ValueError("status payload is missing version")
        return payload

    @staticmethod
    def _encode_varint(value: int) -> bytes:
        encoded = bytearray()
        while True:
            current = value & 0x7F
            value >>= 7
            if value:
                current |= 0x80
            encoded.append(current)
            if not value:
                return bytes(encoded)

    @classmethod
    def _read_varint(cls, connection: socket.socket) -> int:
        value = 0
        for index in range(5):
            current = cls._recv_exact(connection, 1)[0]
            value |= (current & 0x7F) << (7 * index)
            if not current & 0x80:
                return value
        raise ValueError("varint is too long")

    @staticmethod
    def _recv_exact(connection: socket.socket, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            chunk = connection.recv(size - len(data))
            if not chunk:
                raise ValueError("connection closed before packet completed")
            data.extend(chunk)
        return bytes(data)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
