from __future__ import annotations

from datetime import UTC, datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from app.models.schemas import Aoi
from app.tools.provider_utils import (
    coerce_center,
    coerce_radius_km,
    external_data_mode,
    http_user_agent,
    request_timeout_seconds,
)

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"


def get_spatial_exposure_summary(aoi: Aoi | dict) -> dict:
    validation = _validate_aoi(aoi)
    if validation["status"] == "error":
        return validation
    if external_data_mode() == "demo":
        return {"status": "error", "message": "Spatial provider is configured for demo mode; live data is required."}

    try:
        return _fetch_live_spatial_summary(aoi)
    except Exception as exc:
        return {"status": "error", "message": f"Spatial exposure request failed: {exc}"}


def _validate_aoi(aoi: Aoi | dict) -> dict:
    if isinstance(aoi, dict) and aoi.get("simulate_failure"):
        return {"status": "error", "message": "Spatial provider failure simulated."}
    radius = aoi.get("radius_km") if isinstance(aoi, dict) else aoi.radius_km
    if radius is None or radius <= 0:
        return {"status": "error", "message": "AOI radius_km must be positive."}
    return {"status": "success"}


def _fetch_live_spatial_summary(aoi: Aoi | dict) -> dict:
    latitude, longitude = coerce_center(aoi)
    query_radius_km = coerce_radius_km(aoi)
    viewbox = _viewbox(latitude, longitude, query_radius_km)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            ("critical_assets", term): executor.submit(_search_nominatim, term, viewbox)
            for term in ["hospital", "school", "fire station", "police", "substation"]
        }
        protected_future = executor.submit(_fetch_protected_areas, latitude, longitude, query_radius_km)
        results = {(group, term): future.result() for (group, term), future in futures.items()}
        protected_areas = protected_future.result()

    assets = _unique_names(
        item
        for (group, _term), items in results.items()
        if group == "critical_assets"
        for item in items
    )
    summary = (
        f"{len(assets)} critical assets and {len(protected_areas)} parks or protected natural areas "
        "fall inside the monitored radius."
    )
    return {
        "status": "success",
        "mode": "live",
        "source": "OpenStreetMap Nominatim + Overpass APIs",
        "summary": summary,
        "fetched_at": datetime.now(UTC).isoformat(),
        "data": {
            "query_radius_km": query_radius_km,
            "critical_asset_count": len(assets),
            "critical_assets": assets[:10],
            "protected_area_count": len(protected_areas),
            "protected_areas": protected_areas[:10],
            "exposure_notes": summary,
        },
    }


def _viewbox(latitude: float, longitude: float, radius_km: float) -> str:
    lat_delta = radius_km / 110.574
    lon_delta = radius_km / 111.320
    return f"{longitude - lon_delta},{latitude + lat_delta},{longitude + lon_delta},{latitude - lat_delta}"


def _search_nominatim(term: str, viewbox: str) -> list[str]:
    response = httpx.get(
        NOMINATIM_SEARCH_URL,
        params={"q": term, "format": "jsonv2", "limit": 3, "bounded": 1, "viewbox": viewbox},
        headers={"User-Agent": http_user_agent()},
        timeout=request_timeout_seconds(default=4.0),
    )
    response.raise_for_status()
    return [str(item.get("display_name") or item.get("name") or term) for item in response.json()[:3]]


def _fetch_protected_areas(latitude: float, longitude: float, radius_km: float) -> list[str]:
    lat_delta = radius_km / 110.574
    lon_delta = radius_km / 111.320
    south, west, north, east = latitude - lat_delta, longitude - lon_delta, latitude + lat_delta, longitude + lon_delta
    query = f"""
    [out:json][timeout:8];
    (
      way["boundary"="protected_area"]({south},{west},{north},{east});
      relation["boundary"="protected_area"]({south},{west},{north},{east});
      way["leisure"~"park|nature_reserve"]({south},{west},{north},{east});
      relation["leisure"~"park|nature_reserve"]({south},{west},{north},{east});
      way["protect_class"]({south},{west},{north},{east});
      relation["protect_class"]({south},{west},{north},{east});
    );
    out tags qt 50;
    """.strip()
    response = httpx.post(
        OVERPASS_API_URL,
        content=query,
        headers={"User-Agent": http_user_agent(), "Content-Type": "text/plain"},
        timeout=request_timeout_seconds(default=10.0),
    )
    response.raise_for_status()
    return _unique_names(
        tags.get("name") or tags.get("operator") or tags.get("leisure") or tags.get("boundary")
        for element in response.json().get("elements", [])
        for tags in [element.get("tags", {})]
    )


def _unique_names(values: Any) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        names.append(str(value))
    return names


def build_spatial_fallback_summary(message: str | None = None) -> dict:
    payload = {
        "status": "success",
        "mode": "demo",
        "source": "Seeded GeoJSON demo fallback",
        "summary": "Critical assets and protected natural areas fall inside the monitored radius.",
        "data": {
            "critical_asset_count": 4,
            "critical_assets": ["Katoomba Hospital", "Blackheath Fire Station"],
            "protected_area_count": 2,
            "protected_areas": ["Blue Mountains National Park", "Megalong Reserve"],
            "exposure_notes": "Critical assets and protected natural areas fall inside the monitored radius.",
        },
    }
    if message:
        payload["message"] = message
    return payload
