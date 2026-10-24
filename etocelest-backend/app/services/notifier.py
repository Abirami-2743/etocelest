"""Wake-up broadcast so SSE streams react immediately to new events (single process)."""

from __future__ import annotations

import asyncio


class Notifier:
    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}

    def waiter(self, mission_id: str) -> asyncio.Event:
        """Obtain BEFORE querying the DB so a notify in between is never lost."""
        return self._events.setdefault(mission_id, asyncio.Event())

    def notify(self, mission_id: str) -> None:
        ev = self._events.pop(mission_id, None)
        if ev:
            ev.set()
