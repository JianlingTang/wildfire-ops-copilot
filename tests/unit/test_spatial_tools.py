from app.models.schemas import Aoi
from app.tools.spatial_tools import get_spatial_exposure_summary


def test_validates_input_aoi() -> None:
    result = get_spatial_exposure_summary({"radius_km": 0})

    assert result["status"] == "error"
    assert "radius_km" in result["message"]


def test_returns_live_spatial_summary(monkeypatch) -> None:
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "elements": [
                    {"tags": {"name": "Katoomba", "place": "town"}},
                    {"tags": {"name": "Leura", "place": "town"}},
                    {"tags": {"name": "Great Western Highway", "highway": "primary"}},
                    {"tags": {"name": "Blue Mountains Hospital", "amenity": "hospital"}},
                ]
            }

    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")
    monkeypatch.setattr("app.tools.spatial_tools.httpx.post", lambda *args, **kwargs: DummyResponse())

    result = get_spatial_exposure_summary(Aoi())

    assert result["status"] == "success"
    assert result["mode"] == "live"
    assert result["source"] == "OpenStreetMap Overpass API"
    assert result["data"]["nearby_towns"] == ["Katoomba", "Leura"]
    assert result["data"]["roads"] == ["Great Western Highway"]
    assert result["data"]["critical_asset_count"] == 1


def test_falls_back_when_spatial_api_fails(monkeypatch) -> None:
    def failing_post(*args, **kwargs):
        raise RuntimeError("overpass unavailable")

    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")
    monkeypatch.setattr("app.tools.spatial_tools.httpx.post", failing_post)

    result = get_spatial_exposure_summary(Aoi())

    assert result["status"] == "success"
    assert result["mode"] == "demo"
    assert result["source"] == "Seeded GeoJSON demo fallback"
    assert "failed" in result["message"]
