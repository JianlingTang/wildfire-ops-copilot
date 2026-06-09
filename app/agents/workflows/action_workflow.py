from app.models.schemas import RunRecord
from app.services.approval_policy import validate_action_type
from app.tools.approval_tools import create_pending_approval


def draft_action(
    message: str,
    run: RunRecord | None,
    requested_by: str,
    region_name: str | None = None,
) -> dict:
    action_type = _infer_action_type(message)
    validation = validate_action_type(action_type)
    if validation["status"] == "error":
        return validation
    action_region_name = run.region_name if run else region_name or "selected region"
    title = _title_for_action(action_type, action_region_name)
    draft = _draft_text(action_type, action_region_name, run)
    result = create_pending_approval(
        {
            "run_id": run.run_id if run else None,
            "alert_id": None,
            "action_type": action_type,
            "title": title,
            "draft": draft,
            "requested_by": requested_by,
        }
    )
    return {
        **result,
        "safety_note": "Draft created only. External execution requires human approval.",
    }


def _infer_action_type(message: str) -> str:
    lowered = message.lower()
    if "email" in lowered:
        return "emergency_services_email"
    if "field" in lowered or "brief" in lowered:
        return "field_team_brief"
    if "script" in lowered or "call" in lowered:
        return "call_script"
    if "task" in lowered:
        return "internal_task"
    return "public_advisory"


def _title_for_action(action_type: str, region_name: str) -> str:
    labels = {
        "emergency_services_email": "Emergency Services Email Draft",
        "field_team_brief": "Field Team Brief",
        "call_script": "Call Script",
        "internal_task": "Internal Task Draft",
        "public_advisory": "Public Advisory Draft",
    }
    return f"{labels[action_type]} - {region_name}"


def _draft_text(action_type: str, region_name: str, run: RunRecord | None) -> str:
    risk = f"{run.risk_level} ({run.risk_score}/100)" if run else "unscored"
    return (
        f"Draft for {region_name}: current wildfire operational risk is {risk}. "
        "Monitor official channels, avoid unnecessary travel through exposed areas, "
        "and await approved operational instructions. This draft is pending human review."
    )
