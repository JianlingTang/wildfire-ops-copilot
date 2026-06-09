from fastapi.testclient import TestClient

from app.main import app


def test_hotspots_overview_returns_australia_summary() -> None:
    client = TestClient(app)

    response = client.get("/api/hotspots/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["total_count_24h"] >= 1
    assert payload["data"]["display_hotspot_count"] == len(payload["data"]["hotspots"])
    assert any(state["state"] == "NT" for state in payload["data"]["states"])
    assert payload["data"]["states"][0]["radius_options_km"] == [30, 50, 100, 200]


def test_hotspots_focus_returns_state_cluster() -> None:
    client = TestClient(app)

    response = client.get("/api/hotspots/focus?state=NT&radius_km=100")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["state"] == "NT"
    assert payload["data"]["radius_km"] == 100
    assert payload["data"]["display_hotspot_count"] == len(payload["data"]["hotspots"])
