"""Pure clustering/centroid/sampling math over hotspot rows. No I/O."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import ceil, floor
from typing import Any

from app.tools.fire_hotspot_tools.constants import STATE_FOCUS_DEFAULTS


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
