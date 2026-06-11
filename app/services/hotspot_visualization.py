from __future__ import annotations

import base64
import os
import tempfile
from datetime import UTC, datetime
from io import BytesIO
from math import exp
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "wildfire-ops-matplotlib"))

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from app.models.schemas import ChatRequest
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
    interpretation_text = _interpretation_text(interpretation)
    generated_at = datetime.now(UTC)
    artifact_stem = _artifact_stem(region["region_id"], radius_km, generated_at)
    preview = _preview_image(
        region["region_name"],
        radius_km,
        center,
        cluster["center"],
        cells,
        density,
        f"{artifact_stem}.png",
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
        "heatmap": {
            "cells": cells,
            "intensity_field": "density",
        },
        "contours": {
            "type": "FeatureCollection",
            "features": contours,
        },
        "preview": preview,
        "interpretation": interpretation,
        "ui": {
            "description": "Hotspot visualization output includes contour map figure and short AI interpretation.",
            "download_label": "Download AI interpretation + contour map",
        },
        "downloads": {
            "txt_filename": f"{artifact_stem}.txt",
            "txt_content": interpretation_text,
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
        {
            **cell,
            "normalized_intensity": round(float(cell["density"]) / float(max_density), 3),
        }
        for cell in sorted(buckets.values(), key=lambda item: item["density"], reverse=True)[:80]
    ]


def _hotspots_within_radius(
    hotspots: list[dict[str, Any]],
    center: tuple[float, float],
    radius_km: float,
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
    density: dict[str, Any],
) -> list[dict[str, Any]]:
    if not cells or not density["line_levels"]:
        return []
    bands = [
        ("Monitor", density["line_levels"][0], "#d97706"),
        ("Elevated", density["line_levels"][1], "#c2410c"),
        ("Priority 1", density["line_levels"][2], "#991b1b"),
    ]
    figure = Figure(figsize=(2, 2), dpi=80)
    axes = figure.add_subplot(1, 1, 1)
    contour_set = axes.contour(
        density["lons"],
        density["lats"],
        density["values"],
        levels=[band[1] for band in bands],
    )

    features: list[dict[str, Any]] = []
    for (label, threshold, color), segments in zip(bands, contour_set.allsegs, strict=False):
        ring = _largest_closed_ring(segments)
        if not ring:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "band": label,
                    "threshold": round(float(threshold), 4),
                    "color": color,
                    "radius_km": round(_ring_radius_km(center, ring), 1),
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [ring],
                },
            }
        )
    return list(reversed(features))


def _largest_closed_ring(segments: list[Any]) -> list[list[float]]:
    rings = []
    for segment in segments:
        ring = [[float(point[0]), float(point[1])] for point in segment]
        if len(ring) < 4:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        rings.append(ring)
    return max(rings, key=_ring_area, default=[])


def _ring_area(ring: list[list[float]]) -> float:
    area = 0.0
    for current, next_point in zip(ring, ring[1:], strict=False):
        area += current[0] * next_point[1] - next_point[0] * current[1]
    return abs(area) / 2.0


def _ring_radius_km(center: tuple[float, float], ring: list[list[float]]) -> float:
    distances = [haversine_km(center[0], center[1], lat, lon) for lon, lat in ring]
    return max(distances, default=0.0)


def _preview_image(
    region_name: str,
    radius_km: float,
    aoi_center: tuple[float, float],
    hotspot_center: tuple[float, float],
    cells: list[dict[str, Any]],
    density: dict[str, Any],
    filename: str,
) -> dict[str, Any]:
    width_px = 960
    height_px = 640
    figure = Figure(figsize=(width_px / 160, height_px / 160), dpi=160)
    canvas = FigureCanvasAgg(figure)
    axes = figure.add_subplot(1, 1, 1)
    axes.set_facecolor("#f8fafc")
    figure.subplots_adjust(left=0.08, right=0.88, bottom=0.09, top=0.92)

    if density["levels"]:
        contour_fill = axes.contourf(
            density["lons"],
            density["lats"],
            density["values"],
            levels=density["levels"],
            cmap="YlOrRd",
            alpha=0.82,
        )
        axes.contour(
            density["lons"],
            density["lats"],
            density["values"],
            levels=density["line_levels"],
            colors=["#d97706", "#c2410c", "#991b1b"],
            linewidths=1.5,
        )
        colorbar = figure.colorbar(contour_fill, ax=axes, fraction=0.038, pad=0.02)
        colorbar.set_label("KDE density", fontsize=8, color="#334155")
        colorbar.ax.tick_params(labelsize=7, colors="#475569")

    if cells:
        lats = [float(cell["lat"]) for cell in cells]
        lons = [float(cell["lon"]) for cell in cells]
        intensities = [float(cell.get("normalized_intensity") or 0) for cell in cells]
        sizes = [40 + intensity * 220 for intensity in intensities]
        axes.scatter(
            lons,
            lats,
            c=intensities,
            cmap="YlOrRd",
            edgecolors="#7f1d1d",
            linewidths=0.35,
            s=sizes,
            alpha=0.82,
            label="Hotspot density",
        )

    axes.scatter(
        [hotspot_center[1]],
        [hotspot_center[0]],
        marker="+",
        s=150,
        color="#0f172a",
        linewidths=1.8,
        label="Hotspot center (+)",
    )
    if aoi_center != hotspot_center:
        axes.scatter(
            [aoi_center[1]],
            [aoi_center[0]],
            marker="x",
            s=54,
            color="#334155",
            linewidths=1.3,
            label="AOI center (x)",
        )
    axes.set_title(f"{region_name} - {radius_km:g} km contour map", fontsize=10, color="#0f172a", pad=6)
    axes.set_xlabel("Longitude", fontsize=8, color="#475569")
    axes.set_ylabel("Latitude", fontsize=8, color="#475569")
    axes.tick_params(axis="both", labelsize=7, colors="#475569")
    axes.legend(loc="upper right", fontsize=7, framealpha=0.86)
    axes.set_aspect("equal", adjustable="box")
    _set_preview_bounds(axes, density["bounds"], width_px / height_px)
    axes.margins(0)
    figure.tight_layout(pad=1.1)

    buffer = BytesIO()
    canvas.print_png(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "format": "image/png",
        "encoding": "base64",
        "filename": filename,
        "data_url": f"data:image/png;base64,{encoded}",
        "width": width_px,
        "height": height_px,
        "alt": f"{region_name} matplotlib hotspot contour preview",
    }


