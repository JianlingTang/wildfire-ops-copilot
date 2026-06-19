import time
from datetime import UTC, datetime, timedelta

from app.models.schemas import Aoi
from app.services.analysis_pipeline import compute_analysis, reset_analysis_cache
from app.tools.fire_hotspot_tools import resolve_operational_region


def _weather_payload() -> dict:
    return {
        "status": "success",
        "mode": "demo",
        "source": "weather test",
        "data": {
            "temperature_max": 31,
            "humidity_min": 20,
            "wind_speed_max": 25,
            "wind_gust_max": 42,
            "rainfall_7d": 1,
        },
    }


def _warnings_payload() -> dict:
    return {
        "status": "success",
        "mode": "demo",
        "source": "warnings test",
        "data": {
            "warning_level": "ADVICE",
            "incident_count": 0,
            "incidents": [],
        },
    }


def _spatial_payload() -> dict:
    return {
        "status": "success",
        "mode": "demo",
        "source": "spatial test",
        "data": {
            "critical_asset_count": 2,
            "nearby_towns": ["Test Town"],
            "roads": ["Test Road"],
        },
    }


def _elastic_payload() -> dict:
    return {
        "status": "success",
        "mode": "demo",
        "source": "elastic test",
        "evidence": [
            {
                "evidence_id": "elastic_test_001",
                "summary": "Mocked evidence summary",
                "region_name": "Northern Territory hotspot focus",
            }
        ],
    }


def _live_nt_rows() -> tuple[list[dict], str, str, bool]:
    now = datetime.now(UTC)
    return (
        [
            {
                "lat": -12.4513,
                "lon": 132.9192,
                "state": "NT",
                "confidence": "high",
                "detected_at": now - timedelta(minutes=20),
                "power": 24.0,
                "satellite": "HIMAWARI-9",
                "sensor": "AHI",
            },
            {
                "lat": -12.36,
                "lon": 132.98,
                "state": "NT",
                "confidence": "nominal",
                "detected_at": now - timedelta(minutes=40),
                "power": 16.0,
                "satellite": "HIMAWARI-9",
                "sensor": "AHI",
            },
        ],
        "live",
        "test live hotspots",
        False,
    )


def test_state_focus_region_reuses_cached_hotspot_payload(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.fire_hotspot_tools._get_or_load_australia_hotspot_rows", _live_nt_rows)

    result = resolve_operational_region(
        "state_nt",
        "Northern Territory hotspot focus",
        Aoi(center=(-12.4513, 132.9192), radius_km=50),
    )

    assert result["region_context"]["selection_mode"] == "state_focus"
    assert result["hotspots"] is not None
    assert result["hotspots"]["data"]["count_24h"] >= 1


def test_compute_analysis_reuses_cached_inputs_for_same_aoi(monkeypatch) -> None:
    reset_analysis_cache()
    monkeypatch.setattr("app.tools.fire_hotspot_tools._get_or_load_australia_hotspot_rows", _live_nt_rows)
    region = resolve_operational_region(
        "state_nt",
        "Northern Territory hotspot focus",
        Aoi(center=(-12.4513, 132.9192), radius_km=50),
    )

    calls = {"weather": 0, "warnings": 0, "spatial": 0, "elastic": 0}

    def weather(*args, **kwargs):
        calls["weather"] += 1
        return _weather_payload()

    def warnings(*args, **kwargs):
        calls["warnings"] += 1
        return _warnings_payload()

    def spatial(*args, **kwargs):
        calls["spatial"] += 1
        return _spatial_payload()

    def elastic(*args, **kwargs):
        calls["elastic"] += 1
        return _elastic_payload()

    monkeypatch.setattr("app.services.analysis_pipeline.get_weather_forecast", weather)
    monkeypatch.setattr("app.services.analysis_pipeline.get_official_fire_warnings", warnings)
    monkeypatch.setattr("app.services.analysis_pipeline.get_spatial_exposure_summary", spatial)
    monkeypatch.setattr("app.services.analysis_pipeline.query_elastic_evidence", elastic)
    monkeypatch.setattr(
        "app.services.analysis_pipeline.get_fire_hotspots",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("hotspots should be reused from focus")),
    )

    first = compute_analysis(region, recommendations=["Inspect first."], elastic_query="wildfire operational evidence")
    second = compute_analysis(region, recommendations=["Inspect first."], elastic_query="wildfire operational evidence")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert calls == {"weather": 1, "warnings": 1, "spatial": 1, "elastic": 1}


def test_compute_analysis_uses_spatial_fallback_after_soft_timeout(monkeypatch) -> None:
    reset_analysis_cache()
    monkeypatch.setenv("ANALYSIS_SPATIAL_SOFT_TIMEOUT_SECONDS", "0.05")
    region = resolve_operational_region(
        "state_nt",
        "Northern Territory hotspot focus",
        Aoi(center=(-12.4513, 132.9192), radius_km=50),
    )

    monkeypatch.setattr(
        "app.services.analysis_pipeline.get_weather_forecast",
        lambda *args, **kwargs: _weather_payload(),
    )
    monkeypatch.setattr(
        "app.services.analysis_pipeline.get_official_fire_warnings",
        lambda *args, **kwargs: _warnings_payload(),
    )
    monkeypatch.setattr(
        "app.services.analysis_pipeline.query_elastic_evidence",
        lambda *args, **kwargs: _elastic_payload(),
    )

    def slow_spatial(*args, **kwargs):
        time.sleep(0.2)
        return _spatial_payload()

    monkeypatch.setattr("app.services.analysis_pipeline.get_spatial_exposure_summary", slow_spatial)

    started = time.monotonic()
    result = compute_analysis(region, recommendations=["Inspect first."], elastic_query="wildfire operational evidence")
    elapsed = time.monotonic() - started

    assert elapsed < 0.18
    assert result.spatial_soft_timeout is True
    assert "soft timeout" in result.evidence["spatial"]["message"].lower()
