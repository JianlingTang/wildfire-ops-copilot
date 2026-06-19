from fastapi import APIRouter, HTTPException

from app.models.schemas import ApprovalDecisionRequest
from app.services.agent_events import new_trace_id, publish_agent_event
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
    publish_agent_event(
        trace_id=new_trace_id(),
        conversation_id=None,
        run_id=action.run_id,
        region_id=None,
        agent_type="approval",
        status="completed",
        message="Public advisory action approved.",
        data={
            "action_id": action.action_id,
            "approval_id": approval.approval_id,
            "artifact_id": f"{action.action_id}-advisory-assets",
            "output_summary": "TXT and PNG poster assets are generated client-side.",
        },
    )
    return {"action": action, "approval": approval}


@router.post("/actions/{action_id}/reject")
def reject_action(action_id: str, request: ApprovalDecisionRequest) -> dict:
    action = store.actions.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if not can_decide_action(request.actor, action):
        raise HTTPException(status_code=403, detail="Action cannot be rejected by this actor or state")
    action, approval = store.reject_action(action_id, request.actor)
    publish_agent_event(
        trace_id=new_trace_id(),
        conversation_id=None,
        run_id=action.run_id,
        region_id=None,
        agent_type="approval",
        status="completed",
        message="Public advisory action rejected.",
        data={
            "action_id": action.action_id,
            "approval_id": approval.approval_id,
            "output_summary": "No downloadable advisory assets generated for rejected action.",
        },
    )
    return {"action": action, "approval": approval}
