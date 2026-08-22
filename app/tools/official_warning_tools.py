from __future__ import annotations

import re
import threading
from datetime import UTC, datetime, timedelta
from html import unescape
from typing import Any

import httpx

from app.models.schemas import Aoi
from app.tools.provider_utils import (
    coerce_center,
    coerce_radius_km,
    external_data_mode,
    haversine_km,
    http_user_agent,
    request_timeout_seconds,
)

NSW_RFS_INCIDENTS_URL = "https://www.rfs.nsw.gov.au/feeds/majorIncidents.json"
NSW_RFS_DEFAULT_REFRESH_SECONDS = 30
WARNING_LEVELS = {
    "Emergency Warning": "EMERGENCY_WARNING",
    "Watch and Act": "WATCH_AND_ACT",
    "Advice": "ADVICE",
}
_NSW_RFS_CACHE: dict[str, Any] = {
    "payload": None,
    "last_checked_at": None,
    "last_refreshed_at": None,
    "next_refresh_at": None,
    "refresh_error": None,
    "refreshing": False,
}
_NSW_RFS_CACHE_LOCK = threading.Lock()


def get_official_fire_warnings(region_id: str, aoi: Aoi | dict | None = None) -> dict:
    if external_data_mode() == "demo":
        return _demo_official_warnings(region_id)
    if not _supports_nsw_warning_feed(region_id):
        return {
            "status": "success",
            "mode": "live",
            "source": "Australian warning coverage pending outside NSW",
            "data": {
                "region_id": region_id,
                "warning_level": None,
                "summary": "Official warning coverage is currently implemented with the NSW feed only.",
                "source_url": None,
                "issued_time": None,
                "changed_since_previous_run": False,
                "incident_count": 0,
                "incidents": [],
            },
        }

    try:
        return _fetch_nsw_rfs_warnings(region_id, aoi)
    except Exception as exc:
        return _demo_official_warnings(region_id, message=f"Official warning request failed: {exc}")


def _fetch_nsw_rfs_warnings(region_id: str, aoi: Aoi | dict | None) -> dict:
    payload = _get_cached_nsw_rfs_payload()
    if payload is None:
        raise RuntimeError("Live NSW RFS warning cache is not ready yet. Background ingestion has not completed.")
    return _format_nsw_rfs_warnings(region_id, aoi, payload)


def refresh_nsw_rfs_warning_cache(force: bool = False) -> dict[str, Any]:
    now = datetime.now(UTC)
    with _NSW_RFS_CACHE_LOCK:
        next_refresh_at = _NSW_RFS_CACHE.get("next_refresh_at")
        if (
            not force
            and isinstance(next_refresh_at, datetime)
            and next_refresh_at > now
            and _NSW_RFS_CACHE.get("payload") is not None
        ):
            return {"status": "skipped", "reason": "fresh"}
        if _NSW_RFS_CACHE.get("refreshing"):
            return {"status": "skipped", "reason": "refresh_in_progress"}
        _NSW_RFS_CACHE["refreshing"] = True

    try:
        response = httpx.get(
            NSW_RFS_INCIDENTS_URL,
            headers={"User-Agent": http_user_agent()},
            timeout=request_timeout_seconds(default=12.0),
        )
        response.raise_for_status()
        payload = response.json()
        max_age = _cache_control_max_age(response.headers.get("cache-control")) or NSW_RFS_DEFAULT_REFRESH_SECONDS
        now = datetime.now(UTC)
        with _NSW_RFS_CACHE_LOCK:
            _NSW_RFS_CACHE["payload"] = payload
            _NSW_RFS_CACHE["last_checked_at"] = now
            _NSW_RFS_CACHE["last_refreshed_at"] = now
            _NSW_RFS_CACHE["next_refresh_at"] = now + timedelta(seconds=max_age)
            _NSW_RFS_CACHE["refresh_error"] = None
            _NSW_RFS_CACHE["refreshing"] = False
        return {"status": "refreshed", "max_age_seconds": max_age}
    except Exception as exc:
        with _NSW_RFS_CACHE_LOCK:
            _NSW_RFS_CACHE["last_checked_at"] = datetime.now(UTC)
            _NSW_RFS_CACHE["next_refresh_at"] = datetime.now(UTC) + timedelta(seconds=NSW_RFS_DEFAULT_REFRESH_SECONDS)
            _NSW_RFS_CACHE["refresh_error"] = str(exc)
            _NSW_RFS_CACHE["refreshing"] = False
        raise


def seconds_until_nsw_rfs_refresh() -> float:
    with _NSW_RFS_CACHE_LOCK:
        next_refresh_at = _NSW_RFS_CACHE.get("next_refresh_at")
    if not isinstance(next_refresh_at, datetime):
        return 0.0
    return max(0.0, (next_refresh_at - datetime.now(UTC)).total_seconds())


def _get_cached_nsw_rfs_payload() -> dict[str, Any] | None:
    with _NSW_RFS_CACHE_LOCK:
        payload = _NSW_RFS_CACHE.get("payload")
    return payload


