from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.models.schemas import Aoi
from app.tools.provider_utils import coerce_center, external_data_mode, http_user_agent, request_timeout_seconds

MET_NORWAY_FORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def get_weather_forecast(aoi: Aoi | dict, horizon: str = "7d") -> dict:
    validation = _validate_aoi(aoi)
    if validation["status"] == "error":
        return validation
    if external_data_mode() == "demo":
        return {"status": "error", "message": "Weather provider is configured for demo mode; live data is required."}

    try:
        return _fetch_met_norway_forecast(aoi, horizon)
    except Exception as exc:
        return {"status": "error", "message": f"MET Norway weather request failed: {exc}"}


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


def _fetch_met_norway_forecast(aoi: Aoi | dict, horizon: str) -> dict:
    latitude, longitude = coerce_center(aoi)
    response = httpx.get(
        MET_NORWAY_FORECAST_URL,
        params={"lat": latitude, "lon": longitude},
        headers={"User-Agent": http_user_agent()},
        timeout=request_timeout_seconds(default=8.0),
    )
    response.raise_for_status()
    payload = response.json()
    series = payload.get("properties", {}).get("timeseries", [])
    limit = 168 if horizon == "7d" else 72 if horizon == "72h" else 24
    temperatures: list[float] = []
    humidity: list[float] = []
    wind_speed: list[float] = []
    wind_gusts: list[float] = []
    precipitation: list[float] = []
    times: list[str] = []
    for item in series[:limit]:
        if isinstance(item.get("time"), str):
            times.append(item["time"])
        data = item.get("data", {})
        details = data.get("instant", {}).get("details", {})
        if "air_temperature" in details:
            temperatures.append(float(details["air_temperature"]))
        if "relative_humidity" in details:
            humidity.append(float(details["relative_humidity"]))
        if "wind_speed" in details:
            wind_speed.append(float(details["wind_speed"]) * 3.6)
        if details.get("wind_speed_of_gust") is not None:
            wind_gusts.append(float(details["wind_speed_of_gust"]) * 3.6)
        for key in ("next_1_hours", "next_6_hours", "next_12_hours"):
            amount = data.get(key, {}).get("details", {}).get("precipitation_amount")
            if amount is not None:
                precipitation.append(float(amount))
                break

    if not temperatures or not humidity or not wind_speed:
        raise ValueError("MET Norway response was missing expected forecast series.")

    wind_speed_max = round(max(wind_speed))
    return {
        "status": "success",
        "mode": "live",
        "source": "MET Norway Locationforecast API",
        "fetched_at": datetime.now(UTC).isoformat(),
        "data": {
            "horizon": horizon,
            "temperature_max": round(max(temperatures)),
            "humidity_min": round(min(humidity)),
            "wind_speed_max": wind_speed_max,
            "wind_gust_max": round(max(wind_gusts)) if wind_gusts else wind_speed_max,
            "rainfall_7d": round(sum(precipitation), 1),
            "forecast_start": times[0] if times else None,
            "forecast_end": times[-1] if times else None,
            "timezone": "UTC",
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
