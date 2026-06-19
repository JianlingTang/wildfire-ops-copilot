from __future__ import annotations

import os
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from math import ceil, floor
from typing import Any

import httpx

from app.models.schemas import Aoi
from app.tools.provider_utils import (
    coerce_bbox,
    coerce_center,
    coerce_radius_km,
    external_data_mode,
    haversine_km,
    http_user_agent,
    request_timeout_seconds,
)

DEA_HOTSPOTS_URL = "https://hotspots.dea.ga.gov.au/data/recent-hotspots.json"
NASA_FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov"
NASA_FIRMS_SOURCE = "VIIRS_NOAA20_NRT"
AUTO_REGION_IDS = {"live_australia", "auto", "auto_australia"}
STATE_LABELS = {
    "ACT": "Australian Capital Territory",
    "NSW": "New South Wales",
    "QLD": "Queensland",
    "NT": "Northern Territory",
    "WA": "Western Australia",
    "VIC": "Victoria",
    "SA": "South Australia",
    "TAS": "Tasmania",
}
STATE_FOCUS_DEFAULTS = {
    "ACT": (-35.4735, 149.0124),
    "NSW": (-32.1633, 147.0166),
    "QLD": (-21.1411, 145.3260),
    "NT": (-19.4914, 133.6146),
    "WA": (-25.2303, 121.0187),
    "VIC": (-36.7604, 144.2811),
    "SA": (-30.0002, 136.2092),
    "TAS": (-42.0409, 146.8087),
}
OVERVIEW_RADIUS_OPTIONS_KM = [30, 50, 100, 200]
OVERVIEW_CACHE_TTL_SECONDS = 180
OVERVIEW_MAP_HOTSPOT_LIMIT = 2400
FOCUS_MAP_HOTSPOT_LIMIT = 1600
_AUSTRALIA_OVERVIEW_CACHE: dict[str, Any] = {"expires_at": None, "payload": None, "rows": None}


def get_fire_hotspots(aoi: Aoi | dict, time_window: str = "24h") -> dict:
    validation = _validate_aoi(aoi)
    if validation["status"] == "error":
        return validation
    if external_data_mode() == "demo":
        return _demo_hotspots(time_window)

    errors: list[str] = []
    nasa_key = _nasa_firms_api_key()
    if nasa_key:
        try:
            return _fetch_nasa_firms_hotspots(aoi, nasa_key, time_window)
        except Exception as exc:
            errors.append(f"NASA FIRMS failed: {exc}")

    try:
        return _fetch_dea_hotspots(aoi, time_window)
    except Exception as exc:
        errors.append(f"DEA Hotspots failed: {exc}")

    return {"status": "error", "message": "; ".join(errors) or "No live hotspot provider succeeded."}


def get_australia_hotspots_overview() -> dict:
    cached = _get_cached_australia_overview()
    if cached:
        cached["cached"] = True
        return cached

    if external_data_mode() == "demo":
        payload = _demo_australia_hotspot_overview()
        _store_cached_australia_overview(payload, _demo_australia_hotspot_rows())
        return payload

    try:
        rows = _fetch_australia_hotspot_rows()
        payload = _build_australia_hotspot_overview(
            rows,
            mode="live",
            source="DEA Hotspots recent feed",
        )
        _store_cached_australia_overview(payload, rows)
        return payload
    except Exception as exc:
        stale = _get_cached_australia_overview(include_stale=True)
        if stale:
            stale["cached"] = True
            stale["message"] = f"Serving cached Australia hotspot overview after refresh failure: {exc}"
            return stale
        return {"status": "error", "message": f"Live hotspot overview failed: {exc}"}