def _format_nsw_rfs_warnings(region_id: str, aoi: Aoi | dict | None, payload: dict[str, Any]) -> dict:
    relevant_incidents = _filter_relevant_incidents(payload.get("features", []), aoi)
    ranked = sorted(relevant_incidents, key=lambda incident: incident["severity_rank"], reverse=True)
    top_incident = ranked[0] if ranked else None
    latest_update = max((incident["updated_at"] for incident in ranked if incident["updated_at"]), default=None)

    if top_incident:
        summary = (
            f"{len(ranked)} NSW RFS incident(s) were found inside the monitored radius. "
            f"Highest alert level is {top_incident['alert_level_label']} at {top_incident['title']}."
        )
    else:
        summary = "No NSW RFS fire warnings were found inside the monitored radius."

    return {
        "status": "success",
        "mode": "live",
        "source": "NSW Rural Fire Service GeoJSON",
        "data": {
            "region_id": region_id,
            "warning_level": top_incident["warning_level"] if top_incident else None,
            "summary": summary,
            "source_url": NSW_RFS_INCIDENTS_URL,
            "issued_time": latest_update.isoformat() if latest_update else None,
            "changed_since_previous_run": bool(
                latest_update and latest_update >= datetime.now(UTC) - timedelta(days=1)
            ),
            "incident_count": len(ranked),
            "incidents": [
                {
                    "title": incident["title"],
                    "category": incident["category"],
                    "alert_level": incident["alert_level_label"],
                    "status": incident["status"],
                    "location": incident["location"],
                    "distance_km": incident["distance_km"],
                    "lat": incident["lat"],
                    "lon": incident["lon"],
                    "updated_at": incident["updated_at"].isoformat() if incident["updated_at"] else None,
                    "guid": incident["guid"],
                }
                for incident in ranked[:5]
            ],
        },
    }


def _cache_control_max_age(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(?:^|,)\s*max-age\s*=\s*(\d+)\s*(?:,|$)", value, flags=re.IGNORECASE)
    if not match:
        return None
    return max(1, int(match.group(1)))


def _filter_relevant_incidents(features: list[dict[str, Any]], aoi: Aoi | dict | None) -> list[dict[str, Any]]:
    center_lat, center_lon = coerce_center(aoi or Aoi())
    radius_km = coerce_radius_km(aoi or Aoi())
    incidents: list[dict[str, Any]] = []
    for feature in features:
        coordinates = _extract_point_coordinates(feature.get("geometry"))
        if not coordinates:
            continue
        lon, lat = coordinates
        distance_km = haversine_km(center_lat, center_lon, lat, lon)
        if distance_km > radius_km:
            continue
        properties = feature.get("properties", {})
        details = _parse_description(properties.get("description", ""))
        is_fire = details.get("FIRE", "").upper() == "YES"
        category = str(properties.get("category", "Not Applicable"))
        if not is_fire and category not in {"Emergency Warning", "Watch and Act", "Advice", "Planned Burn"}:
            continue
        alert_level_label = details.get("ALERT LEVEL", category)
        warning_level = WARNING_LEVELS.get(alert_level_label) or WARNING_LEVELS.get(category)
        incidents.append(
            {
                "title": str(properties.get("title", "Unknown incident")),
                "category": category,
                "alert_level_label": alert_level_label,
                "warning_level": warning_level,
                "severity_rank": _severity_rank(alert_level_label or category),
                "status": details.get("STATUS", "Unknown"),
                "location": details.get("LOCATION", "Unknown"),
                "distance_km": round(distance_km, 1),
                "lat": lat,
                "lon": lon,
                "updated_at": (
                    _parse_nsw_datetime(details.get("UPDATED"))
                    or _parse_nsw_datetime(properties.get("pubDate"))
                ),
                "guid": properties.get("guid"),
            }
        )
    return incidents


def _extract_point_coordinates(geometry: dict[str, Any] | None) -> tuple[float, float] | None:
    if not geometry:
        return None
    geometry_type = geometry.get("type")
    if geometry_type == "Point":
        coordinates = geometry.get("coordinates", [])
        if len(coordinates) == 2:
            return float(coordinates[0]), float(coordinates[1])
        return None
    if geometry_type == "GeometryCollection":
        for item in geometry.get("geometries", []):
            point = _extract_point_coordinates(item)
            if point:
                return point
    return None


def _parse_description(description: str) -> dict[str, str]:
    details: dict[str, str] = {}
    for chunk in unescape(description).split("<br />"):
        cleaned = " ".join(chunk.split()).strip()
        if ":" not in cleaned:
            continue
        key, value = cleaned.split(":", 1)
        details[key.strip().upper()] = value.strip()
    return details


def _parse_nsw_datetime(raw_value: Any) -> datetime | None:
    if not raw_value:
        return None
    value = str(raw_value).strip()
    for fmt in ("%d/%m/%Y %I:%M:%S %p", "%d %B %Y %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _severity_rank(value: str) -> int:
    return {"Emergency Warning": 3, "Watch and Act": 2, "Advice": 1}.get(value, 0)


def _supports_nsw_warning_feed(region_id: str) -> bool:
    normalized = region_id.lower()
    return "nsw" in normalized or "blue_mountains" in normalized or "oberon" in normalized


def _demo_official_warnings(region_id: str, message: str | None = None) -> dict:
    payload = {
        "status": "success",
        "mode": "demo",
        "source": "Official warnings demo fallback",
        "data": {
            "region_id": region_id,
            "warning_level": "ADVICE",
            "summary": "Elevated fire danger conditions; stay informed through official channels.",
            "source_url": None,
            "issued_time": "demo",
            "changed_since_previous_run": True,
        },
    }
    if message:
        payload["message"] = message
    return payload
