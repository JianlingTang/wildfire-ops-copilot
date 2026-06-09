from fastapi.testclient import TestClient

from app.main import app


def test_get_alerts_returns_alerts_from_store() -> None:
    client = TestClient(app)
    client.post("/api/runs/manual", json={"region_id": "blue_mountains", "region_name": "Blue Mountains"})

    response = client.get("/api/alerts")

    assert response.status_code == 200
    alerts = response.json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["status"] == "active"


def test_acknowledge_alert_updates_status() -> None:
    client = TestClient(app)
    run = client.post("/api/runs/manual", json={"region_id": "blue_mountains", "region_name": "Blue Mountains"})
    alert_id = run.json()["alert"]["alert_id"]

    response = client.post(f"/api/alerts/{alert_id}/acknowledge", json={"actor": "demo_officer"})

    assert response.status_code == 200
    assert response.json()["alert"]["status"] == "acknowledged"