def get_state_hotspot_focus(state: str, radius_km: int | float) -> dict:
    state_code = _normalize_state_code(state)
    if not state_code:
        return {"status": "error", "message": f"Unsupported state code: {state}"}
    if radius_km <= 0:
        return {"status": "error", "message": "radius_km must be positive."}

    try:
        rows, mode, source, cached = _get_or_load_australia_hotspot_rows()
    except Exception as exc:
        return {"status": "error", "message": f"Live hotspot focus failed: {exc}"}
    now = datetime.now(UTC)
    active_rows = [
        row
        for row in rows
        if isinstance(row.get("detected_at"), datetime)
        and row["detected_at"] >= now - timedelta(hours=24)
    ]
    if not active_rows:
        active_rows = rows

    state_rows = [row for row in active_rows if _normalize_state_code(row.get("state")) == state_code]
    center = _focus_center_for_state(state_rows, state_code)
    focus_rows = [
        row
        for row in state_rows
        if haversine_km(center[0], center[1], row["lat"], row["lon"]) <= float(radius_km)
    ]
    sampled_rows = _sample_rows_for_map(focus_rows, FOCUS_MAP_HOTSPOT_LIMIT, cell_size=0.07)

    return {
        "status": "success",
        "mode": mode,
        "source": source,
        "cached": cached,
        "cache_ttl_seconds": OVERVIEW_CACHE_TTL_SECONDS,
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


def resolve_operational_region(
    region_id: str,
    region_name: str,
    aoi: Aoi | None = None,
    *,
    respect_explicit_aoi: bool = False,
) -> dict[str, Any]:
    if region_id not in AUTO_REGION_IDS:
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
                "state": _state_code_from_region_id(region_id),
                "region_id": region_id,
                "region_name": region_name,
                "center": list(actual_aoi.center or (-33.71, 150.31)),
                "radius_km": actual_aoi.radius_km,
            },
        }

    if external_data_mode() == "demo":
        return _demo_live_region_selection()

    try:
        return _select_live_hotspot_region()
    except Exception as exc:
        return _error_operational_region(
            region_id,
            region_name,
            aoi or Aoi(),
            f"Live hotspot region selection failed: {exc}",
        )


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


def _explicit_state_aoi_region(
    state_code: str,
    region_id: str,
    region_name: str,
    aoi: Aoi,
) -> dict[str, Any]:
    center = aoi.center or STATE_FOCUS_DEFAULTS[state_code]
    radius_km = float(aoi.radius_km)
    selected_at = datetime.now(UTC).isoformat()
    try:
        rows, mode, source, cached = _get_or_load_australia_hotspot_rows()
    except Exception as exc:
        rows = []
        mode = "error"
        source = f"DEA Hotspots unavailable: {exc}"
        cached = False

    now = datetime.now(UTC)
    active_rows = [
        row
        for row in rows
        if isinstance(row.get("detected_at"), datetime)
        and row["detected_at"] >= now - timedelta(hours=24)
    ]
    if not active_rows:
        active_rows = rows
    state_rows = [row for row in active_rows if _normalize_state_code(row.get("state")) == state_code]
    focus_rows = [
        row
        for row in state_rows
        if haversine_km(center[0], center[1], row["lat"], row["lon"]) <= radius_km
    ]
    sampled_rows = _sample_rows_for_map(focus_rows, FOCUS_MAP_HOTSPOT_LIMIT, cell_size=0.07)
    hotspot_count_24h = len(focus_rows)
    statewide_hotspot_count_24h = len(state_rows)
    hotspot_payload = {
        "status": "error" if mode == "error" else "success",
        "mode": mode,
        "source": source,
        "cached": cached,
        "data": {
            "time_window": "24h",
            "count_24h": hotspot_count_24h,
            "count_7d": statewide_hotspot_count_24h,
            "count_window_days": 1,
            "hotspots": [_serialize_hotspot(row) for row in sampled_rows],
        },
    }
    if mode == "error":
        hotspot_payload["message"] = source

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
            "selected_at": selected_at,
            "hotspot_count_24h": hotspot_count_24h,
            "statewide_hotspot_count_24h": statewide_hotspot_count_24h,
        },
    }


def _resolve_state_focus_region(
    state_code: str,
    region_id: str,
    region_name: str,
    aoi: Aoi,
) -> dict[str, Any] | None:
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


