"""Engine behaviour end to end through the HTTP API with a fake Groq."""

from __future__ import annotations

import httpx

from tests.conftest import (
    FakeGroq,
    agent_obj,
    completion,
    reopen_obj,
    rule_obj,
    running_app,
    wait_done,
)


async def start(http, payload) -> str:
    r = await http.post("/api/missions", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["missionId"]


async def test_consensus_after_min_rounds_and_agents_see_each_other(tmp_path, payload):
    fake = FakeGroq(judge=lambda rnd, req: completion(reopen_obj() if rnd == 1 else rule_obj(5, 92)))
    async with running_app(tmp_path, fake) as (_, http):
        m = await wait_done(http, await start(http, payload))
    assert m["status"] == "complete"
    assert [r["round"] for r in m["rounds"]] == [1, 2]
    assert all(len(r["turns"]) == 4 for r in m["rounds"])
    assert m["rounds"][0]["judge"]["resolved"] is False
    assert m["rounds"][1]["judge"]["resolved"] is True
    assert m["resolution"] == "consensus" and m["shiftDays"] == 5 and m["confidence"] == 92
    assert m["verdict"].startswith("Shift launch to") and "(+5 days)" in m["verdict"]
    assert m["usage"]["promptTokens"] > 0

    # Communication: the 2nd speaker of round 1 sees the 1st speaker's message...
    agent_calls = [r for r in fake.requests if not r["messages"][0]["content"].startswith("You are the Judge")]
    second = agent_calls[1]["messages"][1]["content"]
    first_name = m["rounds"][0]["turns"][0]["agent"]
    assert m["rounds"][0]["turns"][0]["text"] in second
    # ...and round 2 includes the Judge's open question directed at astro.
    astro_r2 = next(r for r in agent_calls if "It is round 2. Speak now as Astro-Weather" in r["messages"][1]["content"])
    assert "Can you commit to an exact window?" in astro_r2["messages"][1]["content"]
    assert first_name in {"astro", "logistics", "crew", "missionvalue"}


async def test_judge_cannot_rule_before_min_rounds(tmp_path, payload):
    # A judge that tries to rule in round 1 gets rejected by validation, then must reopen.
    calls = {"n": 0}

    def judge(rnd, req):
        calls["n"] += 1
        if rnd == 1 and calls["n"] == 1:
            return completion(rule_obj())
        return completion(reopen_obj() if rnd == 1 else rule_obj())

    async with running_app(tmp_path, FakeGroq(judge=judge)) as (_, http):
        m = await wait_done(http, await start(http, payload))
    assert m["rounds"][0]["judge"]["resolved"] is False
    assert m["status"] == "complete"


async def test_judge_is_forced_to_rule_at_round_cap_without_consensus(tmp_path, payload):
    def agent(name, rnd, req):  # disjoint acceptable ranges: no consensus ever
        spans = {"Astro-Weather": (10, 10, 12), "Logistics": (0, 0, 2), "Crew Readiness": (1, 0, 3), "Mission Value": (2, 0, 4)}
        p, lo, hi = spans[name]
        return completion(agent_obj(name, rnd, p, lo, hi, hard=name == "Astro-Weather"))

    def judge(rnd, req):
        schema = req["response_format"]["json_schema"]["schema"]["properties"]["decision"]["enum"]
        if schema == ["rule"]:  # final round: only 'rule' allowed
            return completion(rule_obj(4, 99))
        return completion(reopen_obj())

    async with running_app(tmp_path, FakeGroq(agent, judge), max_rounds=4) as (_, http):
        m = await wait_done(http, await start(http, payload))
    assert m["status"] == "complete"
    assert len(m["rounds"]) == 4
    assert m["rounds"][-1]["judge"]["resolved"] is True
    assert m["resolution"] == "forced_ruling"
    assert m["confidence"] <= 75  # capped: no consensus


async def test_fallback_ruling_when_judge_model_fails_at_cap(tmp_path, payload):
    def judge(rnd, req):
        return httpx.Response(500, json={"error": {"message": "boom"}}) if rnd >= 2 else completion(reopen_obj())

    async with running_app(tmp_path, FakeGroq(judge=judge), max_rounds=2) as (_, http):
        m = await wait_done(http, await start(http, payload))
    assert m["status"] == "complete"          # the judge ALWAYS concludes
    assert m["resolution"] == "fallback" and m["confidence"] <= 40
    assert m["shiftDays"] == 5                 # median of agents' proposals (all 5)
    assert "Mechanical ruling" in m["verdictSummary"]


async def test_judge_failure_before_cap_continues_debate(tmp_path, payload):
    def judge(rnd, req):
        return httpx.Response(503, json={}) if rnd == 2 else completion(reopen_obj() if rnd == 1 else rule_obj())

    async with running_app(tmp_path, FakeGroq(judge=judge), max_rounds=3) as (_, http):
        m = await wait_done(http, await start(http, payload))
    assert m["status"] == "complete" and len(m["rounds"]) == 3
    assert "could not be reached" in m["rounds"][1]["judge"]["note"]


async def test_one_agent_down_does_not_stop_the_debate(tmp_path, payload):
    def agent(name, rnd, req):
        return httpx.Response(500, json={}) if name == "Logistics" else completion(agent_obj(name, rnd))

    async with running_app(tmp_path, FakeGroq(agent=agent), max_rounds=2) as (_, http):
        m = await wait_done(http, await start(http, payload))
    assert m["status"] == "complete"
    failed = [t for r in m["rounds"] for t in r["turns"] if t["failed"]]
    assert len(failed) == 2 and all(t["agent"] == "logistics" for t in failed)


async def test_all_agents_down_fails_mission_then_retry_succeeds(tmp_path, payload):
    state = {"down": True}

    def agent(name, rnd, req):
        return httpx.Response(500, json={}) if state["down"] else completion(agent_obj(name, rnd))

    async with running_app(tmp_path, FakeGroq(agent=agent), max_rounds=2) as (_, http):
        mid = await start(http, payload)
        m = await wait_done(http, mid)
        assert m["status"] == "failed" and "None of the agents" in m["error"]
        state["down"] = False
        assert (await http.post(f"/api/missions/{mid}/retry")).status_code == 202
        m = await wait_done(http, mid)
        assert m["status"] == "complete" and m["error"] is None


async def test_bad_api_key_fails_with_clear_message(tmp_path, payload):
    fake = FakeGroq(agent=lambda n, r, q: httpx.Response(401, json={"error": {"message": "invalid"}}))
    async with running_app(tmp_path, fake) as (_, http):
        m = await wait_done(http, await start(http, payload))
    assert m["status"] == "failed" and "API key" in m["error"]


async def test_rate_limit_is_retried_honouring_retry_after(tmp_path, payload):
    seen = {"n": 0}

    def agent(name, rnd, req):
        seen["n"] += 1
        if seen["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={})
        return completion(agent_obj(name, rnd))

    async with running_app(tmp_path, FakeGroq(agent=agent), max_rounds=2) as (_, http):
        mid = await start(http, payload)
        m = await wait_done(http, mid)
        events = (await http.get(f"/api/missions/{mid}/stream")).text
    assert m["status"] == "complete"
    assert "retrying in" in events  # visible to the user as a status event


async def test_invalid_model_output_is_repaired_by_reasking(tmp_path, payload):
    seen = {"bad": 0}

    def agent(name, rnd, req):
        if name == "Astro-Weather" and seen["bad"] == 0:
            seen["bad"] += 1
            return completion(agent_obj(name, rnd, proposed=99, lo=3, hi=7))  # violates bounds
        return completion(agent_obj(name, rnd))

    async with running_app(tmp_path, FakeGroq(agent=agent), max_rounds=2) as (_, http):
        m = await wait_done(http, await start(http, payload))
    assert m["status"] == "complete"
    astro = [t for t in m["rounds"][0]["turns"] if t["agent"] == "astro"][0]
    assert not astro["failed"] and astro["proposedShiftDays"] == 5


async def test_grounding_from_noaa_is_used_and_out_of_range_is_honest(tmp_path, payload):
    from datetime import date

    year = int(payload["launchDate"][:4])
    rec = lambda tag: {  # noqa: E731
        "time-tag": tag, "predicted_ssn": 50.0, "low_ssn": 40.0, "high_ssn": 60.0,
        "predicted_f10.7": 120.0, "low_f10.7": 110.0, "high_f10.7": 130.0,
    }
    tags = [f"{year}-{m:02d}" for m in range(1, 13)]
    noaa = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[rec(t) for t in tags])))
    fake = FakeGroq()
    async with running_app(tmp_path, fake, grounding_client=noaa, grounding_enabled=True, max_rounds=2) as (_, http):
        m = await wait_done(http, await start(http, payload))
        far = await wait_done(http, await start(http, {**payload, "launchDate": f"{year + 20}-06-15", "name": "Far future mission"}))
    assert m["grounding"]["available"] is True and m["grounding"]["launchMonth"].startswith(str(year))
    assert any("ssn 50.0" in r["messages"][1]["content"] for r in fake.requests)
    assert far["grounding"]["available"] is False and "outside that range" in far["grounding"]["reason"]
    assert date.today().year <= year + 20
