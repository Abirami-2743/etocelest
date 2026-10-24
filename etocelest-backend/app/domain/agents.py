"""Agent roster. Ids match the frontend's colour/icon keys."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    role: str
    mandate: str


JUDGE_ID = "judge"

AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec(
        "astro",
        "Astro-Weather",
        "Solar activity, radiation exposure, and launch window safety",
        "Assess space-weather and radiation risk for the launch and transit window using the "
        "grounding data. Solar-cycle forecasts are statistical: they describe how active the Sun "
        "is expected to be in a month, they cannot predict individual flares or CMEs months ahead. "
        "Argue risk in those terms and say what a shift could and could not buy.",
    ),
    AgentSpec(
        "logistics",
        "Logistics",
        "Fuel cost, budget, and supply-chain constraints",
        "Assess the cost and feasibility of changing the launch date: propellant, holding costs, "
        "range/vendor availability, re-certification and supply-chain knock-ons.",
    ),
    AgentSpec(
        "crew",
        "Crew Readiness",
        "Crew size, training status, and life-support margins",
        "Assess crew and vehicle-operations readiness: training currency, consumables and "
        "life-support margins, and whether a shift helps or hurts. If the mission is uncrewed, say "
        "so and argue operations-team readiness instead.",
    ),
    AgentSpec(
        "missionvalue",
        "Mission Value",
        "Scientific return, public engagement, and trajectory visibility",
        "Assess what a shift costs or preserves in scientific return, trajectory/visibility "
        "geometry and programme value, and which alignments are truly hard limits.",
    ),
)

AGENT_BY_ID = {a.id: a for a in AGENTS}
AGENT_IDS = tuple(a.id for a in AGENTS)


def speaking_order(round_number: int) -> list[AgentSpec]:
    """Rotate the order each round so no agent always speaks first (or last)."""
    start = (round_number - 1) % len(AGENTS)
    return list(AGENTS[start:]) + list(AGENTS[:start])
