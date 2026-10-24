"""Application factory and lifespan wiring."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router
from app.config import Settings, get_settings
from app.db import Database
from app.domain.grounding import SolarCycleGrounding
from app.llm.groq_client import GroqClient
from app.logging_config import configure_logging
from app.services.engine import DebateEngine
from app.services.notifier import Notifier
from app.services.ratelimit import SlidingWindowLimiter
from app.services.repository import Repository
from app.services.runner import DebateRunner

logger = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    db: Database
    repo: Repository
    notifier: Notifier
    limiter: SlidingWindowLimiter
    llm: GroqClient
    grounding: SolarCycleGrounding | None
    runner: DebateRunner


def create_app(
    settings: Settings | None = None,
    *,
    llm_transport: httpx.AsyncBaseTransport | None = None,
    grounding_client: httpx.AsyncClient | None = None,
    mongo_client: Any | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN202
        db = Database(settings.mongodb_uri, settings.mongodb_db, client=mongo_client)
        await db.ensure_indexes()
        repo = Repository(db)
        notifier = Notifier()
        llm = GroqClient(settings, transport=llm_transport)  # fails fast without GROQ_API_KEY
        grounding = (
            SolarCycleGrounding(
                settings.noaa_solar_cycle_url, settings.grounding_timeout_seconds,
                settings.grounding_cache_ttl_seconds, client=grounding_client,
            )
            if settings.grounding_enabled
            else None
        )
        engine = DebateEngine(repo, llm, grounding, notifier, settings)
        runner = DebateRunner(engine, repo, notifier, settings)
        limiter = SlidingWindowLimiter(settings.rate_limit_missions_per_hour, 3600)
        app.state.container = Container(settings, db, repo, notifier, limiter, llm, grounding, runner)
        await runner.recover()
        logger.info("ÉTOCELEST %s started (agent=%s judge=%s)", __version__, settings.groq_model_agent, settings.groq_model_judge)
        try:
            yield
        finally:
            await runner.shutdown()
            await llm.aclose()
            if grounding:
                await grounding.aclose()
            await db.close()

    app = FastAPI(title="ÉTOCELEST API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Client-Id", "Last-Event-ID"],
    )
    app.include_router(router)
    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn app.main:app_factory --factory`."""
    return create_app()
