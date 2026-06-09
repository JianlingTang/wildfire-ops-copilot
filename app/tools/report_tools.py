from typing import Any

from app.services.firestore_store import store


def save_report(report_payload: dict[str, Any]) -> dict:
    report = store.create_report(report_payload)
    return {"status": "success", "report": report.model_dump()}
