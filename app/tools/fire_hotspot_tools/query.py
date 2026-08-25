"""The public read API over hotspot data: single-AOI, state-focus, and
national-overview queries.

get_state_hotspot_focus and _fetch_dea_hotspots resolve
_get_or_load_australia_hotspot_rows through the package's own module object
(not a direct import from cache.py) because tests monkeypatch it at
app.tools.fire_hotspot_tools._get_or_load_australia_hotspot_rows — a direct
`from .cache import _get_or_load_australia_hotspot_rows` would bind to the
unpatched function and silently ignore the test's fake.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import app.tools.fire_hotspot_tools as _pkg
from app.models.schemas import Aoi
from app.tools.fire_hotspot_tools.cache import _get_cached_australia_overview, _store_cached_australia_overview
from app.tools.fire_hotspot_tools.constants import DEA_REFRESH_INTERVAL_SECONDS, STATE_LABELS
from app.tools.fire_hotspot_tools.demo_data import (
    _demo_australia_hotspot_overview,
    _demo_australia_hotspot_rows,
    _demo_hotspots,
)
from app.tools.fire_hotspot_tools.format import (
    _format_hotspot_payload,
    _normalize_state_code,
    _serialize_hotspot,
    _validate_aoi,
)
from app.tools.fire_hotspot_tools.geo_math import _focus_center_for_state, _sample_rows_for_map
from app.tools.provider_utils import coerce_center, coerce_radius_km, external_data_mode, haversine_km

FOCUS_MAP_HOTSPOT_LIMIT = 1600


def get_fire_hotspots(aoi: Aoi | dict, time_window: str = "24h") -> dict:
    validation = _validate_aoi(aoi)
    if validation["status"] == "error":
        return validation
    if external_data_mode() == "demo":
        return _demo_hotspots(time_window)

    try:
        return _fetch_dea_hotspots(aoi, time_window)
    except Exception as exc:
        return {"status": "error", "message": f"Live hotspot cache unavailable: {exc}"}


def get_australia_hotspots_overview() -> dict:
    if external_data_mode() == "demo":
        payload = _demo_australia_hotspot_overview()
        _store_cached_australia_overview(payload, _demo_australia_hotspot_rows())
        return payload

    cached = _get_cached_australia_overview(include_stale=True)
    if cached:
        cached["cached"] = True
        return cached

    return {
        "status": "error",
        "message": "Live DEA hotspot cache is not ready yet. Background ingestion has not completed.",
    }


def get_state_hotspot_focus(state: str, radius_km: int | float) -> dict:
    state_code = _normalize_state_code(state)
    if not state_code:
        return {"status": "error", "message": f"Unsupported state code: {state}"}
    if radius_km <= 0:
        return {"status": "error", "message": "radius_km must be positive."}

    try:
        rows, mode, source, cached = _pkg._get_or_load_australia_hotspot_rows()
    except Exception as exc:
        return {"status": "error", "message": f"Live hotspot focus failed: {exc}"}
    state_rows, center, focus_rows = _state_focus_rows(rows, state_code, radius_km)
    sampled_rows = _sample_rows_for_map(focus_rows, FOCUS_MAP_HOTSPOT_LIMIT, cell_size=0.07)

    return {
        "status": "success",
        "mode": mode,
        "source": source,
        "cached": cached,
        "cache_ttl_seconds": DEA_REFRESH_INTERVAL_SECONDS,
        "data": {
            "state": state_code,
            "label": STATE_LABELS[state_code],
            "region_id": f"state_{state_code.lower()}",
            "region_name": f"{STATE_LABELS[state_code]} hotspot cluster focus",
            "center": [center[0], center[1]],
            "radius_km": float(radius_km),
            "hotspot_count_24h": len(focus_rows),
            "statewide_hotspot_count_24h": len(state_rows),
            "display_hotspot_count": len(sampled_rows),
            "hotspots": [_serialize_hotspot(row) for row in sampled_rows],
        },
    }


def _state_focus_rows(
    rows: list[dict[str, Any]], state_code: str, radius_km: int | float
) -> tuple[list[dict[str, Any]], tuple[float, float], list[dict[str, Any]]]:
    now = datetime.now(UTC)
    active_rows = [
        row
        for row in rows
        if isinstance(row.get("detected_at"), datetime) and row["detected_at"] >= now - timedelta(hours=24)
    ] or rows
    state_rows = [row for row in active_rows if _normalize_state_code(row.get("state")) == state_code]
    center = _focus_center_for_state(state_rows, state_code)
    focus_rows = [
        row for row in state_rows if haversine_km(center[0], center[1], row["lat"], row["lon"]) <= float(radius_km)
    ]
    return state_rows, center, focus_rows


def _fetch_dea_hotspots(aoi: Aoi | dict, time_window: str) -> dict:
    latitude, longitude = coerce_center(aoi)
    radius_km = coerce_radius_km(aoi)
    rows, _, _, _ = _pkg._get_or_load_australia_hotspot_rows()
    filtered_rows = [row for row in rows if haversine_km(latitude, longitude, row["lat"], row["lon"]) <= radius_km]
    return _format_hotspot_payload(filtered_rows, time_window, source="DEA Hotspots recent feed", count_window_days=3)
