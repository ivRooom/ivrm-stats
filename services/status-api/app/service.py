from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .config import Settings
from .db import Snapshot, StatusRepository
from .minecraft import MinecraftSource
from .models import PublicService, PublicStatus, PublicStatusResponse, worst_status


class StatusService:
    def __init__(self, settings: Settings, repository: StatusRepository) -> None:
        self.settings = settings
        self.repository = repository
        self.minecraft = MinecraftSource(
            current_path=settings.minecraft_current_path,
            history_path=settings.minecraft_history_path,
            stale_after_seconds=settings.minecraft_stale_after_seconds,
        )

    def public_status(self, now: datetime | None = None) -> PublicStatusResponse:
        generated_at = (now or datetime.now(UTC)).astimezone(UTC)
        services = [
            self.minecraft.public_service(generated_at),
            self._herta_service(generated_at),
        ]
        return PublicStatusResponse(
            generated_at=generated_at,
            overall_status=worst_status([service.status for service in services]),
            services=services,
            incidents=[],
        )

    def _herta_service(self, now: datetime) -> PublicService:
        latest = self.repository.latest_snapshot("herta-discord-bot")
        since = now - timedelta(hours=24)
        timeline = self._timeline(
            self.repository.snapshots_since("herta-discord-bot", since),
            since,
            now,
        )

        if latest is None:
            return PublicService(
                id="herta-discord-bot",
                group="Discordサービス",
                name="Herta",
                description="ivRooom Discord Bot",
                status=PublicStatus.UNKNOWN,
                timeline=timeline,
                meta={"type": "discord_bot"},
            )

        age_seconds = (now - latest.received_at.astimezone(UTC)).total_seconds()
        status = (
            PublicStatus.UNKNOWN
            if age_seconds > self.settings.herta_stale_after_seconds
            else latest.status
        )
        meta: dict[str, str] = {"type": "discord_bot"}
        if latest.version:
            meta["version"] = latest.version

        return PublicService(
            id="herta-discord-bot",
            group="Discordサービス",
            name="Herta",
            description="ivRooom Discord Bot",
            status=status,
            checked_at=latest.checked_at,
            last_received_at=latest.received_at,
            timeline=timeline,
            meta=meta,
        )

    @staticmethod
    def _timeline(
        snapshots: list[Snapshot],
        start: datetime,
        end: datetime,
    ) -> list[PublicStatus]:
        buckets: list[list[PublicStatus]] = [[] for _ in range(24)]
        for snapshot in snapshots:
            received = snapshot.received_at.astimezone(UTC)
            if received < start or received > end:
                continue
            index = min(23, int((received - start).total_seconds() // 3600))
            buckets[index].append(snapshot.status)
        return [worst_status(bucket) if bucket else PublicStatus.UNKNOWN for bucket in buckets]
