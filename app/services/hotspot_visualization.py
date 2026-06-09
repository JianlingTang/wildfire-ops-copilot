from __future__ import annotations

from datetime import UTC, datetime
from math import cos, pi, sin
from typing import Any

from app.models.schemas import ChatRequest
from app.tools.fire_hotspot_tools import get_fire_hotspots, resolve_operational_region


def build_hotspot_visualization(request: ChatRequest) -> dict[str, Any]:
    region = resolve_operational_region(
        request.region_id,
        request.region_name or request.region_id.replace("_", " ").title(),
        request.aoi,
        respect_explicit_aoi=bool(request.aoi and request.aoi.center),
    )
    hotspot_payload = region.get("hotspots") or get_fire_hotspots(region["aoi"])
    hotspots = hotspot_payload.get("data", {}).get("hotspots", [])
    center = _center_from_region(region)
    radius_km = float(region["region_context"].get("radius_km") or region["aoi"].radius_km)
    cells = _heatmap_cells(hotspots)
    cluster = _dominant_cluster(hotspots, center)
    contours = _contour_features(cluster["center"], radius_km, cells)
    interpretation = _interpretation(region["region_name"], hotspots, cluster, radius_km)

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
        "generated_at": datetime.now(UTC).isoformat(),
        "hotspot_count": len(hotspots),
        "heatmap": {
            "cells": cells,
            "intensity_field": "density",
        },
        "contours": {
            "type": "FeatureCollection",
            "features": contours,
        },
        "interpretation": interpretation,
        "downloads": {
            "json_filename": "hotspot-visualization.json",
            "csv_filename": "hotspot-visualization.csv",
        },
    }


def _center_from_region(region: dict[str, Any]) -> tuple[float, float]:
    center = region.get("region_context", {}).get("center") or region["aoi"].center
    if center and len(center) == 2:
        return float(center[0]), float(center[1])
    return -25.0, 134.0


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
        {
            **cell,
            "normalized_intensity": round(float(cell["density"]) / float(max_density), 3),
        }
        for cell in sorted(buckets.values(), key=lambda item: item["density"], reverse=True)[:80]
    ]


def _dominant_cluster(hotspots: list[dict[str, Any]], fallback_center: tuple[float, float]) -> dict[str, Any]:
    if not hotspots:
        return {"center": fallback_center, "count": 0, "max_power": 0}
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


def _contour_features(
    center: tuple[float, float],
    radius_km: float,
    cells: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    max_density = max((cell["density"] for cell in cells), default=0)
    bands = [
        ("Priority 1", 0.32, "#991b1b", max_density),
        ("Elevated", 0.58, "#c2410c", max(1, round(max_density * 0.55))),
        ("Monitor", 0.86, "#d97706", max(1, round(max_density * 0.25))),
    ]
    return [
        {
            "type": "Feature",
            "properties": {
                "band": label,
                "threshold": threshold,
                "color": color,
                "radius_km": round(radius_km * scale, 1),
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [_circle_polygon(center, radius_km * scale)],
            },
        }
        for label, scale, color, threshold in bands
    ]


def _circle_polygon(center: tuple[float, float], radius_km: float) -> list[list[float]]:
    lat, lon = center
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / max(20.0, 111.0 * cos(lat * pi / 180.0))
    points = []
    for index in range(49):
        angle = 2 * pi * index / 48
        points.append([lon + lon_delta * cos(angle), lat + lat_delta * sin(angle)])
    return points


def _interpretation(
    region_name: str,
    hotspots: list[dict[str, Any]],
    cluster: dict[str, Any],
    radius_km: float,
) -> dict[str, Any]:
    count = len(hotspots)
    if count == 0:
        summary = f"{region_name} has no rendered hotspot detections inside the selected AOI."
        recommendation = "Keep the AOI watch active and rerun visualization when new detections arrive."
    else:
        summary = (
            f"{region_name} contains a dominant hotspot concentration with {count} rendered detections "
            f"inside the {radius_km:g} km AOI."
        )
        recommendation = (
            "Inspect the Priority 1 contour first, then check downwind access routes and exposed settlement edges."
        )
    return {
        "summary": summary,
        "cluster_center": [round(cluster["center"][0], 5), round(cluster["center"][1], 5)],
        "priority": "Priority 1 contour" if count else "Monitor",
        "recommendation": recommendation,
        "caveat": "Satellite hotspots indicate thermal anomalies, not confirmed fire perimeter or fire size.",
    }
