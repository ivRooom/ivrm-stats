from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from .config import Settings
from .db import Snapshot, StatusRepository
from .minecraft import MinecraftSource
from .models import (
    PublicHistoryDay,
    PublicHistoryRange,
    PublicHistoryResponse,
    PublicHistoryService,
    PublicService,
    PublicStatus,
    PublicStatusResponse,
    worst_status,
)


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

    def public_history(
        self,
        days: int = 30,
        now: datetime | None = None,
    ) -> PublicHistoryResponse:
        if not 1 <= days <= 30:
            raise ValueError("days must be between 1 and 30")

        generated_at = (now or datetime.now(UTC)).astimezone(UTC)
        start_date = generated_at.date() - timedelta(days=days - 1)
        start = datetime.combine(start_date, time.min, tzinfo=UTC)
        current_services = {
            service.id: service for service in self.public_status(generated_at).services
        }

        minecraft = current_services["minecraft-network"]
        herta = current_services["herta-discord-bot"]
        minecraft_days, minecraft_availability = self._daily_history(
            self.minecraft.history_samples(start, generated_at),
            start_date,
            days,
        )
        herta_days, herta_availability = self._daily_history(
            [
                (snapshot.received_at.astimezone(UTC), snapshot.status)
                for snapshot in self.repository.snapshots_since("herta-discord-bot", start)
                if snapshot.received_at.astimezone(UTC) <= generated_at
            ],
            start_date,
            days,
        )

        return PublicHistoryResponse(
            generated_at=generated_at,
            range=PublicHistoryRange(
                days=days,
                from_date=start_date,
                to_date=generated_at.date(),
            ),
            services=[
                PublicHistoryService(
                    id=minecraft.id,
                    group=minecraft.group,
                    name=minecraft.name,
                    description=minecraft.description,
                    current_status=minecraft.status,
                    availability_percent=minecraft_availability,
                    days=minecraft_days,
                ),
                PublicHistoryService(
                    id=herta.id,
                    group=herta.group,
                    name=herta.name,
                    description=herta.description,
                    current_status=herta.status,
                    availability_percent=herta_availability,
                    days=herta_days,
                ),
            ],
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

    @staticmethod
    def _daily_history(
        samples: list[tuple[datetime, PublicStatus]],
        start_date: date,
        days: int,
    ) -> tuple[list[PublicHistoryDay], float | None]:
        buckets: dict[date, list[PublicStatus]] = {
            start_date + timedelta(days=index): [] for index in range(days)
        }
        for recorded_at, status in samples:
            sample_date = recorded_at.astimezone(UTC).date()
            if sample_date in buckets:
                buckets[sample_date].append(status)

        result: list[PublicHistoryDay] = []
        operational_total = 0
        known_total = 0
        for day, values in buckets.items():
            known = [status for status in values if status != PublicStatus.UNKNOWN]
            operational = sum(status == PublicStatus.OPERATIONAL for status in known)
            day_availability = round((operational / len(known)) * 100, 1) if known else None
            result.append(
                PublicHistoryDay(
                    date=day,
                    status=worst_status(known) if known else PublicStatus.UNKNOWN,
                    samples=len(values),
                    availability_percent=day_availability,
                )
            )
            operational_total += operational
            known_total += len(known)

        availability = (
            round((operational_total / known_total) * 100, 2)
            if known_total
            else None
        )
        return result, availability
