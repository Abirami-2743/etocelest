"""Deterministic analysis of agents' stated positions (no LLM involved)."""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    agent: str
    proposed: int
    min_days: int
    max_days: int
    hard: bool


def overlap(positions: list[Position]) -> tuple[int, int] | None:
    """Intersection of every agent's acceptable range, or None if empty / no positions."""
    if not positions:
        return None
    lo = max(p.min_days for p in positions)
    hi = min(p.max_days for p in positions)
    return (lo, hi) if lo <= hi else None


def closest_in(rng: tuple[int, int], target: float) -> int:
    lo, hi = rng
    return int(min(max(round(target), lo), hi))


def mechanical_ruling(positions: list[Position], max_shift: int) -> tuple[int, str]:
    """Ruling used only when the Judge model cannot produce one.

    Median of the final proposals; if all acceptable ranges intersect, the point of the
    intersection closest to that median. Returns (shift_days, explanation).
    """
    if not positions:
        return 0, "No agent produced a position, so the original launch date is retained."
    median = statistics.median(p.proposed for p in positions)
    rng = overlap(positions)
    if rng:
        shift = closest_in(rng, median)
        how = f"all acceptable ranges overlap ({rng[0]}-{rng[1]} days); chose the point closest to the median proposal"
    else:
        shift = int(round(median))
        how = "acceptable ranges do not fully overlap; used the median of the final proposals"
    shift = max(0, min(max_shift, shift))
    return shift, how
