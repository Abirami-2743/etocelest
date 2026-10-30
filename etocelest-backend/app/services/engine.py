"""The debate engine: four agents talk to each other round by round; the Judge always rules.

Control flow (rounds, the Judge's reopen/rule decision, the round cap) is a LangGraph state graph,
see `app.services.debate_graph`. This module supplies the work done at each node: agent and Judge
LLM calls, event-log writes, grounding and the final ruling.

Guarantee: `run()` either ends with a ruling (`done` event) or fails with an `error` event for
a non-recoverable reason (bad API key, no agent able to respond at all). Once the round cap is
reached the Judge is forced to rule; if even that call fails, a documented mechanical ruling
derived from the agents' final positions is issued and labelled `fallback`.

The run is resumable: all state is rebuilt from the persisted event log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.domain import events as ev
from app.domain.agents import AgentSpec, speaking_order
from app.domain.dates import shift, verdict_text
from app.domain.grounding import SolarCycleGrounding
from app.domain.positions import Position, mechanical_ruling, overlap
from app.domain.prompts import TurnRecord, agent_messages, brief, judge_messages
from app.llm.groq_client import GroqClient, LLMError, LLMFatalError, Usage
from app.llm.schemas import AgentTurn, JudgeTurn, agent_json_schema, judge_json_schema
from app.models import Mission, MissionStatus
from app.services.debate_graph import (
    DebateGraphState,
    DebateNodes,
    Ruling,
    RunContext,
    build_debate_graph,
    initial_state,
    recursion_limit,
)
from app.services.notifier import Notifier
from app.services.repository import Repository

logger = logging.getLogger(__name__)

# Upper bounds on reported confidence by how the ruling was reached.
CONFIDENCE_CAP = {"consensus": 100, "judge_decision": 85, "forced_ruling": 75, "fallback": 40}


class EngineFailure(Exception):
    """Unrecoverable problem for this mission (surfaced to the user)."""


@dataclass
class DebateState:
    turns: list[TurnRecord] = field(default_factory=list)
    judge_notes: dict[int, str] = field(default_factory=dict)
    open_issues: list[dict[str, str]] = field(default_factory=list)
    last_round: int = 0
    last_positions: list[Position] = field(default_factory=list)


def rebuild_state(events: list[tuple[str, dict[str, Any]]]) -> DebateState:
    st = DebateState()
    round_positions: dict[int, list[Position]] = {}
    for etype, p in events:
        if etype in (ev.TURN_TEXT, ev.TURN_FAILED):
            rec = TurnRecord(round=p["round"], agent=p["agent"], text=p["text"], failed=etype == ev.TURN_FAILED)
            if etype == ev.TURN_TEXT:
                rec.position = Position(
                    p["agent"], p["proposedShiftDays"], p["acceptableMinDays"], p["acceptableMaxDays"], p["hardConstraint"]
                )
                round_positions.setdefault(p["round"], []).append(rec.position)
            st.turns.append(rec)
        elif etype == ev.JUDGE_NOTE:
            st.last_round = p["round"]
            st.judge_notes[p["round"]] = p["note"]
            st.open_issues = list(p.get("openIssues", []))
            st.last_positions = round_positions.get(p["round"], [])
    return st


class DebateEngine:
    def __init__(
        self,
        repo: Repository,
        llm: GroqClient,
        grounding: SolarCycleGrounding | None,
        notifier: Notifier,
        settings: Settings,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._grounding = grounding
        self._notifier = notifier
        self._s = settings
        # Compiled once; holds no per-run state (that travels in `RunContext`), so it is safe to
        # share across concurrent debates.
        self._graph = build_debate_graph(
            DebateNodes(
                ground=self._node_ground,
                agents=self._node_agents,
                judge=self._node_judge,
                fallback=self._node_fallback,
                finalize=self._node_finalize,
            )
        )

    async def _emit(self, mission_id: str, etype: str, **payload: Any) -> None:
        await self._repo.append_event(mission_id, etype, payload)
        self._notifier.notify(mission_id)

    async def _usage(self, mission_id: str, usage: Usage) -> None:
        await self._repo.add_usage(mission_id, usage.prompt_tokens, usage.completion_tokens)

    # ---------------------------------------------------------------- run
    async def run(self, mission_id: str) -> None:
        mission = await self._repo.get(mission_id)
        if mission is None or mission.status == MissionStatus.COMPLETE:
            return
        if await self._repo.finalize_from_log(mission_id):
            self._notifier.notify(mission_id)  # crash happened between `done` and the status flip
            return
        await self._repo.truncate_incomplete_round(mission_id)
        await self._repo.set_status(mission_id, MissionStatus.RUNNING)
        self._notifier.notify(mission_id)

        stored = await self._repo.events_after(mission_id)
        state = rebuild_state([(e.type, e.payload) for e in stored])
        ctx = RunContext(
            mission=mission,
            brief=brief(mission.name, mission.launch_date, mission.context, mission.created_at.date()),
        )
        start = initial_state(
            max_rounds=mission.max_rounds,
            last_round=state.last_round,
            turns=state.turns,
            judge_notes=state.judge_notes,
            open_issues=state.open_issues,
            last_positions=state.last_positions,
            grounding=mission.grounding,
        )
        config = {"recursion_limit": recursion_limit(mission.max_rounds, self._s.graph_step_headroom)}
        # EngineFailure / LLMFatalError / cancellation propagate unchanged to `DebateRunner`.
        await self._graph.ainvoke(start, config=config, context=ctx)

    # ------------------------------------------------------------- nodes
    async def _node_ground(self, state: DebateGraphState, ctx: RunContext) -> dict[str, Any]:
        grounding = await self._ensure_grounding(ctx.mission)
        if state["last_round"] == 0:
            await self._emit(ctx.mission.id, ev.STATUS, value="Four agents loaded. Judge standing by.")
        return {"grounding": grounding}

    async def _node_agents(self, state: DebateGraphState, ctx: RunContext) -> dict[str, Any]:
        """Play one round: every agent speaks once, each seeing the turns before it."""
        mission = ctx.mission
        r = state["last_round"] + 1
        await self._emit(mission.id, ev.ROUND_START, round=r)

        visible = list(state["turns"])  # grows as agents speak, so later speakers see earlier ones
        new_turns: list[TurnRecord] = []
        positions: list[Position] = []
        for spec in speaking_order(r):
            await self._emit(mission.id, ev.TURN_START, round=r, agent=spec.id)
            rec = await self._agent_turn(
                mission, spec, r, visible, state["judge_notes"], state["open_issues"],
                ctx.brief, state["grounding"],
            )
            visible.append(rec)
            new_turns.append(rec)
            if rec.position:
                positions.append(rec.position)

        if not positions:
            raise EngineFailure("None of the agents could respond. Please try again in a moment.")
        return {"current_round": r, "turns": new_turns, "last_positions": positions}

    async def _node_judge(self, state: DebateGraphState, ctx: RunContext) -> dict[str, Any]:
        """The Judge either rules (-> finalize) or reopens with specific questions (-> agents)."""
        mission = ctx.mission
        r = state["current_round"]
        may_rule = r >= mission.min_rounds
        must_rule = r >= mission.max_rounds
        await self._emit(mission.id, ev.JUDGE_EVALUATING, round=r)
        judge = await self._judge_turn(
            mission, r, state["turns"], state["judge_notes"], state["last_positions"],
            ctx.brief, state["grounding"], may_rule, must_rule,
        )

        if judge is not None and judge.decision == "rule":
            return {
                "last_round": r,
                "ruling": Ruling(judge=judge, forced_resolution=None, note=judge.note.strip(),
                                 summary=judge.summary.strip()),
            }
        if must_rule:
            return {
                "last_round": r,
                "ruling": Ruling(
                    judge=None, forced_resolution="fallback",
                    note="The Judge model could not produce a ruling, so the Judge's fallback rule was applied.",
                    summary=None,
                ),
            }

        if judge is None:
            note = "The Judge could not be reached this round; the debate continues."
            issues: list[dict[str, str]] = []
        else:
            note = judge.note.strip()
            issues = [i.model_dump() for i in judge.open_issues]
        await self._emit(mission.id, ev.JUDGE_NOTE, round=r, resolved=False, note=note, openIssues=issues)
        return {"last_round": r, "judge_notes": {**state["judge_notes"], r: note}, "open_issues": issues}

    async def _node_fallback(self, state: DebateGraphState, ctx: RunContext) -> dict[str, Any]:
        """Defensive: reached the round cap with no recorded ruling (e.g. a resumed, odd log)."""
        mission = ctx.mission
        logger.warning("mission %s reached the round cap without a ruling; issuing fallback", mission.id)
        return {
            "current_round": mission.max_rounds,
            "ruling": Ruling(
                judge=None, forced_resolution="fallback",
                note="The round limit was reached without a recorded ruling; the Judge's fallback rule applies.",
                summary=None,
            ),
        }

    async def _node_finalize(self, state: DebateGraphState, ctx: RunContext) -> dict[str, Any]:
        ruling = state["ruling"]
        assert ruling is not None  # the router only reaches `finalize` with a ruling set
        await self._finalize(
            ctx.mission, state["current_round"], ruling.judge, state["last_positions"],
            ruling.forced_resolution, note=ruling.note, summary=ruling.summary,
        )
        return {}

    # ---------------------------------------------------------- grounding
    async def _ensure_grounding(self, mission: Mission) -> dict[str, Any] | None:
        if mission.grounding is not None:
            return mission.grounding
        if not (self._s.grounding_enabled and self._grounding):
            return None
        await self._emit(mission.id, ev.STATUS, value="Fetching NOAA solar-cycle forecast for the launch window...")
        g = await self._grounding.for_launch(mission.launch_date)
        await self._repo.save_grounding(mission.id, g)
        if g.get("available"):
            await self._emit(mission.id, ev.STATUS, value=f"Loaded NOAA solar-cycle forecast for {g['launchMonth']}.")
        else:
            await self._emit(mission.id, ev.STATUS, value=f"No solar-cycle data for this window: {g['reason']}.")
        return g

    # -------------------------------------------------------------- turns
    async def _agent_turn(
        self, mission: Mission, spec: AgentSpec, r: int, turns: list[TurnRecord],
        judge_notes: dict[int, str], open_issues: list[dict[str, str]], mission_brief: str,
        grounding: dict[str, Any] | None,
    ) -> TurnRecord:
        mid = mission.id
        messages = agent_messages(
            spec, mission_brief=mission_brief, grounding=grounding, turns=turns,
            judge_notes=judge_notes, open_issues=open_issues, round_number=r,
            max_shift=mission.max_shift_days,
        )
        try:
            turn, usage = await self._llm.structured(
                model=mission.model_agent, messages=messages, output=AgentTurn,
                schema_name="agent_turn", schema=agent_json_schema(), temperature=0.6,
                max_tokens=self._s.llm_agent_max_tokens,
                validate=lambda t: t.check_bounds(mission.max_shift_days),
                on_retry=lambda msg: self._emit(mid, ev.STATUS, value=msg),
            )
        except LLMFatalError as exc:
            raise EngineFailure(str(exc)) from exc
        except LLMError as exc:
            logger.error("agent turn failed mission=%s agent=%s round=%d: %s", mid, spec.id, r, exc)
            text = f"{spec.name} could not respond this round."
            await self._emit(mid, ev.TURN_FAILED, round=r, agent=spec.id, text=text)
            return TurnRecord(round=r, agent=spec.id, text=text, failed=True)

        await self._usage(mid, usage)
        pos = Position(spec.id, turn.proposed_shift_days, turn.acceptable_min_days, turn.acceptable_max_days, turn.hard_constraint)
        await self._emit(
            mid, ev.TURN_TEXT, round=r, agent=spec.id, text=turn.message,
            proposedShiftDays=pos.proposed, acceptableMinDays=pos.min_days,
            acceptableMaxDays=pos.max_days, hardConstraint=pos.hard,
        )
        return TurnRecord(round=r, agent=spec.id, text=turn.message, position=pos)

    async def _judge_turn(
        self, mission: Mission, r: int, turns: list[TurnRecord], judge_notes: dict[int, str],
        latest_positions: list[Position], mission_brief: str, grounding: dict[str, Any] | None,
        may_rule: bool, must_rule: bool,
    ) -> JudgeTurn | None:
        messages = judge_messages(
            mission_brief=mission_brief, grounding=grounding, turns=turns, judge_notes=judge_notes,
            latest_positions=latest_positions, round_number=r, max_rounds=mission.max_rounds,
            max_shift=mission.max_shift_days, may_rule=may_rule, must_rule=must_rule,
        )
        try:
            judge, usage = await self._llm.structured(
                model=mission.model_judge, messages=messages, output=JudgeTurn,
                schema_name="judge_turn", schema=judge_json_schema(may_rule=may_rule, must_rule=must_rule),
                temperature=0.2, max_tokens=self._s.llm_judge_max_tokens,
                validate=lambda j: j.check(mission.max_shift_days, may_rule=may_rule, must_rule=must_rule),
                on_retry=lambda msg: self._emit(mission.id, ev.STATUS, value=msg),
            )
        except LLMFatalError as exc:
            raise EngineFailure(str(exc)) from exc
        except LLMError as exc:
            logger.error("judge failed mission=%s round=%d: %s", mission.id, r, exc)
            return None
        await self._usage(mission.id, usage)
        return judge

    # ------------------------------------------------------------ ruling
    async def _finalize(
        self, mission: Mission, r: int, judge: JudgeTurn | None, positions: list[Position],
        forced_resolution: str | None, *, note: str, summary: str | None,
    ) -> bool:
        if judge is not None:
            shift_days = judge.shift_days
            rng = overlap(positions)
            if rng and rng[0] <= shift_days <= rng[1]:
                resolution = "consensus"
            elif r >= mission.max_rounds:
                resolution = "forced_ruling"
            else:
                resolution = "judge_decision"
            confidence = min(judge.confidence, CONFIDENCE_CAP[resolution])
            assert summary is not None
        else:
            resolution = forced_resolution or "fallback"
            shift_days, how = mechanical_ruling(positions, mission.max_shift_days)
            confidence = CONFIDENCE_CAP["fallback"]
            summary = f"Mechanical ruling from the agents' final positions: {how}."

        recommended = shift(mission.launch_date, shift_days)
        verdict = verdict_text(mission.launch_date, shift_days)
        payload = {
            "round": r, "resolved": True, "note": note, "openIssues": [],
            "verdict": verdict, "verdictSummary": summary,
            "recommendedDate": recommended.isoformat(), "confidence": confidence,
            "shiftDays": shift_days, "resolution": resolution,
        }
        await self._repo.complete(
            mission.id, note_payload=payload, verdict=verdict, summary=summary,
            recommended=recommended, shift_days=shift_days, confidence=confidence, resolution=resolution,
        )
        self._notifier.notify(mission.id)
        logger.info("mission %s ruled: %s resolution=%s rounds=%d", mission.id, verdict, resolution, r)
        return True


