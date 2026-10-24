"""Event vocabulary and folding the event log into the rounds structure the UI renders."""

from __future__ import annotations

from typing import Any

STATUS = "status"
ROUND_START = "round_start"
TURN_START = "turn_start"
TURN_TEXT = "turn_text"
TURN_FAILED = "turn_failed"
JUDGE_EVALUATING = "judge_evaluating"
JUDGE_NOTE = "judge_note"
DONE = "done"
ERROR = "error"

TERMINAL = frozenset({DONE, ERROR})


def fold_rounds(events: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Fold (type, payload) events, in order, into `[{round, turns, judge}]`."""
    rounds: dict[int, dict[str, Any]] = {}
    for etype, p in events:
        n = p.get("round")
        if etype == ROUND_START:
            rounds[n] = {"round": n, "turns": [], "judge": None}
        elif etype in (TURN_TEXT, TURN_FAILED) and n in rounds:
            turn = {"agent": p["agent"], "text": p["text"], "failed": etype == TURN_FAILED}
            for k in ("proposedShiftDays", "acceptableMinDays", "acceptableMaxDays", "hardConstraint"):
                if k in p:
                    turn[k] = p[k]
            rounds[n]["turns"].append(turn)
        elif etype == JUDGE_NOTE and n in rounds:
            rounds[n]["judge"] = {
                "resolved": p["resolved"],
                "note": p["note"],
                "openIssues": p.get("openIssues", []),
            }
    return [rounds[k] for k in sorted(rounds)]
