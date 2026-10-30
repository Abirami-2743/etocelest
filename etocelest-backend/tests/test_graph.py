"""The LangGraph debate graph in isolation: topology, routing, loop bounds and run isolation.

These tests use fake node implementations, so they need no LLM, database or HTTP stack. The
behaviour of the real nodes is covered end to end in test_debate.py / test_api.py.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pytest

from app.domain.positions import Position
from app.domain.prompts import TurnRecord
from app.models import Mission
from app.services import debate_graph as dg
from app.services.debate_graph import (
    DebateNodes,
    Ruling,
    RunContext,
    build_debate_graph,
    initial_state,
    recursion_limit,
    route_after_ground,
    route_after_judge,
)


def make_mission(mission_id: str = "m1", *, min_rounds: int = 2, max_rounds: int = 4) -> Mission:
    return Mission(
        id=mission_id, owner_id="o", name="Test", launch_date=date(2030, 1, 1), context="",
        min_rounds=min_rounds, max_rounds=max_rounds, max_shift_days=60,
        model_agent="m", model_judge="m",
    )


def seed(max_rounds: int = 4, last_round: int = 0, **kw: Any) -> dg.DebateGraphState:
    return initial_state(
        max_rounds=max_rounds, last_round=last_round, turns=kw.get("turns", []), judge_notes={},
        open_issues=[], last_positions=kw.get("last_positions", []), grounding=None,
    )


class Recorder:
    """Fake nodes that log the order they ran in; the judge rules once `rule_at` is reached."""

    def __init__(self, rule_at: int | None) -> None:
        self.calls: list[str] = []
        self.finalized: list[dict[str, Any]] = []
        self.rule_at = rule_at

    def nodes(self) -> DebateNodes:
        return DebateNodes(
            ground=self._ground, agents=self._agents, judge=self._judge,
            fallback=self._fallback, finalize=self._finalize,
        )

    async def _ground(self, state, ctx):
        self.calls.append("ground")
        return {"grounding": None}

    async def _agents(self, state, ctx):
        r = state["last_round"] + 1
        self.calls.append(f"agents:{r}")
        pos = Position("astro", 3, 0, 5, False)
        return {"current_round": r, "turns": [TurnRecord(r, "astro", "hi", position=pos)], "last_positions": [pos]}

    async def _judge(self, state, ctx):
        r = state["current_round"]
        self.calls.append(f"judge:{r}")
        if self.rule_at is not None and r >= self.rule_at:
            return {"last_round": r, "ruling": Ruling(None, None, "ruled", "s")}
        return {"last_round": r}  # reopen

    async def _fallback(self, state, ctx):
        self.calls.append("fallback")
        return {"current_round": ctx.mission.max_rounds, "ruling": Ruling(None, "fallback", "cap", None)}

    async def _finalize(self, state, ctx):
        self.calls.append("finalize")
        self.finalized.append(
            {"mission": ctx.mission.id, "turns": len(state["turns"]), "round": state["current_round"]}
        )
        return {}


def config(max_rounds: int, headroom: int = 0) -> dict[str, Any]:
    return {"recursion_limit": recursion_limit(max_rounds, headroom)}


# ------------------------------------------------------------------ topology
def test_topology_matches_documented_graph():
    graph = build_debate_graph(Recorder(rule_at=1).nodes())
    drawn = graph.get_graph()
    assert {dg.GROUND, dg.AGENTS, dg.JUDGE, dg.FALLBACK, dg.FINALIZE} <= set(drawn.nodes)
    edges = {(e.source, e.target) for e in drawn.edges}
    assert (dg.AGENTS, dg.JUDGE) in edges
    assert (dg.JUDGE, dg.AGENTS) in edges  # the reopen loop
    assert (dg.JUDGE, dg.FINALIZE) in edges
    assert (dg.FALLBACK, dg.FINALIZE) in edges
    assert (dg.FINALIZE, "__end__") in edges
    assert "agents" in drawn.draw_mermaid()


# ------------------------------------------------------------------ routing
@pytest.mark.parametrize(
    ("last_round", "max_rounds", "expected"),
    [(0, 4, dg.AGENTS), (3, 4, dg.AGENTS), (4, 4, dg.FALLBACK), (5, 4, dg.FALLBACK)],
)
def test_route_after_ground(last_round, max_rounds, expected):
    assert route_after_ground({"last_round": last_round, "max_rounds": max_rounds}) == expected


@pytest.mark.parametrize(
    ("ruling", "last_round", "max_rounds", "expected"),
    [
        (Ruling(None, None, "n", "s"), 1, 4, dg.FINALIZE),  # ruled early
        (Ruling(None, "fallback", "n", None), 4, 4, dg.FINALIZE),  # forced at the cap
        (None, 1, 4, dg.AGENTS),  # objections remain
        (None, 3, 4, dg.AGENTS),
        (None, 4, 4, dg.FALLBACK),  # defensive: never loops past the cap
    ],
)
def test_route_after_judge(ruling, last_round, max_rounds, expected):
    state = {"ruling": ruling, "last_round": last_round, "max_rounds": max_rounds}
    assert route_after_judge(state) == expected


# ------------------------------------------------------------------ execution
async def test_reopen_loop_then_rule_runs_nodes_in_order_and_accumulates_turns():
    rec = Recorder(rule_at=3)
    graph = build_debate_graph(rec.nodes())
    ctx = RunContext(make_mission(), "brief")
    await graph.ainvoke(seed(), config=config(4), context=ctx)
    assert rec.calls == [
        "ground", "agents:1", "judge:1", "agents:2", "judge:2", "agents:3", "judge:3", "finalize",
    ]
    assert rec.finalized == [{"mission": "m1", "turns": 3, "round": 3}]  # reducer appended each round


async def test_round_cap_without_ruling_ends_in_fallback_not_an_endless_loop():
    rec = Recorder(rule_at=None)  # the judge always reopens
    graph = build_debate_graph(rec.nodes())
    await graph.ainvoke(seed(max_rounds=3), config=config(3), context=RunContext(make_mission(max_rounds=3), "b"))
    assert rec.calls[-2:] == ["fallback", "finalize"]
    assert rec.calls.count("judge:3") == 1 and not any(c.startswith("agents:4") for c in rec.calls)


async def test_resume_with_all_rounds_logged_skips_agents_and_concludes():
    rec = Recorder(rule_at=None)
    graph = build_debate_graph(rec.nodes())
    state = seed(max_rounds=4, last_round=4)
    await graph.ainvoke(state, config=config(4), context=RunContext(make_mission(), "b"))
    assert rec.calls == ["ground", "fallback", "finalize"]


async def test_resume_midway_continues_from_the_next_round():
    rec = Recorder(rule_at=3)
    graph = build_debate_graph(rec.nodes())
    state = seed(last_round=2, turns=[TurnRecord(1, "astro", "x"), TurnRecord(2, "astro", "y")])
    await graph.ainvoke(state, config=config(4), context=RunContext(make_mission(), "b"))
    assert rec.calls == ["ground", "agents:3", "judge:3", "finalize"]
    assert rec.finalized[0]["turns"] == 3  # 2 restored from the log + 1 new


@pytest.mark.parametrize("max_rounds", range(1, 11))
async def test_step_budget_covers_the_worst_case_path_with_zero_headroom(max_rounds):
    """recursion_limit() must never be the thing that kills a legitimate debate."""
    rec = Recorder(rule_at=None)
    graph = build_debate_graph(rec.nodes())
    ctx = RunContext(make_mission(max_rounds=max_rounds), "b")
    await graph.ainvoke(seed(max_rounds=max_rounds), config=config(max_rounds, headroom=0), context=ctx)
    assert rec.calls[-1] == "finalize"


def test_recursion_limit_scales_with_rounds_and_clamps_negative_headroom():
    assert recursion_limit(4, 4) > recursion_limit(2, 4)
    assert recursion_limit(3, -10) == recursion_limit(3, 0)


async def test_node_exceptions_propagate_with_their_original_type():
    class Boom(Exception):
        pass

    rec = Recorder(rule_at=1)

    async def failing_agents(state, ctx):
        raise Boom("agents down")

    nodes = rec.nodes()
    graph = build_debate_graph(DebateNodes(nodes.ground, failing_agents, nodes.judge, nodes.fallback, nodes.finalize))
    with pytest.raises(Boom, match="agents down"):
        await graph.ainvoke(seed(), config=config(4), context=RunContext(make_mission(), "b"))


async def test_one_compiled_graph_isolates_concurrent_runs():
    """The engine shares a single compiled graph across debates; context must never leak."""
    rec = Recorder(rule_at=2)
    graph = build_debate_graph(rec.nodes())

    async def run(mid: str) -> None:
        await graph.ainvoke(seed(), config=config(4), context=RunContext(make_mission(mid), "b"))

    await asyncio.gather(*(run(f"m{i}") for i in range(8)))
    assert sorted(f["mission"] for f in rec.finalized) == [f"m{i}" for i in range(8)]
    assert all(f["turns"] == 2 and f["round"] == 2 for f in rec.finalized)
