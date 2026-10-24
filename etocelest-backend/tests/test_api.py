"""HTTP contract: validation, ownership, streaming, deletion, limits."""

from __future__ import annotations

import json

import httpx

from tests.conftest import CLIENT, OTHER, FakeGroq, future_date, running_app, wait_done


def parse_sse(text: str) -> list[dict]:
    out = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


async def test_health_agents_presets(tmp_path):
    async with running_app(tmp_path, FakeGroq()) as (_, http):
        h = (await http.get("/api/health")).json()
        assert h["status"] == "ok" and h["database"] == "ok"
        assert [a["id"] for a in (await http.get("/api/agents")).json()] == ["astro", "logistics", "crew", "missionvalue"]
        presets = (await http.get("/api/presets")).json()
        assert len(presets) == 3 and all(p["launchDate"] > future_date(0) for p in presets)


async def test_client_id_required_and_validation(tmp_path, payload):
    async with running_app(tmp_path, FakeGroq()) as (_, http):
        r = await http.get("/api/missions", headers={"X-Client-Id": ""})
        assert r.status_code == 400
        assert (await http.post("/api/missions", json={**payload, "name": "x"})).status_code == 422
        assert (await http.post("/api/missions", json={**payload, "launchDate": "2001-01-01"})).status_code == 422
        assert (await http.post("/api/missions", json={**payload, "launchDate": "nope"})).status_code == 422
        assert (await http.post("/api/missions", json={**payload, "context": "x" * 2001})).status_code == 422


async def test_ownership_isolation_and_delete(tmp_path, payload):
    async with running_app(tmp_path, FakeGroq(), max_rounds=2) as (_, http):
        mid = (await http.post("/api/missions", json=payload)).json()["missionId"]
        await wait_done(http, mid)
        other = {"X-Client-Id": OTHER}
        assert (await http.get(f"/api/missions/{mid}", headers=other)).status_code == 404
        assert (await http.get("/api/missions", headers=other)).json() == []
        assert (await http.delete(f"/api/missions/{mid}", headers=other)).status_code == 404
        listing = (await http.get("/api/missions")).json()
        assert [m["id"] for m in listing] == [mid] and "rounds" not in listing[0]
        assert (await http.delete(f"/api/missions/{mid}")).status_code == 204
        assert (await http.get(f"/api/missions/{mid}")).status_code == 404


async def test_stream_replays_and_supports_resume_cursor(tmp_path, payload):
    async with running_app(tmp_path, FakeGroq(), max_rounds=2) as (_, http):
        mid = (await http.post("/api/missions", json=payload)).json()["missionId"]
        await wait_done(http, mid)
        full = await http.get(f"/api/missions/{mid}/stream")
        assert full.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(full.text)
        types = [e["type"] for e in events]
        assert types[-1] == "done" and "judge_note" in types and types.count("round_start") == 2
        # Resume from a cursor: only later events are delivered.
        ids = [int(line[4:]) for line in full.text.splitlines() if line.startswith("id: ")]
        tail = await http.get(f"/api/missions/{mid}/stream", headers={"Last-Event-ID": str(ids[-3])})
        assert [e["type"] for e in parse_sse(tail.text)] == types[-2:]


async def test_stream_follows_live_debate_until_done(tmp_path, payload):
    async with running_app(tmp_path, FakeGroq(), max_rounds=2) as (_, http):
        mid = (await http.post("/api/missions", json=payload)).json()["missionId"]
        async with http.stream("GET", f"/api/missions/{mid}/stream") as resp:
            body = "".join([chunk async for chunk in resp.aiter_text()])
    types = [e["type"] for e in parse_sse(body)]
    assert types[0] == "status" and types[-1] == "done"


async def test_retry_rejected_unless_failed(tmp_path, payload):
    async with running_app(tmp_path, FakeGroq(), max_rounds=2) as (_, http):
        mid = (await http.post("/api/missions", json=payload)).json()["missionId"]
        await wait_done(http, mid)
        assert (await http.post(f"/api/missions/{mid}/retry")).status_code == 409


