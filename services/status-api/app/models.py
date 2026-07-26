from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PublicStatus(StrEnum):
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    DEGRADED = "degraded"
    OUTAGE = "outage"
    UNKNOWN = "unknown"


STATUS_PRIORITY: dict[PublicStatus, int] = {
    PublicStatus.OPERATIONAL: 0,
    PublicStatus.MAINTENANCE: 1,
    PublicStatus.DEGRADED: 2,
    PublicStatus.OUTAGE: 3,
    PublicStatus.UNKNOWN: 4,
}


def worst_status(values: list[PublicStatus]) -> PublicStatus:
    if not values:
        return PublicStatus.UNKNOWN
    return max(values, key=lambda status: STATUS_PRIORITY[status])


class IngestService(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    name: str = Field(min_length=1, max_length=80)
    group: str = Field(min_length=1, max_length=80)
    type: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{2,63}$")


class IngestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    service: IngestService
    status: PublicStatus
    checked_at: datetime
    version: str | None = Field(default=None, max_length=64)
    summary: str = Field(min_length=1, max_length=160)

    @field_validator("checked_at")
    @classmethod
    def checked_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checked_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_registered_service_shape(self) -> "IngestPayload":
        if self.service.id == "herta-discord-bot":
            expected = {
                "name": "Herta",
                "group": "Discordサービス",
                "type": "discord_bot",
            }
            actual = {
                "name": self.service.name,
                "group": self.service.group,
                "type": self.service.type,
            }
            if actual != expected:
                raise ValueError("service metadata does not match the registered service")
        return self


class PublicService(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    group: str
    name: str
    description: str
    status: PublicStatus
    checked_at: datetime | None = None
    last_received_at: datetime | None = None
    timeline: list[PublicStatus]
    meta: dict[str, Any] = Field(default_factory=dict)


class PublicStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    overall_status: PublicStatus
    services: list[PublicService]
    incidents: list[dict[str, Any]] = Field(default_factory=list)


class PublicHistoryDay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    status: PublicStatus
    samples: int = Field(ge=0)
    availability_percent: float | None = Field(default=None, ge=0, le=100)


class PublicHistoryService(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    group: str
    name: str
    description: str
    current_status: PublicStatus
    availability_percent: float | None = Field(default=None, ge=0, le=100)
    days: list[PublicHistoryDay]


class PublicHistoryRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(ge=1, le=30)
    from_date: date
    to_date: date


class PublicHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    range: PublicHistoryRange
    services: list[PublicHistoryService]
    incidents: list[dict[str, Any]] = Field(default_factory=list)
