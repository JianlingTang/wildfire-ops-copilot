from datetime import UTC, datetime

from app.models.schemas import ActionRecord
from app.services.approval_policy import can_decide_action, can_execute_external_action, validate_action_type


def pending_action() -> ActionRecord:
    return ActionRecord(
        action_id="action_test",
        action_type="public_advisory",
        title="Draft",
        draft="Pending review",
        status="pending_approval",
        requested_by="demo_officer",
        created_at=datetime.now(UTC),
    )


def test_blocks_external_actions_without_approval() -> None:
    assert can_execute_external_action("pending_approval") is False
    assert can_execute_external_action(None) is False


def test_allows_execution_only_when_approval_status_is_approved() -> None:
    assert can_execute_external_action("approved") is True


def test_rejects_unsupported_action_types() -> None:
    result = validate_action_type("direct_emergency_call")

    assert result["status"] == "error"


def test_can_decide_pending_action_with_actor() -> None:
    assert can_decide_action("incident_controller", pending_action()) is True
