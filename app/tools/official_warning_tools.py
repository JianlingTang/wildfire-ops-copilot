from __future__ import annotations

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
WARNING_LEVELS = {
    "Emergency Warning": "EMERGENCY_WARNING",
    "Watch and Act": "WATCH_AND_ACT",
    "Advice": "ADVICE",
}


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
    response = httpx.get(
        NSW_RFS_INCIDENTS_URL,
        headers={"User-Agent": http_user_agent()},
        timeout=request_timeout_seconds(default=12.0),
    )
    response.raise_for_status()
    payload = response.json()
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
