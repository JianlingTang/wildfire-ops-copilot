from fastapi.testclient import TestClient

from app.main import app
from app.services.firestore_store import store


def test_get_alerts_returns_alerts_from_store() -> None:
    client = TestClient(app)
    store.create_alert(
        {
            "run_id": "run_test",
            "region_id": "blue_mountains",
            "region_name": "Blue Mountains",
            "severity": "HIGH",
            "reason": "test alert",
            "evidence_ids": [],
            "recommended_next_action": "review",
        }
    )

    response = client.get("/api/alerts")

    assert response.status_code == 200
    alerts = response.json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["status"] == "active"


def test_acknowledge_alert_updates_status() -> None:
    client = TestClient(app)
    alert = store.create_alert(
        {
            "run_id": "run_test",
            "region_id": "blue_mountains",
            "region_name": "Blue Mountains",
            "severity": "HIGH",
            "reason": "test alert",
            "evidence_ids": [],
            "recommended_next_action": "review",
        }
    )

    response = client.post(f"/api/alerts/{alert.alert_id}/acknowledge", json={"actor": "demo_officer"})

    assert response.status_code == 200
    assert response.json()["alert"]["status"] == "acknowledged"
