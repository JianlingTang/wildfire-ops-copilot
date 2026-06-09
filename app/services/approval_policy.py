from app.models.schemas import ActionRecord

SUPPORTED_ACTION_TYPES = {
    "emergency_services_email",
    "public_advisory",
    "field_team_brief",
    "call_script",
    "internal_task",
}


def can_decide_action(actor: str, action: ActionRecord) -> bool:
    return bool(actor.strip()) and action.status == "pending_approval"


def validate_action_type(action_type: str) -> dict:
    if action_type not in SUPPORTED_ACTION_TYPES:
        return {"status": "error", "message": f"Unsupported action type: {action_type}"}
    return {"status": "success", "action_type": action_type}


def can_execute_external_action(approval_status: str | None) -> bool:
    return approval_status == "approved"
