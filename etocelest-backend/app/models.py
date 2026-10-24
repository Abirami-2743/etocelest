"""Domain records persisted in MongoDB.

`missions`: one document per review (`_id` = mission id). It also carries `event_seq`, an
atomically incremented counter used to number events.
`mission_events`: append-only log of the debate; the single source of truth for rounds, turns
and judge notes (rounds are *folded* from events on read, see `app.domain.events`). An event's
`seq` doubles as the SSE cursor; because it comes from a counter that only ever increments, it is
never reused, even after a partial round is truncated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC)


class MissionStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"

    ACTIVE = (PENDING, RUNNING)


@dataclass
class Mission:
    id: str
    owner_id: str
    name: str
    launch_date: date
    context: str
    # Debate configuration frozen at creation so a resumed run behaves identically.
    min_rounds: int
    max_rounds: int
    max_shift_days: int
    model_agent: str
    model_judge: str

    status: str = MissionStatus.PENDING
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    completed_at: datetime | None = None
    rounds_completed: int = 0

    verdict: str | None = None
    verdict_summary: str | None = None
    recommended_date: date | None = None
    shift_days: int | None = None
    confidence: int | None = None
    resolution: str | None = None

    error: str | None = None
    grounding: dict[str, Any] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class MissionEvent:
    id: int  # per-mission sequence number (SSE cursor)
    mission_id: str
    type: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=utcnow)
