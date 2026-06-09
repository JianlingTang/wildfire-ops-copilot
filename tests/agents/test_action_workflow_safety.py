from app.agents.root_agent import classify_intent
from app.agents.workflows.action_workflow import draft_action


def test_advisory_command_routes_to_action_workflow() -> None:
    assert classify_intent("Draft a public advisory for this alert.") == "ACTION_COMMAND"


def test_action_workflow_creates_pending_approval_without_execution() -> None:
    result = draft_action("Draft a public advisory for this alert.", run=None, requested_by="demo_officer")

    assert result["status"] == "success"
    assert result["action"]["status"] == "pending_approval"
    assert result["approval"]["status"] == "pending_approval"
