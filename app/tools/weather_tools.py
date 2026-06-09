from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.models.schemas import Aoi
from app.tools.provider_utils import coerce_center, external_data_mode, http_user_agent, request_timeout_seconds

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def get_weather_forecast(aoi: Aoi | dict, horizon: str = "7d") -> dict:
    validation = _validate_aoi(aoi)
    if validation["status"] == "error":
        return validation
    if external_data_mode() == "demo":
        return _demo_weather_forecast(horizon)

    try:
        return _fetch_live_weather_forecast(aoi, horizon)
    except Exception as exc:
        return _demo_weather_forecast(horizon, message=f"Live weather request failed: {exc}")


def _validate_aoi(aoi: Aoi | dict) -> dict:
    if isinstance(aoi, dict) and aoi.get("simulate_failure"):
        return {"status": "error", "message": "Weather provider failure simulated."}
    radius = aoi.get("radius_km") if isinstance(aoi, dict) else aoi.radius_km
    if radius is None or radius <= 0:
        return {"status": "error", "message": "AOI radius_km must be positive."}
    return {"status": "success"}


def _fetch_live_weather_forecast(aoi: Aoi | dict, horizon: str) -> dict:
    latitude, longitude = coerce_center(aoi)
    forecast_days = 7 if horizon == "7d" else 3 if horizon == "72h" else 1
    response = httpx.get(
        OPEN_METEO_FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "forecast_days": forecast_days,
            "daily": "temperature_2m_max,precipitation_sum",
            "hourly": "relative_humidity_2m,wind_speed_10m,wind_gusts_10m",
            "timezone": "Australia/Sydney",
        },
        headers={"User-Agent": http_user_agent()},
        timeout=request_timeout_seconds(),
    )
    response.raise_for_status()
    payload = response.json()

    hourly = payload.get("hourly", {})
    daily = payload.get("daily", {})
    humidity = [float(value) for value in hourly.get("relative_humidity_2m", [])]
    wind_speed = [float(value) for value in hourly.get("wind_speed_10m", [])]
    wind_gusts = [float(value) for value in hourly.get("wind_gusts_10m", [])]
    daily_temp = [float(value) for value in daily.get("temperature_2m_max", [])]
    precipitation = [float(value) for value in daily.get("precipitation_sum", [])]

    if not humidity or not wind_speed or not wind_gusts or not daily_temp:
        raise ValueError("Open-Meteo response was missing expected forecast series.")

    return {
        "status": "success",
        "mode": "live",
        "source": "Open-Meteo forecast API",
        "fetched_at": datetime.now(UTC).isoformat(),
        "data": {
            "horizon": horizon,
            "temperature_max": round(max(daily_temp)),
            "humidity_min": round(min(humidity)),
            "wind_speed_max": round(max(wind_speed)),
            "wind_gust_max": round(max(wind_gusts)),
            "rainfall_7d": round(sum(precipitation), 1),
            "forecast_start": daily.get("time", [None])[0],
            "forecast_end": daily.get("time", [None])[-1],
            "timezone": payload.get("timezone", "Australia/Sydney"),
        },
    }


def _demo_weather_forecast(horizon: str, message: str | None = None) -> dict:
    payload = {
        "status": "success",
        "mode": "demo",
        "source": "Open-Meteo demo fallback",
        "data": {
            "horizon": horizon,
            "temperature_max": 34,
            "humidity_min": 24,
            "wind_speed_max": 35,
            "wind_gust_max": 45,
            "rainfall_7d": 5,
        },
    }
    if message:
        payload["message"] = message
    return payload
