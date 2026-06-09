from typing import Any


def compute_wildfire_risk_score(evidence: dict[str, Any]) -> dict:
    weather = evidence.get("weather", {}).get("data", {})
    hotspots = evidence.get("hotspots", {}).get("data", {})
    warnings = evidence.get("official_warnings", {}).get("data", {})
    spatial = evidence.get("spatial", {}).get("data", {})

    drivers: list[dict[str, int | str]] = []

    wind = int(weather.get("wind_gust_max", 0))
    wind_points = min(28, max(0, wind - 25))
    if wind_points:
        drivers.append({"factor": "wind_gust", "contribution": wind_points})

    humidity = int(weather.get("humidity_min", 100))
    humidity_points = min(24, max(0, 35 - humidity))
    if humidity_points:
        drivers.append({"factor": "low_humidity", "contribution": humidity_points})

    rainfall_points = 0
    if "rainfall_7d" in weather:
        rainfall = float(weather["rainfall_7d"])
        rainfall_points = 16 if rainfall < 2 else 8 if rainfall < 8 else 0
    if rainfall_points:
        drivers.append({"factor": "low_rainfall", "contribution": rainfall_points})

    hotspot_count = int(hotspots.get("count_24h", 0))
    hotspot_points = min(22, hotspot_count * 7)
    if hotspot_points:
        drivers.append({"factor": "recent_hotspots", "contribution": hotspot_points})

    warning_level = warnings.get("warning_level")
    warning_points = {"ADVICE": 5, "WATCH_AND_ACT": 14, "EMERGENCY_WARNING": 24}.get(warning_level, 0)
    if warning_points:
        drivers.append({"factor": "official_warning", "contribution": warning_points})

    exposed_assets = int(spatial.get("critical_asset_count", 0))
    exposure_points = min(10, exposed_assets * 2)
    if exposure_points:
        drivers.append({"factor": "spatial_exposure", "contribution": exposure_points})

    score = min(100, 10 + sum(int(driver["contribution"]) for driver in drivers))
    if score >= 85:
        level = "EXTREME"
    elif score >= 65:
        level = "HIGH"
    elif score >= 35:
        level = "MODERATE"
    else:
        level = "LOW"

    return {
        "status": "success",
        "risk_score": score,
        "risk_level": level,
        "drivers": drivers,
        "confidence": "medium",
        "limitations": ["Vegetation dryness proxy unavailable in MVP"],
    }
