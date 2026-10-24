"""Real-world grounding data for the agents: NOAA SWPC predicted solar cycle.

The forecast is a monthly-smoothed *statistical* prediction (sunspot number and F10.7 radio
flux with low/high bounds). It covers a limited horizon; outside it we say so instead of
inventing numbers.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_FIELDS = (
    "predicted_ssn", "low_ssn", "high_ssn",
    "predicted_f10.7", "low_f10.7", "high_f10.7",
)


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


class SolarCycleGrounding:
    SOURCE = "NOAA SWPC predicted solar cycle"

    def __init__(self, url: str, timeout: float, ttl: float, client: httpx.AsyncClient | None = None) -> None:
        self._url = url
        self._ttl = ttl
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        self._cache: tuple[float, list[dict[str, Any]]] | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _records(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._cache and now - self._cache[0] < self._ttl:
            return self._cache[1]
        last_exc: Exception | None = None
        for _attempt in range(3):
            try:
                resp = await self._client.get(self._url)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list) or not data:
                    raise ValueError("unexpected payload shape")
                self._cache = (now, data)
                return data
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
        raise RuntimeError(f"NOAA solar-cycle fetch failed: {last_exc}")

    async def for_launch(self, launch: date) -> dict[str, Any]:
        """Return a grounding snapshot for the launch month (+/- 2 months).

        Always returns a dict: {"source", "available", ...}. Never raises.
        """
        base = {"source": self.SOURCE, "url": self._url, "fetchedAt": datetime.now(UTC).isoformat()}
        try:
            records = await self._records()
        except Exception as exc:  # noqa: BLE001
            logger.warning("grounding unavailable: %s", exc)
            return {**base, "available": False, "reason": "NOAA forecast could not be retrieved"}

        by_tag = {r.get("time-tag"): r for r in records}
        tags = sorted(t for t in by_tag if isinstance(t, str))
        target = f"{launch.year:04d}-{launch.month:02d}"
        if target not in by_tag:
            return {
                **base,
                "available": False,
                "reason": f"NOAA forecast covers {tags[0]} to {tags[-1]}; {target} is outside that range",
            }

        idx = tags.index(target)
        months = []
        for tag in tags[max(0, idx - 2): idx + 3]:
            rec = by_tag[tag]
            row: dict[str, Any] = {"month": tag, "isLaunchMonth": tag == target}
            for f in _FIELDS:
                row[f.replace("predicted_", "").replace(".", "")] = _num(rec.get(f))
            months.append(row)
        return {**base, "available": True, "launchMonth": target, "months": months}


def render_for_prompt(g: dict[str, Any] | None) -> str:
    """Plain-text block placed in every agent's prompt."""
    if not g or not g.get("available"):
        reason = (g or {}).get("reason", "grounding disabled")
        return (
            f"No external solar-activity data is available ({reason}). Do NOT cite specific "
            "sunspot numbers, flux values or storm forecasts; argue qualitatively and label any "
            "assumption as an assumption."
        )
    lines = [
        f"Source: {g['source']} (monthly smoothed predictions; ssn = sunspot number, "
        "f107 = 10.7 cm radio flux in sfu; low/high = forecast bounds).",
    ]
    for m in g["months"]:
        mark = "  <-- launch month" if m["isLaunchMonth"] else ""
        lines.append(
            f"{m['month']}: ssn {m['ssn']} (low {m['low_ssn']}, high {m['high_ssn']}); "
            f"f107 {m['f107']} (low {m['low_f107']}, high {m['high_f107']}){mark}"
        )
    lines.append("These are statistical cycle predictions, not forecasts of individual flares or CMEs.")
    return "\n".join(lines)
