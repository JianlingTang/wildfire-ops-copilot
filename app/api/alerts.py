from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import AcknowledgeAlertRequest
from app.services.api_auth import authenticated_actor
from app.services.firestore_store import store

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
def list_alerts(status: str | None = None) -> dict:
    alerts = list(store.alerts.values())
    if status:
        alerts = [alert for alert in alerts if alert.status == status]
    return {"alerts": alerts}


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, request: Request, payload: AcknowledgeAlertRequest) -> dict:
    if alert_id not in store.alerts:
        raise HTTPException(status_code=404, detail="Alert not found")
    # Acknowledging is routine operator work, so unlike approving an action it is not
    # gated behind the admin role.
    actor = authenticated_actor(request, payload.actor)
    return {"alert": store.acknowledge_alert(alert_id, actor)}
