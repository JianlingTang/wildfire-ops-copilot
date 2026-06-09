from app.services.approval_policy import can_execute_external_action
from app.services.firestore_store import store

BLOCKED_MODEL_PATTERNS = [
    "ignore previous instructions",
    "bypass human approval",
    "without approval",
    "pretend to be the official emergency authority",
    "call emergency services now",
]

EXTERNAL_TOOLS = {"send_email", "publish_public_advisory", "notify_field_team", "post_to_social_media"}


def before_model_callback(message: str) -> dict:
    normalized = message.lower()
    for pattern in BLOCKED_MODEL_PATTERNS:
        if pattern in normalized:
            return {
                "status": "blocked",
                "reason": "Unsafe request blocked by wildfire operations guardrail.",
                "safe_response": "I can draft this action, but it requires human approval before execution.",
            }
    return {"status": "allowed"}


def before_tool_callback(tool_name: str, arguments: dict) -> dict:
    if tool_name not in EXTERNAL_TOOLS:
        return {"status": "allowed"}

    approval_id = arguments.get("approval_id")
    if not approval_id:
        return {"status": "blocked", "reason": "External action requires approval_id."}

    approval = store.approvals.get(approval_id)
    if not approval or not can_execute_external_action(approval.status):
        return {"status": "blocked", "reason": "External action requires approved approval state."}

    return {"status": "allowed"}
