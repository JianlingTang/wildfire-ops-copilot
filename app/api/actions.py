from fastapi import APIRouter, HTTPException

from app.models.schemas import ApprovalDecisionRequest
from app.services.approval_policy import can_decide_action
from app.services.firestore_store import store

router = APIRouter(tags=["actions"])


@router.get("/actions")
def list_actions() -> dict:
    return {"actions": list(store.actions.values()), "approvals": list(store.approvals.values())}


@router.post("/actions/{action_id}/approve")
def approve_action(action_id: str, request: ApprovalDecisionRequest) -> dict:
    action = store.actions.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if not can_decide_action(request.actor, action):
        raise HTTPException(status_code=403, detail="Action cannot be approved by this actor or state")
    action, approval = store.approve_action(action_id, request.actor)
    return {"action": action, "approval": approval}


@router.post("/actions/{action_id}/reject")
def reject_action(action_id: str, request: ApprovalDecisionRequest) -> dict:
    action = store.actions.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if not can_decide_action(request.actor, action):
        raise HTTPException(status_code=403, detail="Action cannot be rejected by this actor or state")
    action, approval = store.reject_action(action_id, request.actor)
    return {"action": action, "approval": approval}