def _density_grid(cells: list[dict[str, Any]], fallback_center: tuple[float, float]) -> dict[str, Any]:
    points = [
        (
            float(cell["lat"]),
            float(cell["lon"]),
            max(float(cell.get("density") or 1), 1.0),
        )
        for cell in cells
        if isinstance(cell.get("lat"), (int, float)) and isinstance(cell.get("lon"), (int, float))
    ]
    if not points:
        lat, lon = fallback_center
        return {
            "lons": [lon - 0.05, lon + 0.05],
            "lats": [lat - 0.05, lat + 0.05],
            "values": [[0.0, 0.0], [0.0, 0.0]],
            "levels": [],
            "line_levels": [],
            "bounds": (lon - 0.05, lat - 0.05, lon + 0.05, lat + 0.05),
        }

    lat_values = [point[0] for point in points]
    lon_values = [point[1] for point in points]
    lat_span = max(max(lat_values) - min(lat_values), 0.04)
    lon_span = max(max(lon_values) - min(lon_values), 0.04)
    sigma_lat = max(lat_span / 2.8, 0.025)
    sigma_lon = max(lon_span / 2.8, 0.025)
    south = min(lat_values) - sigma_lat * 3.0
    north = max(lat_values) + sigma_lat * 3.0
    west = min(lon_values) - sigma_lon * 3.0
    east = max(lon_values) + sigma_lon * 3.0
    lat_count = 72
    lon_count = 96
    lats = _linear_space(south, north, lat_count)
    lons = _linear_space(west, east, lon_count)
    values: list[list[float]] = []
    max_value = 0.0
    for lat in lats:
        row = []
        for lon in lons:
            value = sum(
                weight
                * exp(
                    -0.5
                    * (((lat - point_lat) / sigma_lat) ** 2 + ((lon - point_lon) / sigma_lon) ** 2)
                )
                for point_lat, point_lon, weight in points
            )
            max_value = max(max_value, value)
            row.append(value)
        values.append(row)

    outer_level = max_value * 0.08
    levels = [max_value * fraction for fraction in (0.08, 0.18, 0.34, 0.52, 0.72, 1.0)]
    line_levels = [max_value * fraction for fraction in (0.18, 0.34, 0.52)]
    return {
        "lons": lons,
        "lats": lats,
        "values": values,
        "levels": levels,
        "line_levels": line_levels,
        "bounds": _density_bounds(lons, lats, values, outer_level),
    }


def _linear_space(start: float, stop: float, count: int) -> list[float]:
    if count <= 1:
        return [start]
    step = (stop - start) / float(count - 1)
    return [start + step * index for index in range(count)]


def _density_bounds(
    lons: list[float],
    lats: list[float],
    values: list[list[float]],
    threshold: float,
) -> tuple[float, float, float, float]:
    active_lons = []
    active_lats = []
    for lat, row in zip(lats, values, strict=False):
        for lon, value in zip(lons, row, strict=False):
            if value >= threshold:
                active_lons.append(lon)
                active_lats.append(lat)
    if not active_lons or not active_lats:
        return min(lons), min(lats), max(lons), max(lats)

    lon_pad = max((max(lons) - min(lons)) / max(len(lons) - 1, 1), 0.005)
    lat_pad = max((max(lats) - min(lats)) / max(len(lats) - 1, 1), 0.005)
    return (
        min(active_lons) - lon_pad,
        min(active_lats) - lat_pad,
        max(active_lons) + lon_pad,
        max(active_lats) + lat_pad,
    )


def _set_preview_bounds(
    axes: Any,
    bounds: tuple[float, float, float, float],
    target_aspect: float,
) -> None:
    west, south, east, north = bounds
    width = max(east - west, 0.001)
    height = max(north - south, 0.001)
    current_aspect = width / height
    if current_aspect < target_aspect:
        extra = (height * target_aspect - width) / 2.0
        west -= extra
        east += extra
    elif current_aspect > target_aspect:
        extra = (width / target_aspect - height) / 2.0
        south -= extra
        north += extra
    axes.set_xlim(west, east)
    axes.set_ylim(south, north)


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


def _interpretation_text(interpretation: dict[str, Any]) -> str:
    lines = [
        f"Summary: {interpretation['summary']}",
        f"Priority: {interpretation['priority']}",
        "Cluster center: "
        f"{interpretation['cluster_center'][0]}, {interpretation['cluster_center'][1]}",
        f"Recommendation: {interpretation['recommendation']}",
        f"Caveat: {interpretation['caveat']}",
    ]
    return "\n".join(lines) + "\n"
