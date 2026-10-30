"""LangGraph orchestration of a debate: agents -> Judge -> (reopen | rule).

Topology::

    START -> ground --(resume guard)--> agents -> judge --(route)--> agents      (objections remain)
                  \\                                         \\--> finalize -> END (Judge ruled)
                   \\--> fallback -> finalize -> END          \\--> fallback -> finalize (cap, no ruling)

The graph is *pure orchestration*. It owns the control flow and the shape of the state; the work
done inside each node (LLM calls, event log writes, persistence) is injected through
`DebateNodes`, which `DebateEngine` implements. That keeps this module free of I/O, lets the
routing be unit-tested without an LLM or a database, and means one compiled graph is shared by
every concurrent debate: all per-run data travels in `RunContext`, never in module globals.

Durability is deliberately *not* delegated to a LangGraph checkpointer. The persisted event log
is the single source of truth (it also feeds the SSE replay in the UI), so a resumed run seeds the
initial state from that log via `initial_state()`.
"""

from __future__ import annotations

import logging
import operator
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from app.domain.positions import Position
from app.domain.prompts import TurnRecord
from app.llm.schemas import JudgeTurn
from app.models import Mission

logger = logging.getLogger(__name__)

# Node names (also the labels in the rendered graph).
GROUND = "ground"
AGENTS = "agents"
JUDGE = "judge"
FALLBACK = "fallback"
FINALIZE = "finalize"

# Nodes that run at most once per debate regardless of how many rounds are played:
# ground, fallback (only on the cap path) and finalize.
_FIXED_STEPS = 3
# Each round is two graph steps: the agents' turns, then the Judge's.
_STEPS_PER_ROUND = 2
# LangGraph's `recursion_limit` is exclusive: a run of N steps needs a limit of at least N + 1.
_LIMIT_IS_EXCLUSIVE = 1


@dataclass(frozen=True)
class Ruling:
    """How the debate ends. Produced by the judge/fallback nodes, consumed by `finalize`."""

    judge: JudgeTurn | None  # None => mechanical ruling from the agents' last positions
    forced_resolution: str | None  # e.g. "fallback"; only meaningful when `judge` is None
    note: str
    summary: str | None


@dataclass(frozen=True)
class RunContext:
    """Immutable per-run data. Passed via LangGraph's `context=`, so concurrent runs never mix."""

    mission: Mission
    brief: str


class DebateGraphState(TypedDict, total=False):
    max_rounds: int
    last_round: int  # last round the Judge has *completed* (0 = none); the resume cursor
    current_round: int  # round currently / most recently played by the agents
    turns: Annotated[list[TurnRecord], operator.add]  # nodes return only the *new* turns
    judge_notes: dict[int, str]
    open_issues: list[dict[str, str]]
    last_positions: list[Position]
    grounding: dict[str, Any] | None
    ruling: Ruling | None


NodeFn = Callable[[DebateGraphState, RunContext], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class DebateNodes:
    """The work done at each node. Each returns a partial state update (never mutates `state`)."""

    ground: NodeFn
    agents: NodeFn
    judge: NodeFn
    fallback: NodeFn
    finalize: NodeFn


# ------------------------------------------------------------------ routing (pure functions)
def route_after_ground(state: DebateGraphState) -> Literal["agents", "fallback"]:
    """Resume guard: a log that already holds every round but no ruling can only be concluded."""
    if state["last_round"] >= state["max_rounds"]:
        return FALLBACK
    return AGENTS


def route_after_judge(state: DebateGraphState) -> Literal["agents", "finalize", "fallback"]:
    """Rule, send the agents back, or (defensively) conclude. The loop is provably bounded."""
    if state.get("ruling") is not None:
        return FINALIZE
    if state["last_round"] >= state["max_rounds"]:
        return FALLBACK
    return AGENTS


def recursion_limit(max_rounds: int, headroom: int) -> int:
    """LangGraph step budget for one run: the worst-case path plus configurable headroom."""
    return _STEPS_PER_ROUND * max_rounds + _FIXED_STEPS + _LIMIT_IS_EXCLUSIVE + max(0, headroom)


def initial_state(
    *,
    max_rounds: int,
    last_round: int,
    turns: list[TurnRecord],
    judge_notes: dict[int, str],
    open_issues: list[dict[str, str]],
    last_positions: list[Position],
    grounding: dict[str, Any] | None,
) -> DebateGraphState:
    """State for a fresh run (all empty) or one rebuilt from the persisted event log."""
    return DebateGraphState(
        max_rounds=max_rounds,
        last_round=last_round,
        current_round=last_round,
        turns=list(turns),
        judge_notes=dict(judge_notes),
        open_issues=list(open_issues),
        last_positions=list(last_positions),
        grounding=grounding,
        ruling=None,
    )


# ------------------------------------------------------------------ graph construction
def _instrument(name: str, fn: NodeFn) -> Callable[[DebateGraphState, Runtime[RunContext]], Awaitable[dict[str, Any]]]:
    """Adapt a `NodeFn` to LangGraph's (state, runtime) signature and log how long it took."""

    async def node(state: DebateGraphState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        ctx = runtime.context
        started = time.perf_counter()
        update = await fn(state, ctx)
        logger.info(
            "debate node done mission=%s node=%s round=%s elapsed=%.2fs",
            ctx.mission.id, name, update.get("current_round", state.get("current_round")),
            time.perf_counter() - started,
        )
        return update

    node.__name__ = name
    return node


def build_debate_graph(nodes: DebateNodes) -> CompiledStateGraph:
    """Compile the debate graph. Compile once and reuse it: it holds no per-run state."""
    g = StateGraph(DebateGraphState, context_schema=RunContext)
    g.add_node(GROUND, _instrument(GROUND, nodes.ground))
    g.add_node(AGENTS, _instrument(AGENTS, nodes.agents))
    g.add_node(JUDGE, _instrument(JUDGE, nodes.judge))
    g.add_node(FALLBACK, _instrument(FALLBACK, nodes.fallback))
    g.add_node(FINALIZE, _instrument(FINALIZE, nodes.finalize))

    g.add_edge(START, GROUND)
    g.add_conditional_edges(GROUND, route_after_ground, {AGENTS: AGENTS, FALLBACK: FALLBACK})
    g.add_edge(AGENTS, JUDGE)
    g.add_conditional_edges(JUDGE, route_after_judge, {AGENTS: AGENTS, FINALIZE: FINALIZE, FALLBACK: FALLBACK})
    g.add_edge(FALLBACK, FINALIZE)
    g.add_edge(FINALIZE, END)
    return g.compile(name="etocelest-debate")
