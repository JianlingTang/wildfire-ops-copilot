from app.models.schemas import Aoi
from app.tools.weather_tools import get_weather_forecast


def test_validates_input_aoi() -> None:
    result = get_weather_forecast({"radius_km": 0})

    assert result["status"] == "error"
    assert "radius_km" in result["message"]


def test_returns_structured_status() -> None:
    result = get_weather_forecast(Aoi())

    assert result["status"] == "success"
    assert result["source"] == "Open-Meteo demo fallback"
    assert "data" in result


def test_parses_live_weather_response(monkeypatch) -> None:
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "timezone": "Australia/Sydney",
                "hourly": {
                    "relative_humidity_2m": [40, 22, 31],
                    "wind_speed_10m": [12.1, 17.9, 15.5],
                    "wind_gusts_10m": [28.4, 45.2, 38.1],
                },
                "daily": {
                    "time": ["2026-05-28", "2026-05-29"],
                    "temperature_2m_max": [18.2, 24.6],
                    "precipitation_sum": [0.4, 2.0],
                },
            }

    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")
    monkeypatch.setattr("app.tools.weather_tools.httpx.get", lambda *args, **kwargs: DummyResponse())

    result = get_weather_forecast(Aoi())

    assert result["status"] == "success"
    assert result["mode"] == "live"
    assert result["source"] == "Open-Meteo forecast API"
    assert result["data"]["temperature_max"] == 25
    assert result["data"]["humidity_min"] == 22
    assert result["data"]["wind_gust_max"] == 45
    assert result["data"]["rainfall_7d"] == 2.4


def test_handles_api_failure() -> None:
    result = get_weather_forecast({"radius_km": 30, "simulate_failure": True})

    assert result["status"] == "error"
    assert "failure" in result["message"]