def _validate_aoi(aoi: Aoi | dict) -> dict:
    if isinstance(aoi, dict) and aoi.get("simulate_failure"):
        return {"status": "error", "message": "Hotspot provider failure simulated."}
    radius = aoi.get("radius_km") if isinstance(aoi, dict) else aoi.radius_km
    if radius is None or radius <= 0:
        return {"status": "error", "message": "AOI radius_km must be positive."}
    return {"status": "success"}


def _fetch_nasa_firms_hotspots(aoi: Aoi | dict, api_key: str, time_window: str) -> dict:
    west, south, east, north = coerce_bbox(aoi)
    bbox = f"{west:.4f},{south:.4f},{east:.4f},{north:.4f}"
    response = httpx.get(
        f"{NASA_FIRMS_BASE_URL}/api/area/csv/{api_key}/{NASA_FIRMS_SOURCE}/{bbox}/7",
        headers={"User-Agent": http_user_agent()},
        timeout=request_timeout_seconds(default=12.0),
    )
    response.raise_for_status()
    rows = _parse_nasa_csv(response.text)
    return _format_hotspot_payload(rows, time_window, source=f"NASA FIRMS {NASA_FIRMS_SOURCE}", count_window_days=7)


def _fetch_dea_hotspots(aoi: Aoi | dict, time_window: str) -> dict:
    latitude, longitude = coerce_center(aoi)
    radius_km = coerce_radius_km(aoi)
    features = _fetch_dea_features()
    filtered_rows: list[dict[str, Any]] = []
    for feature in features:
        row = _dea_feature_to_row(feature)
        if not row:
            continue
        if haversine_km(latitude, longitude, row["lat"], row["lon"]) > radius_km:
            continue
        filtered_rows.append(row)
    return _format_hotspot_payload(
        filtered_rows,
        time_window,
        source="DEA Hotspots recent feed",
        count_window_days=3,
    )


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
    hotspots = [
        {
            "lat": row["lat"],
            "lon": row["lon"],
            "state": row.get("state"),
            "confidence": row.get("confidence", "unknown"),
            "detected_at": (
                row["detected_at"].isoformat()
                if isinstance(row.get("detected_at"), datetime)
                else "unknown"
            ),
            "power": row.get("power"),
            "satellite": row.get("satellite"),
            "sensor": row.get("sensor"),
        }
        for row in sorted_rows[:50]
    ]
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
    active_rows = [
        row
        for row in rows
        if isinstance(row.get("detected_at"), datetime)
        and row["detected_at"] >= now - timedelta(hours=24)
    ]
    if not active_rows:
        active_rows = rows

    sorted_rows = sorted(
        active_rows,
        key=lambda row: row.get("detected_at") or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
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

    sampled_rows = _sample_rows_for_map(
        sorted_rows,
        OVERVIEW_MAP_HOTSPOT_LIMIT,
        cell_size=0.16,
    )

    payload = {
        "status": "success",
        "mode": mode,
        "source": source,
        "cached": False,
        "cache_ttl_seconds": OVERVIEW_CACHE_TTL_SECONDS,
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


def _select_live_hotspot_region() -> dict[str, Any]:
    rows = [row for row in (_dea_feature_to_row(feature) for feature in _fetch_dea_features()) if row]
    if not rows:
        raise ValueError("DEA Hotspots feed returned no usable hotspot rows.")

    now = datetime.now(UTC)
    candidate_rows = [row for row in rows if row["detected_at"] and row["detected_at"] >= now - timedelta(hours=24)]
    if not candidate_rows:
        candidate_rows = [row for row in rows if row["detected_at"] and row["detected_at"] >= now - timedelta(hours=72)]
    if not candidate_rows:
        candidate_rows = rows

    clusters: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    cell_size = 0.35
    for row in candidate_rows:
        state = str(row.get("state") or "AU").strip() or "AU"
        key = (state, floor(row["lat"] / cell_size), floor(row["lon"] / cell_size))
        clusters[key].append(row)

    cluster_key, cluster_rows = max(clusters.items(), key=lambda item: _cluster_score(item[1]))
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
            cluster_rows,
            "24h",
            source="DEA Hotspots recent feed",
            count_window_days=3,
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
                1
                for row in cluster_rows
                if row.get("detected_at") and row["detected_at"] >= now - timedelta(hours=24)
            ),
        },
    }


