from app.models.schemas import RunRecord
from app.services.approval_policy import validate_action_type
from app.tools.approval_tools import create_pending_approval


def draft_action(
    message: str,
    run: RunRecord | None,
    requested_by: str,
    region_name: str | None = None,
    custom_draft: str | None = None,
) -> dict:
    action_type = _infer_action_type(message)
    validation = validate_action_type(action_type)
    if validation["status"] == "error":
        return validation
    action_region_name = run.region_name if run else region_name or "selected region"
    title = _title_for_action(action_type, action_region_name)
    draft = (
        custom_draft.strip()
        if custom_draft and custom_draft.strip()
        else _draft_text(message, action_type, action_region_name, run)
    )
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
        "answer": f"Created a pending-approval {action_type.replace('_', ' ')} draft: {draft}",
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


def _draft_text(message: str, action_type: str, region_name: str, run: RunRecord | None) -> str:
    risk = f"{run.risk_level} ({run.risk_score}/100)" if run else "unscored"
    lower_message = message.lower()
    exposure = _exposure_context(run)
    warning_status = _warning_status(run)
    audience = _audience_for_action(action_type)
    lines = [
        f"{audience} draft for {region_name}.",
        f"Current wildfire operational risk is {risk}. {warning_status}",
    ]
    if "road" in lower_message:
        lines.append(_road_sentence(exposure["roads"]))
    if "asset" in lower_message or "infrastructure" in lower_message:
        lines.append(_asset_sentence(exposure["assets"], exposure["protected_areas"], exposure["towns"]))
    if action_type == "field_team_brief":
        lines.append(
            "Use this as an internal brief only; confirm access, crew safety, and official incident updates before "
            "fielding tasks."
        )
    elif action_type == "emergency_services_email":
        lines.append(
            "Please verify official warning status and local access constraints before any external distribution."
        )
    elif action_type == "call_script":
        lines.append(
            "Operator note: keep this script informational and refer emergency instructions to the responsible agency."
        )
    else:
        lines.append(
            "Check official emergency channels for current warnings and follow instructions from responsible agencies."
        )
    lines.append("This draft is pending human approval and official-source verification before release.")
    return " ".join(lines)


def _audience_for_action(action_type: str) -> str:
    labels = {
        "emergency_services_email": "Emergency services email",
        "field_team_brief": "Field team brief",
        "call_script": "Call script",
        "internal_task": "Internal task",
        "public_advisory": "Public advisory",
    }
    return labels.get(action_type, "Action")


def _exposure_context(run: RunRecord | None) -> dict[str, list[str]]:
    spatial = run.evidence.get("spatial", {}) if run else {}
    data = spatial.get("data", {}) if isinstance(spatial, dict) else {}
    return {
        "assets": _string_list(data.get("critical_assets", [])),
        "protected_areas": _string_list(data.get("protected_areas", [])),
        "roads": _string_list(data.get("roads", [])),
        "towns": _string_list(data.get("nearby_towns", [])),
    }


def _warning_status(run: RunRecord | None) -> str:
    warnings = run.evidence.get("official_warnings", {}) if run else {}
    data = warnings.get("data", {}) if isinstance(warnings, dict) else {}
    level = data.get("warning_level") or data.get("status")
    source = warnings.get("source") if isinstance(warnings, dict) else None
    if level:
        return f"Official warning status to verify: {level}."
    if source:
        return f"Official warning feed checked via {source}; verify before release."
    return "Official warning status is unavailable in the current evidence."


def _road_sentence(roads: list[str]) -> str:
    if roads:
        return (
            f"Affected road watchlist: {_join_limited(roads)}; confirm closures or access restrictions with official "
            "road and fire agencies."
        )
    return (
        "Affected roads were requested, but no road watchlist is available in the current evidence; verify access "
        "routes before publication."
    )


def _asset_sentence(assets: list[str], protected_areas: list[str], towns: list[str]) -> str:
    parts = []
    if assets:
        parts.append(f"critical assets: {_join_limited(assets)}")
    if protected_areas:
        parts.append(f"protected areas: {_join_limited(protected_areas)}")
    if towns:
        parts.append(f"nearby towns: {_join_limited(towns)}")
    if not parts:
        return (
            "Affected assets were requested, but no asset watchlist is available in the current evidence; verify local "
            "exposure before publication."
        )
    return f"Affected asset watchlist includes {'; '.join(parts)}."


def _string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if value]


def _join_limited(values: list[str], limit: int = 4) -> str:
    visible = values[:limit]
    suffix = f", plus {len(values) - limit} more" if len(values) > limit else ""
    return ", ".join(visible) + suffix
