from app.models.schemas import Aoi
from app.tools.spatial_tools import get_spatial_exposure_summary


def test_validates_input_aoi() -> None:
    result = get_spatial_exposure_summary({"radius_km": 0})

    assert result["status"] == "error"
    assert "radius_km" in result["message"]


def test_returns_live_spatial_summary(monkeypatch) -> None:
    class DummyResponse:
        def __init__(self, items) -> None:
            self.items = items

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.items

    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")

    def fake_get(*args, **kwargs):
        query = kwargs.get("params", {}).get("q")
        if query == "hospital":
            return DummyResponse([{"display_name": "Blue Mountains Hospital"}])
        return DummyResponse([])

    def fake_post(*args, **kwargs):
        return DummyResponse(
            {"elements": [{"tags": {"name": "Blue Mountains National Park", "boundary": "protected_area"}}]}
        )

    monkeypatch.setattr("app.tools.spatial_tools.httpx.get", fake_get)
    monkeypatch.setattr("app.tools.spatial_tools.httpx.post", fake_post)

    result = get_spatial_exposure_summary(Aoi())

    assert result["status"] == "success"
    assert result["mode"] == "live"
    assert result["source"] == "OpenStreetMap Nominatim + Overpass APIs"
    assert result["data"]["critical_asset_count"] == 1
    assert result["data"]["critical_assets"] == ["Blue Mountains Hospital"]
    assert result["data"]["protected_area_count"] == 1
    assert result["data"]["protected_areas"] == ["Blue Mountains National Park"]


def test_returns_error_when_spatial_api_fails(monkeypatch) -> None:
    def failing_get(*args, **kwargs):
        raise RuntimeError("nominatim unavailable")

    monkeypatch.setenv("WILDFIRE_DATA_MODE", "auto")
    monkeypatch.setattr("app.tools.spatial_tools.httpx.get", failing_get)

    result = get_spatial_exposure_summary(Aoi())

    assert result["status"] == "error"
    assert "nominatim unavailable" in result["message"]
