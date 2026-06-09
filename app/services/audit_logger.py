from typing import Any

from app.services.firestore_store import store


def write_audit_log(actor: str, event_type: str, target_id: str, metadata: dict[str, Any] | None = None) -> dict:
    return store.create_audit_log(
        actor=actor,
        event_type=event_type,
        target_id=target_id,
        metadata=metadata or {},
    )