def _parse_nasa_csv(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return rows
    headers = [header.strip() for header in lines[0].split(",")]
    for line in lines[1:]:
        values = [value.strip() for value in line.split(",")]
        row = dict(zip(headers, values, strict=False))
        lat = float(row["latitude"])
        lon = float(row["longitude"])
        detected_at = _coerce_datetime(f"{row.get('acq_date', '')}T{row.get('acq_time', '0000').zfill(4)}")
        rows.append(
            {
                "lat": lat,
                "lon": lon,
                "confidence": row.get("confidence", "unknown"),
                "detected_at": detected_at,
                "power": float(row["frp"]) if row.get("frp") else None,
                "satellite": row.get("satellite"),
                "sensor": row.get("instrument"),
                "state": None,
            }
        )
    return rows


def _fetch_dea_features() -> list[dict[str, Any]]:
    response = httpx.get(
        DEA_HOTSPOTS_URL,
        headers={"User-Agent": http_user_agent()},
        timeout=request_timeout_seconds(default=15.0),
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("features", [])


def _fetch_australia_hotspot_rows() -> list[dict[str, Any]]:
    return [row for row in (_dea_feature_to_row(feature) for feature in _fetch_dea_features()) if row]


def _dea_feature_to_row(feature: dict[str, Any]) -> dict[str, Any] | None:
    geometry = feature.get("geometry", {})
    coordinates = geometry.get("coordinates", [])
    if len(coordinates) != 2:
        return None
    properties = feature.get("properties", {})
    return {
        "lat": float(coordinates[1]),
        "lon": float(coordinates[0]),
        "confidence": str(properties.get("confidence", "unknown")),
        "detected_at": _coerce_datetime(properties.get("datetime")),
        "power": properties.get("power"),
        "satellite": properties.get("satellite"),
        "sensor": properties.get("sensor"),
        "state": str(properties.get("australian_state", "")).strip() or None,
    }


def _coerce_datetime(raw_value: Any) -> datetime | None:
    if not raw_value:
        return None
    value = str(raw_value).strip()
    if len(value) == 15 and "T" in value and value.count(":") == 0:
        value = f"{value[:11]}{value[11:13]}:{value[13:15]}:00"
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _nasa_firms_api_key() -> str | None:
    return (os.getenv("NASA_FIRMS_API_KEY") or os.getenv("NASA_FIRMS_MAP_KEY") or "").strip() or None


def _cluster_score(rows: list[dict[str, Any]]) -> float:
    return sum(_row_weight(row) for row in rows) + len(rows) * 10


def _weighted_center(rows: list[dict[str, Any]]) -> tuple[float, float]:
    total_weight = sum(_row_weight(row) for row in rows) or 1.0
    lat = sum(row["lat"] * _row_weight(row) for row in rows) / total_weight
    lon = sum(row["lon"] * _row_weight(row) for row in rows) / total_weight
    return round(lat, 4), round(lon, 4)


def _row_weight(row: dict[str, Any]) -> float:
    confidence = _confidence_score(row.get("confidence"))
    power = float(row.get("power") or 10.0)
    return confidence + min(power, 200.0) / 8


def _confidence_score(value: Any) -> float:
    if value is None:
        return 2.0
    text = str(value).strip().lower()
    if text.isdigit():
        return max(1.0, float(text) / 20.0)
    return {"high": 4.0, "nominal": 2.5, "low": 1.0}.get(text, 2.0)


def _demo_live_region_selection(message: str | None = None) -> dict[str, Any]:
    hotspots = _demo_hotspots("24h", message=message)
    hotspots["data"]["hotspots"] = [
        {"lat": -15.0596, "lon": 143.2559, "confidence": "high", "detected_at": "demo"},
        {"lat": -15.0781, "lon": 143.2373, "confidence": "high", "detected_at": "demo"},
        {"lat": -15.04, "lon": 143.2363, "confidence": "nominal", "detected_at": "demo"},
    ]
    region_context = {
        "selection_mode": "demo_auto_live_hotspot",
        "state": "QLD",
        "region_id": "live_qld_demo_cluster",
        "region_name": "Queensland live hotspot cluster",
        "center": [-15.0596, 143.2559],
        "radius_km": 40,
        "selected_at": "demo",
        "hotspot_count_24h": 3,
    }
    result = {
        "region_id": "live_qld_demo_cluster",
        "region_name": "Queensland live hotspot cluster",
        "aoi": Aoi(center=(-15.0596, 143.2559), radius_km=40),
        "hotspots": hotspots,
        "region_context": region_context,
    }
    return result


def _serialize_hotspot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "lat": row["lat"],
        "lon": row["lon"],
        "state": row.get("state"),
        "confidence": row.get("confidence", "unknown"),
        "detected_at": (
            row["detected_at"].isoformat()
            if isinstance(row.get("detected_at"), datetime)
            else "unknown"
        ),
        "power": row.get("power"),
        "satellite": row.get("satellite"),
        "sensor": row.get("sensor"),
    }


def _sample_rows_for_map(
    rows: list[dict[str, Any]],
    limit: int,
    *,
    cell_size: float,
) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return rows

    by_cell: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        key = (floor(row["lat"] / cell_size), floor(row["lon"] / cell_size))
        current = by_cell.get(key)
        if current is None or _row_sort_key(row) > _row_sort_key(current):
            by_cell[key] = row

    sampled_rows = sorted(by_cell.values(), key=_row_sort_key, reverse=True)
    if len(sampled_rows) <= limit:
        return sampled_rows

    step = max(1, ceil(len(sampled_rows) / limit))
    return sampled_rows[::step][:limit]


def _row_sort_key(row: dict[str, Any]) -> tuple[float, float]:
    detected_at = row.get("detected_at")
    timestamp = detected_at.timestamp() if isinstance(detected_at, datetime) else 0.0
    return (timestamp, _row_weight(row))


def _focus_center_for_state(rows: list[dict[str, Any]], state_code: str) -> tuple[float, float]:
    if not rows:
        return STATE_FOCUS_DEFAULTS[state_code]

    clusters: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    cell_size = 0.45
    for row in rows:
        key = (floor(row["lat"] / cell_size), floor(row["lon"] / cell_size))
        clusters[key].append(row)

    _, cluster_rows = max(clusters.items(), key=lambda item: _cluster_score(item[1]))
    return _weighted_center(cluster_rows)


def _normalize_state_code(value: Any) -> str | None:
    if not value:
        return None
    state_code = str(value).strip().upper()
    return state_code if state_code in STATE_LABELS else None


def _state_code_from_region_id(region_id: str) -> str | None:
    if not region_id.startswith("state_"):
        return None
    return _normalize_state_code(region_id.replace("state_", "", 1))


def _get_cached_australia_overview(include_stale: bool = False) -> dict | None:
    payload = _AUSTRALIA_OVERVIEW_CACHE.get("payload")
    expires_at = _AUSTRALIA_OVERVIEW_CACHE.get("expires_at")
    if not payload:
        return None
    if include_stale or (isinstance(expires_at, datetime) and expires_at > datetime.now(UTC)):
        return deepcopy(payload)
    return None


def _get_cached_australia_rows(include_stale: bool = False) -> list[dict[str, Any]] | None:
    rows = _AUSTRALIA_OVERVIEW_CACHE.get("rows")
    expires_at = _AUSTRALIA_OVERVIEW_CACHE.get("expires_at")
    if not rows:
        return None
    if include_stale or (isinstance(expires_at, datetime) and expires_at > datetime.now(UTC)):
        return deepcopy(rows)
    return None


def _store_cached_australia_overview(payload: dict, rows: list[dict[str, Any]]) -> None:
    _AUSTRALIA_OVERVIEW_CACHE["payload"] = deepcopy(payload)
    _AUSTRALIA_OVERVIEW_CACHE["rows"] = deepcopy(rows)
    _AUSTRALIA_OVERVIEW_CACHE["expires_at"] = datetime.now(UTC) + timedelta(seconds=OVERVIEW_CACHE_TTL_SECONDS)


def _get_or_load_australia_hotspot_rows() -> tuple[list[dict[str, Any]], str, str, bool]:
    cached_rows = _get_cached_australia_rows()
    cached_payload = _get_cached_australia_overview()
    if cached_rows and cached_payload:
        return (
            cached_rows,
            str(cached_payload.get("mode", "live")),
            str(cached_payload.get("source", "DEA Hotspots recent feed")),
            True,
        )

    if external_data_mode() == "demo":
        rows = _demo_australia_hotspot_rows()
        payload = _build_australia_hotspot_overview(
            rows,
            mode="demo",
            source="DEA Hotspots demo overview",
        )
        _store_cached_australia_overview(payload, rows)
        return rows, "demo", "DEA Hotspots demo overview", False

    rows = _fetch_australia_hotspot_rows()
    payload = _build_australia_hotspot_overview(
        rows,
        mode="live",
        source="DEA Hotspots recent feed",
    )
    _store_cached_australia_overview(payload, rows)
    return rows, "live", "DEA Hotspots recent feed", False


def _demo_australia_hotspot_rows() -> list[dict[str, Any]]:
    return [
        {
            "lat": -12.4513,
            "lon": 132.9192,
            "state": "NT",
            "confidence": "high",
            "detected_at": datetime.now(UTC) - timedelta(hours=2),
            "power": 26.0,
            "satellite": "DEA_DEMO",
            "sensor": "DEMO",
        },
        {
            "lat": -12.3487,
            "lon": 133.1021,
            "state": "NT",
            "confidence": "high",
            "detected_at": datetime.now(UTC) - timedelta(hours=3),
            "power": 21.0,
            "satellite": "DEA_DEMO",
            "sensor": "DEMO",
        },
        {
            "lat": -16.9179,
            "lon": 145.7746,
            "state": "QLD",
            "confidence": "nominal",
            "detected_at": datetime.now(UTC) - timedelta(hours=4),
            "power": 12.0,
            "satellite": "DEA_DEMO",
            "sensor": "DEMO",
        },
        {
            "lat": -31.9523,
            "lon": 115.8613,
            "state": "WA",
            "confidence": "low",
            "detected_at": datetime.now(UTC) - timedelta(hours=7),
            "power": 9.0,
            "satellite": "DEA_DEMO",
            "sensor": "DEMO",
        },
        {
            "lat": -37.8136,
            "lon": 144.9631,
            "state": "VIC",
            "confidence": "low",
            "detected_at": datetime.now(UTC) - timedelta(hours=9),
            "power": 8.0,
            "satellite": "DEA_DEMO",
            "sensor": "DEMO",
        },
    ]


def _demo_australia_hotspot_overview(message: str | None = None) -> dict:
    rows = _demo_australia_hotspot_rows()
    return _build_australia_hotspot_overview(
        rows,
        mode="demo",
        source="DEA Hotspots demo overview",
        message=message,
    )


def _demo_hotspots(time_window: str, message: str | None = None) -> dict:
    payload = {
        "status": "success",
        "mode": "demo",
        "source": "DEA Hotspots demo fallback",
        "data": {
            "time_window": time_window,
            "count_24h": 3,
            "count_7d": 8,
            "count_window_days": 7,
            "hotspots": [
                {"lat": -33.69, "lon": 150.28, "confidence": "high", "detected_at": "demo"},
                {"lat": -33.76, "lon": 150.35, "confidence": "nominal", "detected_at": "demo"},
                {"lat": -33.64, "lon": 150.41, "confidence": "nominal", "detected_at": "demo"},
            ],
        },
    }
    if message:
        payload["message"] = message
    return payload
