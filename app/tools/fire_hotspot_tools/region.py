"""Resolves a chat/analysis request's region_id + AOI into a concrete region
context (fixed AOI, state focus, explicit state AOI, or auto-selected live
hotspot cluster).

Like query.py, _explicit_state_aoi_region and _select_live_hotspot_region
resolve _get_or_load_australia_hotspot_rows through the package's own module
object rather than importing it directly from cache.py, to keep tests'
monkeypatch on app.tools.fire_hotspot_tools._get_or_load_australia_hotspot_rows
in effect (see the comment in query.py for why).
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from math import floor
from typing import Any

import app.tools.fire_hotspot_tools as _pkg
from app.models.schemas import Aoi
from app.tools.fire_hotspot_tools.constants import AUTO_REGION_IDS, STATE_FOCUS_DEFAULTS, STATE_LABELS
from app.tools.fire_hotspot_tools.demo_data import _demo_live_region_selection
from app.tools.fire_hotspot_tools.format import _format_hotspot_payload, _normalize_state_code, _serialize_hotspot
from app.tools.fire_hotspot_tools.geo_math import _cluster_score, _sample_rows_for_map, _weighted_center
from app.tools.fire_hotspot_tools.query import FOCUS_MAP_HOTSPOT_LIMIT, get_state_hotspot_focus
from app.tools.provider_utils import external_data_mode, haversine_km


def resolve_operational_region(
    region_id: str,
    region_name: str,
    aoi: Aoi | None = None,
    *,
    respect_explicit_aoi: bool = False,
) -> dict[str, Any]:
    if region_id not in AUTO_REGION_IDS:
        return _fixed_or_focused_region(region_id, region_name, aoi, respect_explicit_aoi=respect_explicit_aoi)

    if external_data_mode() == "demo":
        return _demo_live_region_selection()

    try:
        return _select_live_hotspot_region()
    except Exception as exc:
        return _error_operational_region(
            region_id, region_name, aoi or Aoi(), f"Live hotspot region selection failed: {exc}"
        )


def _fixed_or_focused_region(
    region_id: str, region_name: str, aoi: Aoi | None, *, respect_explicit_aoi: bool
) -> dict[str, Any]:
    actual_aoi = aoi or Aoi()
    state_code = _state_code_from_region_id(region_id)
    if respect_explicit_aoi and state_code and actual_aoi.center:
        return _explicit_state_aoi_region(state_code, region_id, region_name, actual_aoi)
    if state_code and actual_aoi.radius_km:
        focused_region = _resolve_state_focus_region(state_code, region_id, region_name, actual_aoi)
        if focused_region is not None:
            return focused_region
    return {
        "region_id": region_id,
        "region_name": region_name,
        "aoi": actual_aoi,
        "hotspots": None,
        "region_context": {
            "selection_mode": "fixed",
            "state": state_code,
            "region_id": region_id,
            "region_name": region_name,
            "center": list(actual_aoi.center or (-33.71, 150.31)),
            "radius_km": actual_aoi.radius_km,
        },
    }


def _state_code_from_region_id(region_id: str) -> str | None:
    if not region_id.startswith("state_"):
        return None
    return _normalize_state_code(region_id.replace("state_", "", 1))


def _error_operational_region(region_id: str, region_name: str, aoi: Aoi, message: str) -> dict[str, Any]:
    center = aoi.center or (-33.71, 150.31)
    return {
        "region_id": region_id,
        "region_name": region_name,
        "aoi": aoi,
        "hotspots": {"status": "error", "message": message, "data": {"hotspots": [], "count_24h": 0}},
        "region_context": {
            "selection_mode": "provider_error",
            "region_id": region_id,
            "region_name": region_name,
            "center": list(center),
            "radius_km": aoi.radius_km,
            "provider_error": message,
        },
    }


def _explicit_state_aoi_region(state_code: str, region_id: str, region_name: str, aoi: Aoi) -> dict[str, Any]:
    center = aoi.center or STATE_FOCUS_DEFAULTS[state_code]
    radius_km = float(aoi.radius_km)
    rows, mode, source, cached = _explicit_aoi_rows()
    state_rows, focus_rows = _explicit_aoi_focus_rows(rows, state_code, center, radius_km)
    hotspot_payload = _explicit_aoi_hotspot_payload(mode, source, cached, state_rows, focus_rows)

    return {
        "region_id": region_id,
        "region_name": region_name,
        "aoi": aoi,
        "hotspots": hotspot_payload,
        "region_context": {
            "selection_mode": "selected_aoi",
            "state": state_code,
            "region_id": region_id,
            "region_name": region_name,
            "center": list(center),
            "radius_km": radius_km,
            "selected_at": datetime.now(UTC).isoformat(),
            "hotspot_count_24h": len(focus_rows),
            "statewide_hotspot_count_24h": len(state_rows),
        },
    }


def _explicit_aoi_rows() -> tuple[list[dict[str, Any]], str, str, bool]:
    try:
        return _pkg._get_or_load_australia_hotspot_rows()
    except Exception as exc:
        return [], "error", f"DEA Hotspots unavailable: {exc}", False


def _explicit_aoi_focus_rows(
    rows: list[dict[str, Any]], state_code: str, center: tuple[float, float], radius_km: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    now = datetime.now(UTC)
    active_rows = [
        row
        for row in rows
        if isinstance(row.get("detected_at"), datetime) and row["detected_at"] >= now - timedelta(hours=24)
    ] or rows
    state_rows = [row for row in active_rows if _normalize_state_code(row.get("state")) == state_code]
    focus_rows = [
        row for row in state_rows if haversine_km(center[0], center[1], row["lat"], row["lon"]) <= radius_km
    ]
    return state_rows, focus_rows


def _explicit_aoi_hotspot_payload(
    mode: str, source: str, cached: bool, state_rows: list[dict[str, Any]], focus_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    sampled_rows = _sample_rows_for_map(focus_rows, FOCUS_MAP_HOTSPOT_LIMIT, cell_size=0.07)
    hotspot_payload: dict[str, Any] = {
        "status": "error" if mode == "error" else "success",
        "mode": mode,
        "source": source,
        "cached": cached,
        "data": {
            "time_window": "24h",
            "count_24h": len(focus_rows),
            "count_7d": len(state_rows),
            "count_window_days": 1,
            "hotspots": [_serialize_hotspot(row) for row in sampled_rows],
        },
    }
    if mode == "error":
        hotspot_payload["message"] = source
    return hotspot_payload


def _resolve_state_focus_region(state_code: str, region_id: str, region_name: str, aoi: Aoi) -> dict[str, Any] | None:
    focus = get_state_hotspot_focus(state_code, aoi.radius_km)
    if focus.get("status") != "success":
        return None

    center = tuple(focus["data"]["center"])
    radius_km = float(focus["data"]["radius_km"])
    hotspot_count_24h = int(focus["data"]["hotspot_count_24h"])
    statewide_hotspot_count_24h = int(focus["data"]["statewide_hotspot_count_24h"])
    selected_at = datetime.now(UTC).isoformat()
    hotspot_payload = {
        "status": "success",
        "mode": focus.get("mode", "live"),
        "source": focus.get("source", "DEA Hotspots recent feed"),
        "cached": focus.get("cached", False),
        "cache_ttl_seconds": focus.get("cache_ttl_seconds"),
        "data": {
            "time_window": "24h",
            "count_24h": hotspot_count_24h,
            "count_7d": statewide_hotspot_count_24h,
            "count_window_days": 1,
            "hotspots": deepcopy(focus["data"]["hotspots"]),
        },
    }
    return {
        "region_id": region_id,
        "region_name": region_name,
        "aoi": Aoi(center=center, radius_km=radius_km),
        "hotspots": hotspot_payload,
        "region_context": {
            "selection_mode": "state_focus",
            "state": state_code,
            "region_id": region_id,
            "region_name": region_name,
            "center": list(center),
            "radius_km": radius_km,
            "selected_at": selected_at,
            "hotspot_count_24h": hotspot_count_24h,
            "statewide_hotspot_count_24h": statewide_hotspot_count_24h,
        },
    }


def _select_live_hotspot_region() -> dict[str, Any]:
    rows, _, _, _ = _pkg._get_or_load_australia_hotspot_rows()
    if not rows:
        raise ValueError("DEA Hotspots feed returned no usable hotspot rows.")

    now = datetime.now(UTC)
    candidate_rows = _candidate_rows_for_clustering(rows, now)
    cluster_key, cluster_rows = _best_cluster(candidate_rows)
    state_code = cluster_key[0]
    center_lat, center_lon = _weighted_center(cluster_rows)
    region_id = f"live_{state_code.lower()}_{abs(cluster_key[1])}_{abs(cluster_key[2])}"
    region_name = f"{STATE_LABELS.get(state_code, state_code)} live hotspot cluster"
    radius_km = 40 if len(cluster_rows) >= 8 else 30

    return {
        "region_id": region_id,
        "region_name": region_name,
        "aoi": Aoi(center=(center_lat, center_lon), radius_km=radius_km),
        "hotspots": _format_hotspot_payload(
            cluster_rows, "24h", source="DEA Hotspots recent feed", count_window_days=3
        ),
        "region_context": {
            "selection_mode": "auto_live_hotspot",
            "state": state_code,
            "region_id": region_id,
            "region_name": region_name,
            "center": [center_lat, center_lon],
            "radius_km": radius_km,
            "selected_at": now.isoformat(),
            "hotspot_count_24h": sum(
                1 for row in cluster_rows if row.get("detected_at") and row["detected_at"] >= now - timedelta(hours=24)
            ),
        },
    }


def _candidate_rows_for_clustering(rows: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    candidate_rows = [row for row in rows if row["detected_at"] and row["detected_at"] >= now - timedelta(hours=24)]
    if not candidate_rows:
        candidate_rows = [row for row in rows if row["detected_at"] and row["detected_at"] >= now - timedelta(hours=72)]
    return candidate_rows or rows


def _best_cluster(
    candidate_rows: list[dict[str, Any]],
) -> tuple[tuple[str, int, int], list[dict[str, Any]]]:
    clusters: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    cell_size = 0.35
    for row in candidate_rows:
        state = str(row.get("state") or "AU").strip() or "AU"
        key = (state, floor(row["lat"] / cell_size), floor(row["lon"] / cell_size))
        clusters[key].append(row)
    return max(clusters.items(), key=lambda item: _cluster_score(item[1]))
