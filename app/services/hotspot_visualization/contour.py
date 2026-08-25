"""Matplotlib contour-band GeoJSON generation for the hotspot visualization."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure

from app.tools.provider_utils import haversine_km


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
                "geometry": {"type": "Polygon", "coordinates": [ring]},
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
