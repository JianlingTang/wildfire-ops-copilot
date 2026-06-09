from typing import Any

from app.services.firestore_store import store


def create_pending_approval(action_draft: dict[str, Any]) -> dict:
    action, approval = store.create_action(action_draft)
    return {
        "status": "success",
        "action": action.model_dump(),
        "approval": approval.model_dump(),
    }
