"""Static/demo hotspot data used when WILDFIRE_DATA_MODE=demo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.schemas import Aoi
from app.tools.fire_hotspot_tools.format import _build_australia_hotspot_overview


def _demo_australia_hotspot_rows() -> list[dict[str, Any]]:
    return [
        {
            "lat": -12.4513,
            "lon": 132.9192,
            "state": "NT",
            "confidence": "high",
            "detected_at": datetime.now(UTC) - timedelta(hours=2),
            "power": 26.0,
            "satellite": "DEA_DEMO",
            "sensor": "DEMO",
        },
        {
            "lat": -12.3487,
            "lon": 133.1021,
            "state": "NT",
            "confidence": "high",
            "detected_at": datetime.now(UTC) - timedelta(hours=3),
            "power": 21.0,
            "satellite": "DEA_DEMO",
            "sensor": "DEMO",
        },
        {
            "lat": -16.9179,
            "lon": 145.7746,
            "state": "QLD",
            "confidence": "nominal",
            "detected_at": datetime.now(UTC) - timedelta(hours=4),
            "power": 12.0,
            "satellite": "DEA_DEMO",
            "sensor": "DEMO",
        },
        {
            "lat": -31.9523,
            "lon": 115.8613,
            "state": "WA",
            "confidence": "low",
            "detected_at": datetime.now(UTC) - timedelta(hours=7),
            "power": 9.0,
            "satellite": "DEA_DEMO",
            "sensor": "DEMO",
        },
        {
            "lat": -37.8136,
            "lon": 144.9631,
            "state": "VIC",
            "confidence": "low",
            "detected_at": datetime.now(UTC) - timedelta(hours=9),
            "power": 8.0,
            "satellite": "DEA_DEMO",
            "sensor": "DEMO",
        },
    ]


def _demo_australia_hotspot_overview(message: str | None = None) -> dict:
    rows = _demo_australia_hotspot_rows()
    return _build_australia_hotspot_overview(
        rows,
        mode="demo",
        source="DEA Hotspots demo overview",
        message=message,
    )


def _demo_hotspots(time_window: str, message: str | None = None) -> dict:
    payload = {
        "status": "success",
        "mode": "demo",
        "source": "DEA Hotspots demo fallback",
        "data": {
            "time_window": time_window,
            "count_24h": 3,
            "count_7d": 8,
            "count_window_days": 7,
            "hotspots": [
                {"lat": -33.69, "lon": 150.28, "confidence": "high", "detected_at": "demo"},
                {"lat": -33.76, "lon": 150.35, "confidence": "nominal", "detected_at": "demo"},
                {"lat": -33.64, "lon": 150.41, "confidence": "nominal", "detected_at": "demo"},
            ],
        },
    }
    if message:
        payload["message"] = message
    return payload


def _demo_live_region_selection(message: str | None = None) -> dict[str, Any]:
    hotspots = _demo_hotspots("24h", message=message)
    hotspots["data"]["hotspots"] = [
        {"lat": -15.0596, "lon": 143.2559, "confidence": "high", "detected_at": "demo"},
        {"lat": -15.0781, "lon": 143.2373, "confidence": "high", "detected_at": "demo"},
        {"lat": -15.04, "lon": 143.2363, "confidence": "nominal", "detected_at": "demo"},
    ]
    region_context = {
        "selection_mode": "demo_auto_live_hotspot",
        "state": "QLD",
        "region_id": "live_qld_demo_cluster",
        "region_name": "Queensland live hotspot cluster",
        "center": [-15.0596, 143.2559],
        "radius_km": 40,
        "selected_at": "demo",
        "hotspot_count_24h": 3,
    }
    return {
        "region_id": "live_qld_demo_cluster",
        "region_name": "Queensland live hotspot cluster",
        "aoi": Aoi(center=(-15.0596, 143.2559), radius_km=40),
        "hotspots": hotspots,
        "region_context": region_context,
    }
