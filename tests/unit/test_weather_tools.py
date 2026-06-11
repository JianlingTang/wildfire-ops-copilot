from app.models.schemas import Aoi
from app.tools.weather_tools import get_weather_forecast


def test_validates_input_aoi() -> None:
    result = get_weather_forecast({"radius_km": 0})

    assert result["status"] == "error"
    assert "radius_km" in result["message"]


def test_returns_structured_status() -> None:
    result = get_weather_forecast(Aoi())

    assert result["status"] == "error"
    assert "live data is required" in result["message"]


def test_parses_live_weather_response(monkeypatch) -> None:
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "properties": {
                    "timeseries": [
                        {
                            "time": "2026-05-28T00:00:00Z",
                            "data": {
                                "instant": {
                                    "details": {
                                        "air_temperature": 18.2,
                                        "relative_humidity": 40,
                                        "wind_speed": 12.1,
                                        "wind_speed_of_gust": 14,
                                    }
                                },
                                "next_1_hours": {"details": {"precipitation_amount": 0.4}},
                            },
                        },
                        {
                            "time": "2026-05-28T01:00:00Z",
                            "data": {
                                "instant": {
                                    "details": {
                                        "air_temperature": 24.6,
                                        "relative_humidity": 22,
                                        "wind_speed": 17.9,
                                        "wind_speed_of_gust": 20,
                                    }
                                },
                                "next_1_hours": {"details": {"precipitation_amount": 2.0}},
                            },
                        },
                    ]
                }
            }

    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")
    monkeypatch.setattr("app.tools.weather_tools.httpx.get", lambda *args, **kwargs: DummyResponse())

    result = get_weather_forecast(Aoi())

    assert result["status"] == "success"
    assert result["mode"] == "live"
    assert result["source"] == "MET Norway Locationforecast API"
    assert result["data"]["temperature_max"] == 25
    assert result["data"]["humidity_min"] == 22
    assert result["data"]["wind_gust_max"] == 72
    assert result["data"]["rainfall_7d"] == 2.4


def test_handles_api_failure() -> None:
    result = get_weather_forecast({"radius_km": 30, "simulate_failure": True})

    assert result["status"] == "error"
    assert "failure" in result["message"]
