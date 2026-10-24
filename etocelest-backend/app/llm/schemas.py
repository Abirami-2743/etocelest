"""Structured-output contracts for agent and judge turns.

JSON schemas are written by hand to be compatible with Groq's strict mode (all properties
required, additionalProperties=false, only basic keywords). Range checks that strict mode
cannot express are enforced by the Pydantic models + validators below.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.agents import AGENT_IDS


class AgentTurn(BaseModel):
    message: str = Field(min_length=20, max_length=1500)
    proposed_shift_days: int
    acceptable_min_days: int
    acceptable_max_days: int
    hard_constraint: bool

    @field_validator("message")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    def check_bounds(self, max_shift: int) -> None:
        if not (0 <= self.acceptable_min_days <= self.proposed_shift_days <= self.acceptable_max_days <= max_shift):
            raise ValueError(
                f"require 0 <= acceptable_min_days <= proposed_shift_days <= acceptable_max_days <= {max_shift}; "
                f"got min={self.acceptable_min_days}, proposed={self.proposed_shift_days}, "
                f"max={self.acceptable_max_days}"
            )


class OpenIssue(BaseModel):
    agent: Literal["astro", "logistics", "crew", "missionvalue", "all"]
    question: str = Field(min_length=5, max_length=500)


class JudgeTurn(BaseModel):
    decision: Literal["rule", "reopen"]
    note: str = Field(min_length=10, max_length=1200)
    open_issues: list[OpenIssue]
    shift_days: int
    confidence: int
    summary: str

    def check(self, max_shift: int, *, may_rule: bool, must_rule: bool) -> None:
        if self.decision == "rule":
            if not may_rule:
                raise ValueError("it is too early to rule; decision must be 'reopen'")
            if not 0 <= self.shift_days <= max_shift:
                raise ValueError(f"shift_days must be within 0..{max_shift}")
            if not 0 <= self.confidence <= 100:
                raise ValueError("confidence must be within 0..100")
            if len(self.summary.strip()) < 40:
                raise ValueError("summary must be a substantive explanation (>= 40 characters)")
        else:
            if must_rule:
                raise ValueError("the round cap is reached; decision must be 'rule'")
            if not self.open_issues:
                raise ValueError("a 'reopen' decision must list at least one open_issue")


def agent_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "proposed_shift_days": {"type": "integer"},
            "acceptable_min_days": {"type": "integer"},
            "acceptable_max_days": {"type": "integer"},
            "hard_constraint": {"type": "boolean"},
        },
        "required": ["message", "proposed_shift_days", "acceptable_min_days", "acceptable_max_days", "hard_constraint"],
        "additionalProperties": False,
    }


def judge_json_schema(*, may_rule: bool, must_rule: bool) -> dict[str, Any]:
    decisions = ["rule"] if must_rule else (["rule", "reopen"] if may_rule else ["reopen"])
    return {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": decisions},
            "note": {"type": "string"},
            "open_issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "enum": [*AGENT_IDS, "all"]},
                        "question": {"type": "string"},
                    },
                    "required": ["agent", "question"],
                    "additionalProperties": False,
                },
            },
            "shift_days": {"type": "integer"},
            "confidence": {"type": "integer"},
            "summary": {"type": "string"},
        },
        "required": ["decision", "note", "open_issues", "shift_days", "confidence", "summary"],
        "additionalProperties": False,
    }
