from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.minecraft import MinecraftSource
from app.minecraft_probe import MinecraftProbeResult


class StubProbe:
    def __init__(self, result: MinecraftProbeResult) -> None:
        self.result = result

    def check(self) -> MinecraftProbeResult:
        return self.result


def write_snapshot(path: Path, *, now: datetime, status: str = "online") -> None:
    path.write_text(
        json.dumps(
            {
                "collected_at": now.isoformat(),
                "status": status,
                "server": {
                    "name": "GT New Horizons",
                    "mode": "GTNH 2.8.4",
                    "connection": "mc.ivrm.jp",
                },
                "players": {"online": 4, "max": 10},
            }
        ),
        encoding="utf-8",
    )


def source_with_probe(
    tmp_path: Path,
    result: MinecraftProbeResult,
    *,
    now: datetime,
    raw_status: str = "online",
) -> MinecraftSource:
    current = tmp_path / "current.json"
    history = tmp_path / "history.json"
    write_snapshot(current, now=now, status=raw_status)
    history.write_text("[]", encoding="utf-8")
    return MinecraftSource(
        current_path=current,
        history_path=history,
        stale_after_seconds=300,
        probe=StubProbe(result),  # type: ignore[arg-type]
    )


def test_unreachable_server_overrides_fresh_online_snapshot(tmp_path: Path) -> None:
    now = datetime(2026, 7, 28, 3, 0, tzinfo=UTC)
    source = source_with_probe(
        tmp_path,
        MinecraftProbeResult(reachable=False, checked_at=now),
        now=now,
    )

    service = source.public_service(now)

    assert service.status.value == "outage"
    assert service.timeline[-1].value == "outage"
    assert service.meta["probeStatus"] == "unreachable"


def test_valid_minecraft_ping_overrides_stale_offline_snapshot(tmp_path: Path) -> None:
    now = datetime(2026, 7, 28, 3, 0, tzinfo=UTC)
    old = now - timedelta(hours=1)
    source = source_with_probe(
        tmp_path,
        MinecraftProbeResult(
            reachable=True,
            checked_at=now,
            latency_ms=24,
            players_online=2,
            players_max=10,
            version_name="GTNH 2.8.4",
        ),
        now=old,
        raw_status="offline",
    )

    service = source.public_service(now)

    assert service.status.value == "operational"
    assert service.meta["playersOnline"] == 2
    assert service.meta["playersMax"] == 10
    assert service.meta["latencyMs"] == 24
    assert service.meta["serverVersion"] == "GTNH 2.8.4"


def test_planned_maintenance_is_not_reclassified_as_outage(tmp_path: Path) -> None:
    now = datetime(2026, 7, 28, 3, 0, tzinfo=UTC)
    source = source_with_probe(
        tmp_path,
        MinecraftProbeResult(reachable=False, checked_at=now),
        now=now,
        raw_status="maintenance",
    )

    assert source.public_service(now).status.value == "maintenance"


def test_probe_can_report_runtime_without_snapshot_file(tmp_path: Path) -> None:
    now = datetime(2026, 7, 28, 3, 0, tzinfo=UTC)
    history = tmp_path / "history.json"
    history.write_text("[]", encoding="utf-8")
    source = MinecraftSource(
        current_path=tmp_path / "missing-current.json",
        history_path=history,
        stale_after_seconds=300,
        probe=StubProbe(  # type: ignore[arg-type]
            MinecraftProbeResult(
                reachable=True,
                checked_at=now,
                players_online=0,
                players_max=10,
            )
        ),
    )

    service = source.public_service(now)

    assert service.status.value == "operational"
    assert service.checked_at == now
    assert service.meta["probeStatus"] == "reachable"


def test_runtime_probe_is_added_to_history_samples(tmp_path: Path) -> None:
    now = datetime(2026, 7, 28, 3, 0, tzinfo=UTC)
    source = source_with_probe(
        tmp_path,
        MinecraftProbeResult(reachable=False, checked_at=now),
        now=now,
    )

    samples = source.history_samples(now - timedelta(days=1), now)

    assert samples[-1] == (now, source.public_service(now).status)
    assert samples[-1][1].value == "outage"
