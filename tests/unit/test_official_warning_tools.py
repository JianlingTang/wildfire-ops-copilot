from app.models.schemas import Aoi
from app.tools.official_warning_tools import (
    _NSW_RFS_CACHE,
    _NSW_RFS_CACHE_LOCK,
    get_official_fire_warnings,
    refresh_nsw_rfs_warning_cache,
)


def _reset_rfs_cache() -> None:
    with _NSW_RFS_CACHE_LOCK:
        _NSW_RFS_CACHE.update(
            {
                "payload": None,
                "last_checked_at": None,
                "last_refreshed_at": None,
                "next_refresh_at": None,
                "refresh_error": None,
                "refreshing": False,
            }
        )


def test_returns_live_warning_summary(monkeypatch) -> None:
    _reset_rfs_cache()

    class DummyResponse:
        headers = {"cache-control": "max-age=30, must-revalidate"}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "features": [
                    {
                        "geometry": {"type": "Point", "coordinates": [150.33, -33.72]},
                        "properties": {
                            "title": "Blue Mountains Fire",
                            "category": "Watch and Act",
                            "guid": "incident-1",
                            "pubDate": "28/05/2026 10:06:00 AM",
                            "description": (
                                "ALERT LEVEL: Watch and Act <br />LOCATION: Katoomba <br />"
                                "STATUS: Out of control <br />FIRE: Yes <br />UPDATED: 28 May 2026 10:06"
                            ),
                        },
                    },
                    {
                        "geometry": {"type": "Point", "coordinates": [151.7, -33.7]},
                        "properties": {
                            "title": "Far Away Fire",
                            "category": "Advice",
                            "guid": "incident-2",
                            "pubDate": "28/05/2026 09:00:00 AM",
                            "description": (
                                "ALERT LEVEL: Advice <br />LOCATION: Distant <br />"
                                "STATUS: Under control <br />FIRE: Yes"
                            ),
                        },
                    },
                ]
            }

    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")
    monkeypatch.setattr("app.tools.official_warning_tools.httpx.get", lambda *args, **kwargs: DummyResponse())

    refresh_nsw_rfs_warning_cache(force=True)
    result = get_official_fire_warnings("blue_mountains", Aoi())

    assert result["status"] == "success"
    assert result["mode"] == "live"
    assert result["source"] == "NSW Rural Fire Service GeoJSON"
    assert result["data"]["warning_level"] == "WATCH_AND_ACT"
    assert result["data"]["incident_count"] == 1
    assert result["data"]["incidents"][0]["lat"] == -33.72
    assert result["data"]["incidents"][0]["lon"] == 150.33


def test_live_warning_request_does_not_fetch_when_cache_is_ready(monkeypatch) -> None:
    _reset_rfs_cache()
    calls = {"count": 0}

    class DummyResponse:
        headers = {"cache-control": "max-age=30"}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"features": []}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        return DummyResponse()

    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")
    monkeypatch.setattr("app.tools.official_warning_tools.httpx.get", fake_get)

    refresh_nsw_rfs_warning_cache(force=True)
    assert calls["count"] == 1

    result = get_official_fire_warnings("blue_mountains", Aoi())
    assert result["status"] == "success"
    assert calls["count"] == 1


def test_falls_back_when_warning_feed_fails(monkeypatch) -> None:
    _reset_rfs_cache()

    def failing_get(*args, **kwargs):
        raise RuntimeError("feed unavailable")

    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")
    monkeypatch.setattr("app.tools.official_warning_tools.httpx.get", failing_get)

    result = get_official_fire_warnings("blue_mountains", Aoi())

    assert result["status"] == "success"
    assert result["mode"] == "demo"
    assert result["source"] == "Official warnings demo fallback"
    assert "failed" in result["message"]


def test_non_nsw_region_reports_warning_coverage_gap(monkeypatch) -> None:
    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")

    result = get_official_fire_warnings("live_qld_demo_cluster", Aoi(center=(-15.0596, 143.2559), radius_km=40))

    assert result["status"] == "success"
    assert result["mode"] == "live"
    assert result["source"] == "Australian warning coverage pending outside NSW"
    assert result["data"]["incident_count"] == 0
