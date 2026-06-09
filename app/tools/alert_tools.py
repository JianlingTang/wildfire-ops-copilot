from typing import Any

from app.services.firestore_store import store


def create_alert(alert_payload: dict[str, Any]) -> dict:
    alert = store.create_alert(alert_payload)
    return {"status": "success", "alert": alert.model_dump()}
