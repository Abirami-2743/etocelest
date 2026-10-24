"""API request/response models (camelCase on the wire, as the frontend expects)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class MissionCreate(CamelModel):
    name: str = Field(min_length=3, max_length=120)
    launch_date: date
    context: str = Field(default="", max_length=2000)

    @field_validator("name", "context")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("name must be at least 3 characters")
        return v


class MissionCreated(CamelModel):
    mission_id: str


class MissionSummary(CamelModel):
    id: str
    name: str
    launch_date: date
    status: Literal["pending", "running", "complete", "failed"]
    created_at: datetime
    completed_at: datetime | None = None
    verdict: str | None = None
    recommended_date: date | None = None
    shift_days: int | None = None
    confidence: int | None = None
    resolution: str | None = None
    rounds_completed: int = 0
    error: str | None = None


class MissionDetail(MissionSummary):
    context: str
    verdict_summary: str | None = None
    rounds: list[dict[str, Any]]
    grounding: dict[str, Any] | None = None
    limits: dict[str, int]
    models: dict[str, str]
    usage: dict[str, int]


class Preset(CamelModel):
    name: str
    launch_date: date
    context: str


class AgentInfo(CamelModel):
    id: str
    name: str
    role: str
