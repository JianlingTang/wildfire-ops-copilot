"""Row/AOI validation and payload formatting for hotspot responses."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.schemas import Aoi
from app.tools.fire_hotspot_tools.constants import (
    DEA_REFRESH_INTERVAL_SECONDS,
    OVERVIEW_MAP_HOTSPOT_LIMIT,
    OVERVIEW_RADIUS_OPTIONS_KM,
    STATE_LABELS,
)
from app.tools.fire_hotspot_tools.geo_math import _focus_center_for_state, _sample_rows_for_map


def _validate_aoi(aoi: Aoi | dict) -> dict:
    if isinstance(aoi, dict) and aoi.get("simulate_failure"):
        return {"status": "error", "message": "Hotspot provider failure simulated."}
    radius = aoi.get("radius_km") if isinstance(aoi, dict) else aoi.radius_km
    if radius is None or radius <= 0:
        return {"status": "error", "message": "AOI radius_km must be positive."}
    return {"status": "success"}


def _serialize_hotspot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "lat": row["lat"],
        "lon": row["lon"],
        "state": row.get("state"),
        "confidence": row.get("confidence", "unknown"),
        "detected_at": (
            row["detected_at"].isoformat() if isinstance(row.get("detected_at"), datetime) else "unknown"
        ),
        "power": row.get("power"),
        "satellite": row.get("satellite"),
        "sensor": row.get("sensor"),
    }


def _normalize_state_code(value: Any) -> str | None:
    if not value:
        return None
    state_code = str(value).strip().upper()
    return state_code if state_code in STATE_LABELS else None


def _format_hotspot_payload(
    rows: list[dict[str, Any]],
    time_window: str,
    *,
    source: str,
    count_window_days: int,
) -> dict:
    now = datetime.now(UTC)
    sorted_rows = sorted(
        rows,
        key=lambda row: row.get("detected_at") or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    count_24h = sum(
        1
        for row in sorted_rows
        if isinstance(row.get("detected_at"), datetime) and row["detected_at"] >= now - timedelta(hours=24)
    )
    hotspots = [_serialize_hotspot(row) for row in sorted_rows[:50]]
    return {
        "status": "success",
        "mode": "live",
        "source": source,
        "data": {
            "time_window": time_window,
            "count_24h": count_24h,
            "count_7d": len(sorted_rows),
            "count_window_days": count_window_days,
            "hotspots": hotspots,
        },
    }


def _build_australia_hotspot_overview(
    rows: list[dict[str, Any]],
    *,
    mode: str,
    source: str,
    message: str | None = None,
) -> dict:
    now = datetime.now(UTC)
    active_rows = _active_rows(rows, now)
    sorted_rows = sorted(
        active_rows,
        key=lambda row: row.get("detected_at") or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    states = _state_summaries(sorted_rows)
    sampled_rows = _sample_rows_for_map(sorted_rows, OVERVIEW_MAP_HOTSPOT_LIMIT, cell_size=0.16)

    payload = {
        "status": "success",
        "mode": mode,
        "source": source,
        "cached": False,
        "cache_ttl_seconds": DEA_REFRESH_INTERVAL_SECONDS,
        "data": {
            "time_window": "24h",
            "updated_at": now.isoformat(),
            "total_count_24h": len(sorted_rows),
            "display_hotspot_count": len(sampled_rows),
            "hotspots": [_serialize_hotspot(row) for row in sampled_rows],
            "states": states,
        },
    }
    if message:
        payload["message"] = message
    return payload


def _active_rows(rows: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    cutoff = now - timedelta(hours=24)
    active_rows = [row for row in rows if isinstance(row.get("detected_at"), datetime) and row["detected_at"] >= cutoff]
    return active_rows or rows


def _state_summaries(sorted_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    state_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted_rows:
        state_code = _normalize_state_code(row.get("state"))
        if state_code:
            state_rows[state_code].append(row)

    states = []
    for state_code, label in STATE_LABELS.items():
        rows_for_state = state_rows.get(state_code, [])
        center = _focus_center_for_state(rows_for_state, state_code)
        states.append(
            {
                "state": state_code,
                "label": label,
                "count_24h": len(rows_for_state),
                "center": [center[0], center[1]],
                "region_id": f"state_{state_code.lower()}",
                "region_name": f"{label} hotspot focus",
                "radius_options_km": OVERVIEW_RADIUS_OPTIONS_KM,
            }
        )
    return states
