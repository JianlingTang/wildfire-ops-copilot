from app.services.firestore_store import store
from app.services.guardrails import before_tool_callback


def send_approved_email(approval_id: str) -> dict:
    guardrail = before_tool_callback("send_email", {"approval_id": approval_id})
    if guardrail["status"] == "blocked":
        return {"status": "error", "message": guardrail["reason"]}
    approval = store.approvals.get(approval_id)
    if not approval:
        return {"status": "error", "message": "Approval record not found."}
    if approval.status != "approved":
        return {"status": "error", "message": "External email requires approved approval state."}
    return {"status": "success", "message": "Demo email execution recorded; no real email was sent."}
