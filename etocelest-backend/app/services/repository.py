"""Persistence operations on MongoDB. No multi-document transactions are required (works on a
standalone mongod or Atlas free tier); write ordering is chosen so a crash at any point is
recoverable (see `complete`)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pymongo import ReturnDocument

from app.db import Database
from app.domain import events as ev
from app.models import Mission, MissionEvent, MissionStatus, utcnow


class MissionGone(Exception):
    """The mission document no longer exists (deleted while its debate was running)."""


def _d(v: date | None) -> str | None:
    return v.isoformat() if v else None


def _pd(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


def to_doc(m: Mission) -> dict[str, Any]:
    return {
        "_id": m.id, "owner_id": m.owner_id, "name": m.name, "launch_date": _d(m.launch_date),
        "context": m.context, "min_rounds": m.min_rounds, "max_rounds": m.max_rounds,
        "max_shift_days": m.max_shift_days, "model_agent": m.model_agent, "model_judge": m.model_judge,
        "status": m.status, "created_at": m.created_at, "updated_at": m.updated_at,
        "completed_at": m.completed_at, "rounds_completed": m.rounds_completed,
        "verdict": m.verdict, "verdict_summary": m.verdict_summary,
        "recommended_date": _d(m.recommended_date), "shift_days": m.shift_days,
        "confidence": m.confidence, "resolution": m.resolution, "error": m.error,
        "grounding": m.grounding, "prompt_tokens": m.prompt_tokens,
        "completion_tokens": m.completion_tokens, "event_seq": 0,
    }


def from_doc(d: dict[str, Any]) -> Mission:
    return Mission(
        id=d["_id"], owner_id=d["owner_id"], name=d["name"], launch_date=_pd(d["launch_date"]),
        context=d.get("context", ""), min_rounds=d["min_rounds"], max_rounds=d["max_rounds"],
        max_shift_days=d["max_shift_days"], model_agent=d["model_agent"], model_judge=d["model_judge"],
        status=d["status"], created_at=d["created_at"], updated_at=d["updated_at"],
        completed_at=d.get("completed_at"), rounds_completed=d.get("rounds_completed", 0),
        verdict=d.get("verdict"), verdict_summary=d.get("verdict_summary"),
        recommended_date=_pd(d.get("recommended_date")), shift_days=d.get("shift_days"),
        confidence=d.get("confidence"), resolution=d.get("resolution"), error=d.get("error"),
        grounding=d.get("grounding"), prompt_tokens=d.get("prompt_tokens", 0),
        completion_tokens=d.get("completion_tokens", 0),
    )


class Repository:
    def __init__(self, db: Database) -> None:
        self._m = db.missions
        self._e = db.events

    # -- missions ----------------------------------------------------------
    async def create_mission(self, mission: Mission) -> Mission:
        await self._m.insert_one(to_doc(mission))
        return mission

    async def get(self, mission_id: str, owner_id: str | None = None) -> Mission | None:
        q: dict[str, Any] = {"_id": mission_id}
        if owner_id is not None:
            q["owner_id"] = owner_id
        d = await self._m.find_one(q)
        return from_doc(d) if d else None

    async def list_for_owner(self, owner_id: str, limit: int, offset: int) -> list[Mission]:
        cur = (
            self._m.find({"owner_id": owner_id})
            .sort([("created_at", -1), ("_id", 1)])
            .skip(offset)
            .limit(limit)
        )
        return [from_doc(d) for d in await cur.to_list(None)]

    async def count_active(self, owner_id: str) -> int:
        return await self._m.count_documents({"owner_id": owner_id, "status": {"$in": list(MissionStatus.ACTIVE)}})

    async def active_ids(self) -> list[str]:
        cur = self._m.find({"status": {"$in": list(MissionStatus.ACTIVE)}}, {"_id": 1}).sort("created_at", 1)
        return [d["_id"] for d in await cur.to_list(None)]

    async def delete(self, mission_id: str) -> None:
        await self._e.delete_many({"mission_id": mission_id})
        await self._m.delete_one({"_id": mission_id})

    async def _set(self, mission_id: str, **fields: Any) -> None:
        fields["updated_at"] = utcnow()
        await self._m.update_one({"_id": mission_id}, {"$set": fields})

    async def set_status(self, mission_id: str, status: str) -> None:
        await self._set(mission_id, status=status)

    async def save_grounding(self, mission_id: str, grounding: dict[str, Any]) -> None:
        await self._set(mission_id, grounding=grounding)

    async def add_usage(self, mission_id: str, prompt: int, completion: int) -> None:
        await self._m.update_one(
            {"_id": mission_id}, {"$inc": {"prompt_tokens": prompt, "completion_tokens": completion}}
        )

    # -- events ------------------------------------------------------------
    async def _next_seq(self, mission_id: str, count: int = 1) -> int:
        """Atomically reserve `count` sequence numbers; returns the first one."""
        d = await self._m.find_one_and_update(
            {"_id": mission_id}, {"$inc": {"event_seq": count}},
            projection={"event_seq": 1}, return_document=ReturnDocument.AFTER,
        )
        if d is None:
            raise MissionGone(mission_id)
        return int(d["event_seq"]) - count + 1

    async def append_event(self, mission_id: str, etype: str, payload: dict[str, Any]) -> int:
        seq = await self._next_seq(mission_id)
        await self._e.insert_one(
            {"mission_id": mission_id, "seq": seq, "type": etype, "payload": payload, "created_at": utcnow()}
        )
        if etype == ev.JUDGE_NOTE:
            await self._m.update_one({"_id": mission_id}, {"$set": {"rounds_completed": payload["round"]}})
        return seq

    async def events_after(self, mission_id: str, after_id: int = 0) -> list[MissionEvent]:
        cur = self._e.find({"mission_id": mission_id, "seq": {"$gt": after_id}}).sort("seq", 1)
        return [
            MissionEvent(id=d["seq"], mission_id=d["mission_id"], type=d["type"],
                         payload=d.get("payload", {}), created_at=d["created_at"])
            for d in await cur.to_list(None)
        ]

    async def truncate_incomplete_round(self, mission_id: str) -> None:
        """Drop events of a round that never reached its judge_note (crash/restart recovery)."""
        started: int | None = None
        for e in await self.events_after(mission_id):
            if e.type == ev.ROUND_START:
                started = e.id
            elif e.type == ev.JUDGE_NOTE:
                started = None
        if started is not None:
            await self._e.delete_many({"mission_id": mission_id, "seq": {"$gte": started}})
        await self._e.delete_many({"mission_id": mission_id, "type": ev.ERROR})

    # -- terminal transitions ---------------------------------------------
    async def complete(
        self,
        mission_id: str,
        *,
        note_payload: dict[str, Any],
        verdict: str,
        summary: str,
        recommended: date,
        shift_days: int,
        confidence: int,
        resolution: str,
    ) -> None:
        """Record the final judge note + `done`, then flip the mission to complete.

        Events are written FIRST: a stream that sees `status=complete` is guaranteed to find the
        `done` event already stored. A crash between the two writes leaves `done` in the log with
        the mission still running; `finalize_from_log` repairs that on recovery.
        """
        await self.append_event(mission_id, ev.JUDGE_NOTE, note_payload)
        await self.append_event(mission_id, ev.DONE, {})
        await self._mark_complete(
            mission_id, rounds=note_payload["round"], verdict=verdict, summary=summary,
            recommended=recommended, shift_days=shift_days, confidence=confidence, resolution=resolution,
        )

    async def _mark_complete(
        self, mission_id: str, *, rounds: int, verdict: str, summary: str, recommended: date,
        shift_days: int, confidence: int, resolution: str,
    ) -> None:
        await self._set(
            mission_id, status=MissionStatus.COMPLETE, rounds_completed=rounds, verdict=verdict,
            verdict_summary=summary, recommended_date=_d(recommended), shift_days=shift_days,
            confidence=confidence, resolution=resolution, error=None, completed_at=utcnow(),
        )

    async def finalize_from_log(self, mission_id: str) -> bool:
        """If the log already holds a ruling + `done` (crash before the status flip), finish it."""
        events = await self.events_after(mission_id)
        if not any(e.type == ev.DONE for e in events):
            return False
        ruling = next((e.payload for e in reversed(events) if e.type == ev.JUDGE_NOTE and e.payload.get("resolved")), None)
        if ruling is None:
            return False
        await self._mark_complete(
            mission_id, rounds=ruling["round"], verdict=ruling["verdict"], summary=ruling["verdictSummary"],
            recommended=date.fromisoformat(ruling["recommendedDate"]), shift_days=ruling["shiftDays"],
            confidence=ruling["confidence"], resolution=ruling["resolution"],
        )
        return True

    async def fail(self, mission_id: str, message: str) -> None:
        await self.append_event(mission_id, ev.ERROR, {"message": message})
        await self._set(mission_id, status=MissionStatus.FAILED, error=message)

    async def reset_for_retry(self, mission_id: str) -> None:
        await self._set(mission_id, status=MissionStatus.PENDING, error=None)
