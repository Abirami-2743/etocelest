"""MongoDB connection management (PyMongo's native async client)."""

from __future__ import annotations

import logging
from typing import Any

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient

logger = logging.getLogger(__name__)


class Database:
    """Owns the client and exposes the two collections.

    A pre-built client can be injected (tests); an injected client is not closed by us.
    """

    def __init__(self, uri: str, db_name: str, client: Any | None = None) -> None:
        self._owns_client = client is None
        self.client = client or AsyncMongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name]
        self.missions = self.db["missions"]
        self.events = self.db["mission_events"]

    async def ensure_indexes(self) -> None:
        await self.missions.create_index([("owner_id", ASCENDING), ("created_at", DESCENDING)])
        await self.missions.create_index([("status", ASCENDING)])
        await self.events.create_index([("mission_id", ASCENDING), ("seq", ASCENDING)], unique=True)

    async def ping(self) -> bool:
        try:
            await self.client.admin.command("ping")
            return True
        except Exception:  # noqa: BLE001 - health probe must never raise
            logger.exception("mongodb ping failed")
            return False

    async def close(self) -> None:
        if self._owns_client:
            await self.client.close()
