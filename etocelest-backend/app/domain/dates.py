"""Locale-independent date helpers."""

from __future__ import annotations

from datetime import date, timedelta

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def format_date(d: date) -> str:
    return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"


def shift(d: date, days: int) -> date:
    return d + timedelta(days=days)


def verdict_text(launch: date, shift_days: int) -> str:
    if shift_days == 0:
        return "Proceed on original date"
    return f"Shift launch to {format_date(shift(launch, shift_days))} (+{shift_days} days)"
