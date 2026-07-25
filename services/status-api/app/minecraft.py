from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import PublicService, PublicStatus, worst_status


@dataclass(frozen=True, slots=True)
class MinecraftSource:
    current_path: Path
    history_path: Path
    stale_after_seconds: int

    def public_service(self, now: datetime) -> PublicService:
        current = self._read_json(self.current_path)
        history = self._read_json(self.history_path)

        if not isinstance(current, dict):
            return self._unknown_service()

        collected_at = self._parse_datetime(current.get("collected_at"))
        raw_status = self._normalize_status(current.get("status"))
        is_stale = (
            collected_at is None
            or (now - collected_at).total_seconds() > self.stale_after_seconds
        )
        status = PublicStatus.UNKNOWN if is_stale else raw_status

        server = current.get("server") if isinstance(current.get("server"), dict) else {}
        players = current.get("players") if isinstance(current.get("players"), dict) else {}
        settings = current.get("settings") if isinstance(current.get("settings"), dict) else {}

        history_items = history if isinstance(history, list) else history.get("history", []) if isinstance(history, dict) else []

        return PublicService(
            id="minecraft-network",
            group="ゲームサービス",
            name="Minecraft Network",
            description=str(server.get("name") or "Minecraftサーバー"),
            status=status,
            checked_at=collected_at,
            last_received_at=collected_at,
            timeline=self._timeline(history_items, now),
            meta={
                "type": "minecraft",
                "connection": str(server.get("connection") or "mc.ivrm.jp"),
                "playersOnline": self._safe_int(players.get("online"), 0),
                "playersMax": self._safe_int(
                    players.get("max"), self._safe_int(settings.get("max-players"), 0)
                ),
                "mode": str(server.get("mode") or "Minecraft Server"),
            },
        )

    def _unknown_service(self) -> PublicService:
        return PublicService(
            id="minecraft-network",
            group="ゲームサービス",
            name="Minecraft Network",
            description="Minecraftサーバー",
            status=PublicStatus.UNKNOWN,
            timeline=[PublicStatus.UNKNOWN] * 24,
            meta={
                "type": "minecraft",
                "connection": "mc.ivrm.jp",
                "playersOnline": 0,
                "playersMax": 0,
                "mode": "Minecraft Server",
            },
        )

    def _timeline(self, history: Any, now: datetime) -> list[PublicStatus]:
        if not isinstance(history, list):
            return [PublicStatus.UNKNOWN] * 24

        buckets: list[list[PublicStatus]] = [[] for _ in range(24)]
        start = now - timedelta(hours=24)
        for item in history:
            if not isinstance(item, dict):
                continue
            collected_at = self._parse_datetime(item.get("collected_at"))
            if collected_at is None or collected_at < start or collected_at > now:
                continue
            index = min(23, int((collected_at - start).total_seconds() // 3600))
            buckets[index].append(self._normalize_status(item.get("status")))

        return [worst_status(bucket) if bucket else PublicStatus.UNKNOWN for bucket in buckets]

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            if path.stat().st_size > 5_000_000:
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(UTC)

    @staticmethod
    def _normalize_status(value: Any) -> PublicStatus:
        normalized = str(value or "unknown").lower()
        aliases = {
            "online": PublicStatus.OPERATIONAL,
            "ok": PublicStatus.OPERATIONAL,
            "healthy": PublicStatus.OPERATIONAL,
            "up": PublicStatus.OPERATIONAL,
            "warning": PublicStatus.DEGRADED,
            "partial": PublicStatus.DEGRADED,
            "offline": PublicStatus.OUTAGE,
            "down": PublicStatus.OUTAGE,
            "critical": PublicStatus.OUTAGE,
        }
        if normalized in aliases:
            return aliases[normalized]
        try:
            return PublicStatus(normalized)
        except ValueError:
            return PublicStatus.UNKNOWN

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
