"""Orchestrates the hotspot visualization: resolves the AOI, assembles heatmap
cells and the dominant cluster, then delegates to contour/density/render/
interpretation for the rest of the payload."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.schemas import ChatRequest
from app.services.hotspot_visualization.contour import _contour_features
from app.services.hotspot_visualization.density import _density_grid
from app.services.hotspot_visualization.interpretation import _interpretation, _interpretation_text
from app.services.hotspot_visualization.render import _preview_image
from app.tools.fire_hotspot_tools import get_fire_hotspots, resolve_operational_region
from app.tools.provider_utils import haversine_km


def build_hotspot_visualization(request: ChatRequest) -> dict[str, Any]:
    region = resolve_operational_region(
        request.region_id,
        request.region_name or request.region_id.replace("_", " ").title(),
        request.aoi,
        respect_explicit_aoi=bool(request.aoi and request.aoi.center),
    )
    hotspot_payload = region.get("hotspots") or get_fire_hotspots(region["aoi"])
    center = _center_from_region(region)
    radius_km = float(region["region_context"].get("radius_km") or region["aoi"].radius_km)
    hotspots = _hotspots_within_radius(hotspot_payload.get("data", {}).get("hotspots", []), center, radius_km)
    cells = _heatmap_cells(hotspots)
    cluster = _dominant_cluster(hotspots, center)
    density = _density_grid(cells, cluster["center"])
    contours = _contour_features(cluster["center"], radius_km, cells, density)
    interpretation = _interpretation(region["region_name"], hotspots, cluster, radius_km)
    generated_at = datetime.now(UTC)
    artifact_stem = _artifact_stem(region["region_id"], radius_km, generated_at)
    preview = _preview_image(
        region["region_name"], radius_km, center, cluster["center"], cells, density, f"{artifact_stem}.png"
    )

    return {
        "status": "success",
        "mode": hotspot_payload.get("mode", "live"),
        "region": {
            "region_id": region["region_id"],
            "region_name": region["region_name"],
            "center": list(center),
            "radius_km": radius_km,
        },
        "source": hotspot_payload.get("source", "Hotspot feed"),
        "generated_at": generated_at.isoformat(),
        "hotspot_count": len(hotspots),
        "heatmap": {"cells": cells, "intensity_field": "density"},
        "contours": {"type": "FeatureCollection", "features": contours},
        "preview": preview,
        "interpretation": interpretation,
        "ui": {
            "description": "Hotspot visualization output includes contour map figure and short AI interpretation.",
            "download_label": "Download AI interpretation + contour map",
        },
        "downloads": {
            "txt_filename": f"{artifact_stem}.txt",
            "txt_content": _interpretation_text(interpretation),
            "png_filename": f"{artifact_stem}.png",
        },
    }


def _center_from_region(region: dict[str, Any]) -> tuple[float, float]:
    center = region.get("region_context", {}).get("center") or region["aoi"].center
    if center and len(center) == 2:
        return float(center[0]), float(center[1])
    return -25.0, 134.0


def _artifact_stem(region_id: str, radius_km: float, generated_at: datetime) -> str:
    safe_region = "".join(char if char.isalnum() else "_" for char in region_id.lower()).strip("_")
    radius_label = f"{radius_km:g}km".replace(".", "_")
    request_id = generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    return f"{safe_region}_{radius_label}_{request_id}"


def _heatmap_cells(hotspots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[float, float], dict[str, Any]] = {}
    for hotspot in hotspots:
        lat = hotspot.get("lat")
        lon = hotspot.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        key = (round(float(lat), 2), round(float(lon), 2))
        power = hotspot.get("power") if isinstance(hotspot.get("power"), (int, float)) else 1
        bucket = buckets.setdefault(
            key,
            {
                "lat": key[0],
                "lon": key[1],
                "density": 0,
                "max_power": 0,
                "latest_detection": hotspot.get("detected_at", "unknown"),
            },
        )
        bucket["density"] += 1
        bucket["max_power"] = max(float(bucket["max_power"]), float(power or 0))
    max_density = max((cell["density"] for cell in buckets.values()), default=1)
    return [
        {**cell, "normalized_intensity": round(float(cell["density"]) / float(max_density), 3)}
        for cell in sorted(buckets.values(), key=lambda item: item["density"], reverse=True)[:80]
    ]


def _hotspots_within_radius(
    hotspots: list[dict[str, Any]], center: tuple[float, float], radius_km: float
) -> list[dict[str, Any]]:
    filtered = []
    for hotspot in hotspots:
        lat = hotspot.get("lat")
        lon = hotspot.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        if haversine_km(center[0], center[1], float(lat), float(lon)) <= radius_km:
            filtered.append(hotspot)
    return filtered


def _dominant_cluster(hotspots: list[dict[str, Any]], fallback_center: tuple[float, float]) -> dict[str, Any]:
    rows = [
        hotspot
        for hotspot in hotspots
        if isinstance(hotspot.get("lat"), (int, float)) and isinstance(hotspot.get("lon"), (int, float))
    ]
    if not rows:
        return {"center": fallback_center, "count": 0, "max_power": 0}
    weights = [max(float(row.get("power") or 1), 1.0) for row in rows]
    total_weight = sum(weights)
    center_lat = sum(float(row["lat"]) * weight for row, weight in zip(rows, weights, strict=False)) / total_weight
    center_lon = sum(float(row["lon"]) * weight for row, weight in zip(rows, weights, strict=False)) / total_weight
    return {
        "center": (center_lat, center_lon),
        "count": len(rows),
        "max_power": max(float(row.get("power") or 0) for row in rows),
    }
