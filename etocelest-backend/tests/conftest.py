"""Shared test helpers: a scriptable fake Groq server (httpx MockTransport) and app factory."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from contextlib import asynccontextmanager

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.config import Settings
from app.main import create_app

CLIENT = "11111111-2222-3333-4444-555555555555"
OTHER = "99999999-8888-7777-6666-555555555555"
NAMES = {"Astro-Weather": "astro", "Logistics": "logistics", "Crew Readiness": "crew", "Mission Value": "missionvalue"}


def completion(obj: dict | str, finish: str = "stop") -> httpx.Response:
    content = obj if isinstance(obj, str) else json.dumps(obj)
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        },
    )


def agent_obj(name: str, rnd: int, proposed=5, lo=3, hi=7, hard=False) -> dict:
    return {
        "message": f"{name} round {rnd}: I argue for a shift of {proposed} days based on my domain's evidence.",
        "proposed_shift_days": proposed,
        "acceptable_min_days": lo,
        "acceptable_max_days": hi,
        "hard_constraint": hard,
    }


def rule_obj(shift=5, conf=90) -> dict:
    return {
        "decision": "rule", "note": "The specialists converged on a bounded shift; ruling.",
        "open_issues": [], "shift_days": shift, "confidence": conf,
        "summary": "A bounded shift clears the binding radiation constraint while staying inside the other domains' tolerances.",
    }


def reopen_obj() -> dict:
    return {
        "decision": "reopen", "note": "Astro-Weather and Logistics have not agreed a bounded window yet.",
        "open_issues": [{"agent": "astro", "question": "Can you commit to an exact window?"}],
        "shift_days": 0, "confidence": 0, "summary": "",
    }


class FakeGroq:
    """Routes requests to `agent(name, rnd, req)` / `judge(rnd, req)` callables."""

    def __init__(self, agent: Callable | None = None, judge: Callable | None = None) -> None:
        self.agent = agent or (lambda name, rnd, req: completion(agent_obj(name, rnd)))
        self.judge = judge or (lambda rnd, req: completion(rule_obj()))
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if system.startswith("You are the Judge"):
            rnd = int(re.search(r"(\d+)", user.split("Give your decision for round")[-1]).group(1))
            return self.judge(rnd, body)
        name = re.match(r"You are ([^,]+),", system).group(1)
        rnd = int(re.search(r"It is round (\d+)", user).group(1))
        return self.agent(name, rnd, body)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(
        groq_api_key="test-key",
        grounding_enabled=False, llm_max_retries=1, llm_max_backoff_seconds=0.05,
        llm_validation_attempts=2, environment="test", log_level="WARNING",
    )
    base.update(kw)
    return Settings(**base)


@asynccontextmanager
async def running_app(tmp_path, fake: FakeGroq, grounding_client=None, mongo=None, **settings_kw):
    app = create_app(
        make_settings(tmp_path, **settings_kw), llm_transport=fake.transport(),
        grounding_client=grounding_client, mongo_client=mongo or AsyncMongoMockClient(),
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers={"X-Client-Id": CLIENT}) as http:
            yield app, http


async def wait_done(http: httpx.AsyncClient, mission_id: str, timeout: float = 20.0) -> dict:
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        m = (await http.get(f"/api/missions/{mission_id}")).json()
        if m["status"] in ("complete", "failed"):
            return m
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(f"mission did not finish: {m['status']}")
        await asyncio.sleep(0.05)


def future_date(days: int = 400) -> str:
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


@pytest.fixture
def payload() -> dict:
    return {"name": "Ares-9 Lunar Gateway Resupply", "launchDate": future_date(), "context": "Crewed, 4 crew."}