async def test_rate_limit_and_active_cap(tmp_path, payload):
    async with running_app(tmp_path, FakeGroq(), rate_limit_missions_per_hour=2, max_active_missions_per_owner=5) as (_, http):
        codes = [(await http.post("/api/missions", json=payload)).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


async def test_active_cap_per_owner(tmp_path, payload):
    import asyncio

    slow = FakeGroq(agent=lambda n, r, q: (_ for _ in ()).throw(RuntimeError("never")))  # not reached
    async with running_app(tmp_path, FakeGroq(), max_active_missions_per_owner=1, max_concurrent_debates=1) as (app, http):
        # Hold the only slot so the first mission stays active.
        await app.state.container.runner._slots.acquire()
        assert (await http.post("/api/missions", json=payload)).status_code == 201
        assert (await http.post("/api/missions", json=payload)).status_code == 429
        app.state.container.runner._slots.release()
        await asyncio.sleep(0)
    assert slow  # silence linters


async def test_unfinished_missions_resume_after_restart(tmp_path, payload):
    """Simulate a crash mid-round-1: partial events exist, status=running; restart must finish it."""
    from mongomock_motor import AsyncMongoMockClient

    from app.main import create_app
    from tests.conftest import make_settings

    settings = make_settings(tmp_path, max_rounds=2)
    fake = FakeGroq()
    mongo = AsyncMongoMockClient()  # shared: simulates the same database across restarts
    # First boot: block the debate by holding the slot, then stop the app (simulated crash).
    app = create_app(settings, llm_transport=fake.transport(), mongo_client=mongo)
    async with app.router.lifespan_context(app):
        c = app.state.container
        await c.runner._slots.acquire()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers={"X-Client-Id": CLIENT}) as http:
            mid = (await http.post("/api/missions", json=payload)).json()["missionId"]
        # Partial progress left behind by the "crashed" run:
        await c.repo.set_status(mid, "running")
        await c.repo.append_event(mid, "round_start", {"round": 1})
        await c.repo.append_event(mid, "turn_start", {"round": 1, "agent": "astro"})
    # Second boot on the same database.
    app2 = create_app(settings, llm_transport=fake.transport(), mongo_client=mongo)
    async with app2.router.lifespan_context(app2):
        transport = httpx.ASGITransport(app=app2)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers={"X-Client-Id": CLIENT}) as http:
            m = await wait_done(http, mid)
    assert m["status"] == "complete" and [r["round"] for r in m["rounds"]] == [1, 2]


async def test_crash_between_done_event_and_status_flip_is_repaired(tmp_path, payload):
    """Events are written before the status flip; if we die in between, recovery finishes the job
    without running another debate."""
    from mongomock_motor import AsyncMongoMockClient

    from app.main import create_app
    from tests.conftest import make_settings

    settings = make_settings(tmp_path)
    fake = FakeGroq()
    mongo = AsyncMongoMockClient()
    app = create_app(settings, llm_transport=fake.transport(), mongo_client=mongo)
    async with app.router.lifespan_context(app):
        c = app.state.container
        await c.runner._slots.acquire()  # keep the real debate from starting
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers={"X-Client-Id": CLIENT}) as http:
            mid = (await http.post("/api/missions", json=payload)).json()["missionId"]
        await c.repo.append_event(mid, "round_start", {"round": 2})
        await c.repo.append_event(mid, "judge_note", {
            "round": 2, "resolved": True, "note": "ruling", "openIssues": [], "verdict": "Proceed on original date",
            "verdictSummary": "No binding conflict.", "recommendedDate": payload["launchDate"],
            "confidence": 80, "shiftDays": 0, "resolution": "consensus"})
        await c.repo.append_event(mid, "done", {})
    app2 = create_app(settings, llm_transport=fake.transport(), mongo_client=mongo)
    async with app2.router.lifespan_context(app2):
        transport = httpx.ASGITransport(app=app2)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers={"X-Client-Id": CLIENT}) as http:
            m = await wait_done(http, mid)
    assert m["status"] == "complete" and m["verdict"] == "Proceed on original date" and m["confidence"] == 80
    assert fake.requests == []  # no LLM call: nothing was re-run
