from app.models.schemas import Aoi
from app.tools.fire_hotspot_tools import (
    get_australia_hotspots_overview,
    get_fire_hotspots,
    get_state_hotspot_focus,
    resolve_operational_region,
)


def test_validates_input_aoi() -> None:
    result = get_fire_hotspots({"radius_km": -1})

    assert result["status"] == "error"
    assert "radius_km" in result["message"]


def test_returns_structured_status() -> None:
    result = get_fire_hotspots(Aoi())

    assert result["status"] == "error"
    assert "live data is required" in result["message"]


def test_parses_live_hotspot_response_from_dea(monkeypatch) -> None:
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "features": [
                    {
                        "geometry": {"type": "Point", "coordinates": [150.31, -33.71]},
                        "properties": {
                            "datetime": "2026-05-28T00:30:00Z",
                            "confidence": 90,
                            "power": 18.4,
                            "satellite": "HIMAWARI-9",
                            "sensor": "AHI",
                        },
                    },
                    {
                        "geometry": {"type": "Point", "coordinates": [150.33, -33.73]},
                        "properties": {
                            "datetime": "2026-05-27T06:15:00Z",
                            "confidence": 80,
                            "power": 9.0,
                            "satellite": "HIMAWARI-9",
                            "sensor": "AHI",
                        },
                    },
                    {
                        "geometry": {"type": "Point", "coordinates": [151.8, -33.7]},
                        "properties": {"datetime": "2026-05-28T01:00:00Z", "confidence": 50},
                    },
                ]
            }

    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")
    monkeypatch.delenv("NASA_FIRMS_API_KEY", raising=False)
    monkeypatch.delenv("NASA_FIRMS_MAP_KEY", raising=False)
    monkeypatch.setattr("app.tools.fire_hotspot_tools.httpx.get", lambda *args, **kwargs: DummyResponse())

    result = get_fire_hotspots(Aoi())

    assert result["status"] == "success"
    assert result["mode"] == "live"
    assert result["source"] == "DEA Hotspots recent feed"
    assert result["data"]["count_7d"] == 2
    assert len(result["data"]["hotspots"]) == 2


def test_handles_api_failure() -> None:
    result = get_fire_hotspots({"radius_km": 30, "simulate_failure": True})

    assert result["status"] == "error"
    assert "failure" in result["message"]


def test_auto_region_selection_returns_provider_error_in_demo_mode() -> None:
    result = resolve_operational_region("live_australia", "Australia Live Hotspot AOI")

    assert result["region_id"] == "live_australia"
    assert result["region_context"]["selection_mode"] == "provider_error"
    assert result["hotspots"]["status"] == "error"
    assert "live data is required" in result["hotspots"]["message"]


def test_australia_overview_returns_error_in_demo_mode() -> None:
    result = get_australia_hotspots_overview()

    assert result["status"] == "error"
    assert "live data is required" in result["message"]


def test_state_focus_returns_error_in_demo_mode() -> None:
    result = get_state_hotspot_focus("NT", 50)

    assert result["status"] == "error"
    assert "live data is required" in result["message"]


def test_explicit_state_aoi_region_reuses_aoi_hotspots_in_demo_mode() -> None:
    result = resolve_operational_region(
        "state_nt",
        "Northern Territory hotspot cluster focus",
        Aoi(center=(-12.4513, 132.9192), radius_km=50),
        respect_explicit_aoi=True,
    )

    assert result["region_context"]["selection_mode"] == "selected_aoi"
    assert result["hotspots"]["status"] == "error"
    assert result["hotspots"]["data"]["count_24h"] == 0
    assert result["hotspots"]["data"]["hotspots"] == []
