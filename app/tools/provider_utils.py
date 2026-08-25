from __future__ import annotations

import os
from math import asin, cos, radians, sin, sqrt

from app.models.schemas import Aoi


def external_data_mode() -> str:
    mode = os.getenv("WILDFIRE_DATA_MODE", "auto").strip().lower()
    return mode if mode in {"auto", "demo", "live"} else "auto"


def request_timeout_seconds(default: float = 8.0) -> float:
    raw = os.getenv("EXTERNAL_API_TIMEOUT_SECONDS", str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def http_user_agent() -> str:
    return os.getenv("EXTERNAL_API_USER_AGENT", "wildfire-ops-copilot/0.1")


def coerce_center(aoi: Aoi | dict) -> tuple[float, float]:
    center = aoi.get("center") if isinstance(aoi, dict) else aoi.center
    if center and len(center) == 2:
        return float(center[0]), float(center[1])

    bbox = aoi.get("bbox") if isinstance(aoi, dict) else aoi.bbox
    if bbox and len(bbox) == 4:
        west, south, east, north = (float(value) for value in bbox)
        return (south + north) / 2, (west + east) / 2

    return -33.71, 150.31


def coerce_radius_km(aoi: Aoi | dict) -> float:
    radius = aoi.get("radius_km") if isinstance(aoi, dict) else aoi.radius_km
    return float(radius if radius is not None else 30)


def haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    earth_radius_km = 6371.0
    lat1 = radians(lat_a)
    lat2 = radians(lat_b)
    delta_lat = radians(lat_b - lat_a)
    delta_lon = radians(lon_b - lon_a)
    hav = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(hav))
