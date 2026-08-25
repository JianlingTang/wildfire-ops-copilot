"""KDE density grid math for the hotspot heatmap/contour visualization."""

from __future__ import annotations

from math import exp
from typing import Any


def _density_grid(cells: list[dict[str, Any]], fallback_center: tuple[float, float]) -> dict[str, Any]:
    points = [
        (float(cell["lat"]), float(cell["lon"]), max(float(cell.get("density") or 1), 1.0))
        for cell in cells
        if isinstance(cell.get("lat"), (int, float)) and isinstance(cell.get("lon"), (int, float))
    ]
    if not points:
        return _empty_density_grid(fallback_center)
    return _density_grid_from_points(points)


def _empty_density_grid(fallback_center: tuple[float, float]) -> dict[str, Any]:
    lat, lon = fallback_center
    return {
        "lons": [lon - 0.05, lon + 0.05],
        "lats": [lat - 0.05, lat + 0.05],
        "values": [[0.0, 0.0], [0.0, 0.0]],
        "levels": [],
        "line_levels": [],
        "bounds": (lon - 0.05, lat - 0.05, lon + 0.05, lat + 0.05),
    }


def _density_grid_from_points(points: list[tuple[float, float, float]]) -> dict[str, Any]:
    lats, lons, sigma_lat, sigma_lon = _grid_axes(points)
    values, max_value = _kde_values(lats, lons, points, sigma_lat, sigma_lon)
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


def _grid_axes(points: list[tuple[float, float, float]]) -> tuple[list[float], list[float], float, float]:
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
    lats = _linear_space(south, north, 72)
    lons = _linear_space(west, east, 96)
    return lats, lons, sigma_lat, sigma_lon


def _kde_values(
    lats: list[float],
    lons: list[float],
    points: list[tuple[float, float, float]],
    sigma_lat: float,
    sigma_lon: float,
) -> tuple[list[list[float]], float]:
    values: list[list[float]] = []
    max_value = 0.0
    for lat in lats:
        row = []
        for lon in lons:
            value = sum(
                weight * exp(-0.5 * (((lat - point_lat) / sigma_lat) ** 2 + ((lon - point_lon) / sigma_lon) ** 2))
                for point_lat, point_lon, weight in points
            )
            max_value = max(max_value, value)
            row.append(value)
        values.append(row)
    return values, max_value


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
