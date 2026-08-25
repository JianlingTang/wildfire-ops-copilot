from app.models.schemas import Aoi
from app.tools.fire_hotspot_tools import (
    _AUSTRALIA_OVERVIEW_CACHE,
    _AUSTRALIA_OVERVIEW_CACHE_LOCK,
    get_australia_hotspots_overview,
    get_fire_hotspots,
    get_state_hotspot_focus,
    refresh_dea_hotspot_cache,
    resolve_operational_region,
)


def _reset_dea_cache() -> None:
    with _AUSTRALIA_OVERVIEW_CACHE_LOCK:
        _AUSTRALIA_OVERVIEW_CACHE.update(
            {
                "etag": None,
                "last_modified": None,
                "last_checked_at": None,
                "last_refreshed_at": None,
                "next_refresh_at": None,
                "payload": None,
                "refresh_error": None,
                "refreshing": False,
                "rows": None,
            }
        )


def test_validates_input_aoi() -> None:
    result = get_fire_hotspots({"radius_km": -1})

    assert result["status"] == "error"
    assert "radius_km" in result["message"]


def test_returns_structured_status() -> None:
    result = get_fire_hotspots(Aoi())

    assert result["status"] == "success"
    assert result["mode"] == "demo"
    assert result["data"]["count_24h"] >= 1


def test_parses_live_hotspot_response_from_dea(monkeypatch) -> None:
    _reset_dea_cache()

    class DummyResponse:
        status_code = 200
        headers = {"etag": '"test-etag"', "last-modified": "Sat, 22 Aug 2026 06:52:14 GMT"}

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
    monkeypatch.setattr("app.tools.fire_hotspot_tools.cache.httpx.get", lambda *args, **kwargs: DummyResponse())

    refresh_dea_hotspot_cache(force=True)
    result = get_fire_hotspots(Aoi())

    assert result["status"] == "success"
    assert result["mode"] == "live"
    assert result["source"] == "DEA Hotspots recent feed"
    assert result["data"]["count_7d"] == 2
    assert len(result["data"]["hotspots"]) == 2


def test_live_hotspot_request_does_not_fetch_dea_when_cache_is_ready(monkeypatch) -> None:
    _reset_dea_cache()
    calls = {"count": 0}

    class DummyResponse:
        status_code = 200
        headers = {"etag": '"test-etag"'}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "features": [
                    {
                        "geometry": {"type": "Point", "coordinates": [150.31, -33.71]},
                        "properties": {"datetime": "2026-05-28T00:30:00Z", "confidence": 90},
                    }
                ]
            }

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        return DummyResponse()

    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")
    monkeypatch.delenv("NASA_FIRMS_API_KEY", raising=False)
    monkeypatch.delenv("NASA_FIRMS_MAP_KEY", raising=False)
    monkeypatch.setattr("app.tools.fire_hotspot_tools.cache.httpx.get", fake_get)

    refresh_dea_hotspot_cache(force=True)
    assert calls["count"] == 1

    result = get_australia_hotspots_overview()
    assert result["status"] == "success"
    assert calls["count"] == 1


def test_handles_api_failure() -> None:
    result = get_fire_hotspots({"radius_km": 30, "simulate_failure": True})

    assert result["status"] == "error"
    assert "failure" in result["message"]


def test_auto_region_selection_returns_demo_region_in_demo_mode() -> None:
    result = resolve_operational_region("live_australia", "Australia Live Hotspot AOI")

    assert result["region_id"] == "live_qld_demo_cluster"
    assert result["region_context"]["selection_mode"] == "demo_auto_live_hotspot"
    assert result["hotspots"]["status"] == "success"
    assert result["hotspots"]["mode"] == "demo"


def test_australia_overview_returns_demo_payload_in_demo_mode() -> None:
    result = get_australia_hotspots_overview()

    assert result["status"] == "success"
    assert result["mode"] == "demo"
    assert any(state["state"] == "NT" for state in result["data"]["states"])


def test_state_focus_returns_demo_payload_in_demo_mode() -> None:
    result = get_state_hotspot_focus("NT", 50)

    assert result["status"] == "success"
    assert result["mode"] == "demo"
    assert result["data"]["state"] == "NT"


def test_explicit_state_aoi_region_reuses_aoi_hotspots_in_demo_mode() -> None:
    result = resolve_operational_region(
        "state_nt",
        "Northern Territory hotspot cluster focus",
        Aoi(center=(-12.4513, 132.9192), radius_km=50),
        respect_explicit_aoi=True,
    )

    assert result["region_context"]["selection_mode"] == "selected_aoi"
    assert result["hotspots"]["status"] == "success"
    assert result["hotspots"]["mode"] == "demo"
    assert result["hotspots"]["data"]["count_24h"] >= 1
    assert result["hotspots"]["data"]["hotspots"]
