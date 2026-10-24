"""HTTP routes."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse

from app import __version__
from app.domain import events as ev
from app.domain.agents import AGENTS
from app.models import Mission, MissionStatus
from app.schemas import (
    AgentInfo,
    MissionCreate,
    MissionCreated,
    MissionDetail,
    MissionSummary,
    Preset,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9-]{16,64}$")
_PRESETS_PATH = Path(__file__).resolve().parent.parent / "data" / "presets.json"
HEARTBEAT_SECONDS = 15.0


def get_container(request: Request):  # noqa: ANN201
    return request.app.state.container


Container = Annotated[Any, Depends(get_container)]


def client_id(x_client_id: Annotated[str | None, Header()] = None) -> str:
    """Anonymous per-browser owner id (random UUID kept in the browser). Scopes all missions."""
    if not x_client_id or not _CLIENT_ID_RE.match(x_client_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing or invalid X-Client-Id header")
    return x_client_id


Owner = Annotated[str, Depends(client_id)]


def _detail(m: Mission, events: list[Any]) -> MissionDetail:
    rounds = ev.fold_rounds([(e.type, e.payload) for e in events])
    base = MissionSummary.model_validate(m).model_dump()
    return MissionDetail(
        **base,
        context=m.context,
        verdict_summary=m.verdict_summary,
        rounds=rounds,
        grounding=m.grounding,
        limits={"minRounds": m.min_rounds, "maxRounds": m.max_rounds, "maxShiftDays": m.max_shift_days},
        models={"agent": m.model_agent, "judge": m.model_judge},
        usage={"promptTokens": m.prompt_tokens, "completionTokens": m.completion_tokens},
    )


async def _owned(c: Any, mission_id: str, owner: str) -> Mission:
    m = await c.repo.get(mission_id, owner)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mission not found")
    return m


# ------------------------------------------------------------------ meta
@router.get("/health")
async def health(c: Container) -> dict[str, Any]:
    db_ok = await c.db.ping()
    s = c.settings
    body = {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "database": "ok" if db_ok else "unreachable",
        "llm": {
            "provider": "groq",
            "agentModel": s.groq_model_agent,
            "judgeModel": s.groq_model_judge,
        },
        "grounding": s.grounding_enabled,
        "activeDebates": c.runner.active_count,
    }
    return body


@router.get("/agents", response_model=list[AgentInfo])
async def agents() -> list[AgentInfo]:
    return [AgentInfo(id=a.id, name=a.name, role=a.role) for a in AGENTS]


@router.get("/presets", response_model=list[Preset])
async def presets() -> list[Preset]:
    raw = json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
    today = datetime.now(UTC).date()
    return [
        Preset(name=p["name"], launch_date=today + timedelta(days=int(p["leadDays"])), context=p["context"])
        for p in raw
    ]


# -------------------------------------------------------------- missions
@router.post("/missions", status_code=status.HTTP_201_CREATED, response_model=MissionCreated)
async def create_mission(body: MissionCreate, request: Request, c: Container, owner: Owner) -> MissionCreated:
    s = c.settings
    today = datetime.now(UTC).date()
    if body.launch_date < today:
        raise HTTPException(422, "Launch date must be today or later")
    if body.launch_date > today + timedelta(days=365 * 30):
        raise HTTPException(422, "Launch date is too far in the future")

    ip = request.client.host if request.client else "unknown"
    if not c.limiter.allow(f"ip:{ip}") or not c.limiter.allow(f"owner:{owner}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many reviews started recently. Try again later.")
    if await c.repo.count_active(owner) >= s.max_active_missions_per_owner:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "You already have reviews in progress. Wait for one to finish."
        )

    mission = Mission(
        id=uuid.uuid4().hex,
        owner_id=owner,
        name=body.name,
        launch_date=body.launch_date,
        context=body.context,
        status=MissionStatus.PENDING,
        min_rounds=s.min_rounds,
        max_rounds=s.max_rounds,
        max_shift_days=s.max_shift_days,
        model_agent=s.groq_model_agent,
        model_judge=s.groq_model_judge,
    )
    await c.repo.create_mission(mission)
    c.runner.start(mission.id)
    return MissionCreated(mission_id=mission.id)


@router.get("/missions", response_model=list[MissionSummary])
async def list_missions(
    c: Container, owner: Owner, limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Mission]:
    return await c.repo.list_for_owner(owner, limit, offset)


@router.get("/missions/{mission_id}", response_model=MissionDetail)
async def get_mission(mission_id: str, c: Container, owner: Owner) -> MissionDetail:
    m = await _owned(c, mission_id, owner)
    return _detail(m, await c.repo.events_after(mission_id))


@router.delete("/missions/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mission(mission_id: str, c: Container, owner: Owner) -> Response:
    await _owned(c, mission_id, owner)
    await c.runner.cancel(mission_id)
    await c.repo.delete(mission_id)
    c.notifier.notify(mission_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/missions/{mission_id}/retry", status_code=status.HTTP_202_ACCEPTED, response_model=MissionCreated)
async def retry_mission(mission_id: str, c: Container, owner: Owner) -> MissionCreated:
    m = await _owned(c, mission_id, owner)
    if m.status != MissionStatus.FAILED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed missions can be retried")
    if await c.repo.count_active(owner) >= c.settings.max_active_missions_per_owner:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "You already have reviews in progress.")
    await c.repo.reset_for_retry(mission_id)
    c.runner.start(mission_id)
    return MissionCreated(mission_id=mission_id)


def _sse(event_id: int | None, data: dict[str, Any]) -> bytes:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}data: {json.dumps(data, separators=(',', ':'))}\n\n".encode()


@router.get("/missions/{mission_id}/stream")
async def stream_mission(
    mission_id: str,
    request: Request,
    c: Container,
    owner: Owner,
    last_event_id: Annotated[str | None, Header()] = None,
    after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    """Server-Sent Events: replays persisted events after the cursor, then follows live."""
    await _owned(c, mission_id, owner)
    cursor = after
    if last_event_id and last_event_id.isdigit():
        cursor = max(cursor, int(last_event_id))

    async def gen() -> AsyncIterator[bytes]:
        nonlocal cursor
        yield b"retry: 3000\n\n"
        while True:
            waiter = c.notifier.waiter(mission_id)  # before the query: no lost wake-ups
            batch = await c.repo.events_after(mission_id, cursor)
            for e in batch:
                cursor = e.id
                yield _sse(e.id, {"type": e.type, **e.payload})
                if e.type in ev.TERMINAL:
                    return
            if batch:
                continue
            m = await c.repo.get(mission_id)
            if m is None or m.status in (MissionStatus.COMPLETE, MissionStatus.FAILED):
                return
            try:
                await asyncio.wait_for(waiter.wait(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                yield b": ping\n\n"
            if await request.is_disconnected():
                return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
