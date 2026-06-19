from datetime import UTC, datetime

from app.agents.root_agent import classify_intent
from app.agents.workflows.action_workflow import draft_action
from app.models.schemas import RunRecord


def test_advisory_command_routes_to_action_workflow() -> None:
    assert classify_intent("Draft a public advisory for this alert.") == "ACTION_COMMAND"


def test_action_workflow_creates_pending_approval_without_execution() -> None:
    result = draft_action("Draft a public advisory for this alert.", run=None, requested_by="demo_officer")

    assert result["status"] == "success"
    assert result["action"]["status"] == "pending_approval"
    assert result["approval"]["status"] == "pending_approval"


def test_action_workflow_uses_user_requested_roads_and_assets_focus() -> None:
    run = RunRecord(
        run_id="run_test",
        region_id="state_nt",
        region_name="Northern Territory hotspot cluster focus",
        status="completed",
        risk_score=72,
        risk_level="HIGH",
        created_at=datetime.now(UTC),
        evidence={
            "official_warnings": {"source": "demo warnings", "data": {"warning_level": "ADVICE"}},
            "spatial": {
                "data": {
                    "critical_assets": ["Katherine Hospital", "Power substation"],
                    "protected_areas": ["Nitmiluk National Park"],
                    "roads": ["Stuart Highway", "Victoria Highway"],
                    "nearby_towns": ["Katherine"],
                }
            },
        },
    )

    result = draft_action(
        "Draft a public advisory for this alert, focus on alert the affected roads and assets.",
        run=run,
        requested_by="demo_officer",
    )

    draft = result["action"]["draft"]
    assert "Stuart Highway" in draft
    assert "Katherine Hospital" in draft
    assert "Nitmiluk National Park" in draft
    assert "ADVICE" in draft
    assert "Stuart Highway" in result["answer"]


def test_action_workflow_accepts_llm_custom_draft() -> None:
    result = draft_action(
        "Draft a public advisory for this alert.",
        run=None,
        requested_by="demo_officer",
        custom_draft="Custom LLM advisory text focused on affected roads and assets.",
    )

    assert result["action"]["draft"] == "Custom LLM advisory text focused on affected roads and assets."
    assert "Custom LLM advisory text" in result["answer"]
