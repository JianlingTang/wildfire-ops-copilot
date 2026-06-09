from __future__ import annotations

from datetime import UTC, datetime
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

OVERPASS_API_URL = "https://overpass.kumi.systems/api/interpreter"


def get_spatial_exposure_summary(aoi: Aoi | dict) -> dict:
    validation = _validate_aoi(aoi)
    if validation["status"] == "error":
        return validation
    if external_data_mode() == "demo":
        return build_spatial_fallback_summary()

    try:
        return _fetch_live_spatial_summary(aoi)
    except Exception as exc:
        return build_spatial_fallback_summary(message=f"Spatial exposure request failed: {exc}")


def _validate_aoi(aoi: Aoi | dict) -> dict:
    if isinstance(aoi, dict) and aoi.get("simulate_failure"):
        return {"status": "error", "message": "Spatial provider failure simulated."}
    radius = aoi.get("radius_km") if isinstance(aoi, dict) else aoi.radius_km
    if radius is None or radius <= 0:
        return {"status": "error", "message": "AOI radius_km must be positive."}
    return {"status": "success"}


def _fetch_live_spatial_summary(aoi: Aoi | dict) -> dict:
    latitude, longitude = coerce_center(aoi)
    radius_m = int(coerce_radius_km(aoi) * 1000)
    query = f"""
    [out:json][timeout:25];
    (
      node["place"~"city|town|village|suburb"](around:{radius_m},{latitude},{longitude});
      way["highway"]["name"](around:{radius_m},{latitude},{longitude});
      node["amenity"~"hospital|school|fire_station|police"](around:{radius_m},{latitude},{longitude});
      way["amenity"~"hospital|school|fire_station|police"](around:{radius_m},{latitude},{longitude});
      node["power"="substation"](around:{radius_m},{latitude},{longitude});
      way["power"="substation"](around:{radius_m},{latitude},{longitude});
    );
    out center tags qt;
    """.strip()
    response = httpx.post(
        OVERPASS_API_URL,
        content=query,
        headers={"User-Agent": http_user_agent(), "Content-Type": "text/plain"},
        timeout=request_timeout_seconds(default=6.0),
    )
    response.raise_for_status()
    elements = response.json().get("elements", [])

    towns = _collect_named_tags(
        elements,
        predicate=lambda tags: tags.get("place") in {"city", "town", "village", "suburb"},
    )
    roads = _collect_named_tags(elements, predicate=lambda tags: "highway" in tags)
    assets = _collect_assets(elements)
    summary = (
        f"{len(towns)} towns, {len(roads)} named roads, and {len(assets)} critical assets "
        "fall inside the monitored radius."
    )
    return {
        "status": "success",
        "mode": "live",
        "source": "OpenStreetMap Overpass API",
        "summary": summary,
        "fetched_at": datetime.now(UTC).isoformat(),
        "data": {
            "nearby_towns": towns[:5],
            "roads": roads[:5],
            "critical_asset_count": len(assets),
            "critical_assets": assets[:10],
            "exposure_notes": summary,
        },
    }


def _collect_named_tags(elements: list[dict[str, Any]], predicate: Any) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name")
        if not name or not predicate(tags):
            continue
        if name in seen:
            continue
        seen.add(name)
        values.append(str(name))
    return values


def _collect_assets(elements: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    assets: list[str] = []
    for element in elements:
        tags = element.get("tags", {})
        if not (
            tags.get("amenity") in {"hospital", "school", "fire_station", "police"}
            or tags.get("power") == "substation"
        ):
            continue
        label = str(tags.get("name") or tags.get("amenity") or tags.get("power"))
        if label in seen:
            continue
        seen.add(label)
        assets.append(label)
    return assets


def build_spatial_fallback_summary(message: str | None = None) -> dict:
    payload = {
        "status": "success",
        "mode": "demo",
        "source": "Seeded GeoJSON demo fallback",
        "summary": "Several towns and a major road corridor fall inside the monitored radius.",
        "data": {
            "nearby_towns": ["Katoomba", "Blackheath", "Wentworth Falls"],
            "roads": ["Great Western Highway"],
            "critical_asset_count": 4,
            "exposure_notes": "Several towns and a major road corridor fall inside the monitored radius.",
        },
    }
    if message:
        payload["message"] = message
    return payload
