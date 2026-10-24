"""Background execution of debates: one task per mission, bounded concurrency, crash recovery."""

from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.domain import events as ev
from app.services.engine import DebateEngine, EngineFailure
from app.services.notifier import Notifier
from app.services.repository import MissionGone, Repository

logger = logging.getLogger(__name__)


class DebateRunner:
    def __init__(self, engine: DebateEngine, repo: Repository, notifier: Notifier, settings: Settings) -> None:
        self._engine = engine
        self._repo = repo
        self._notifier = notifier
        self._s = settings
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._slots = asyncio.Semaphore(settings.max_concurrent_debates)

    @property
    def active_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())

    def start(self, mission_id: str) -> None:
        existing = self._tasks.get(mission_id)
        if existing and not existing.done():
            return
        task = asyncio.create_task(self._run(mission_id), name=f"debate-{mission_id}")
        self._tasks[mission_id] = task
        task.add_done_callback(lambda t, m=mission_id: self._tasks.pop(m, None) if self._tasks.get(m) is t else None)

    async def _run(self, mission_id: str) -> None:
        try:
            if self._slots.locked():
                await self._repo.append_event(mission_id, ev.STATUS, {"value": "Queued: waiting for a free reasoning slot..."})
                self._notifier.notify(mission_id)
            async with self._slots:
                async with asyncio.timeout(self._s.mission_timeout_seconds):
                    await self._engine.run(mission_id)
        except asyncio.CancelledError:
            raise  # shutdown (resumed on next boot) or delete
        except MissionGone:
            logger.info("mission %s was deleted while running", mission_id)
        except EngineFailure as exc:
            await self._fail(mission_id, str(exc))
        except TimeoutError:
            await self._fail(mission_id, "The review timed out. Please retry.")
        except Exception:  # noqa: BLE001
            logger.exception("debate crashed mission=%s", mission_id)
            await self._fail(mission_id, "Internal error while running the debate. Please retry.")

    async def _fail(self, mission_id: str, message: str) -> None:
        logger.error("mission %s failed: %s", mission_id, message)
        try:
            await self._repo.fail(mission_id, message)
        except Exception:  # noqa: BLE001 - e.g. mission deleted meanwhile
            logger.exception("could not record failure for mission %s", mission_id)
        self._notifier.notify(mission_id)

    async def cancel(self, mission_id: str) -> None:
        task = self._tasks.get(mission_id)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def recover(self) -> int:
        ids = await self._repo.active_ids()
        for mid in ids:
            self.start(mid)
        if ids:
            logger.info("resuming %d unfinished mission(s)", len(ids))
        return len(ids)

    async def shutdown(self) -> None:
        tasks = [t for t in self._tasks.values() if not t.done()]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
