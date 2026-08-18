from __future__ import annotations

from typing import Any

from app.agents.specialists.analyst_agent import answer_operational_question
from app.agents.workflows.action_workflow import draft_action
from app.models.schemas import ChatRequest, RunRecord


def is_exposure_action_request(message: str) -> bool:
    lowered = message.lower()
    exposure_terms = [
        "asset",
        "assets",
        "road",
        "roads",
        "exposure",
        "exposed",
        "protected area",
        "protected areas",
    ]
    action_terms = ["generate", "create", "draft", "issue", "publish", "send", "alert", "advisory", "avoid"]
    public_safety_terms = ["alert", "advisory", "avoid", "warning", "people", "public"]
    return (
        any(term in lowered for term in exposure_terms)
        and any(term in lowered for term in action_terms)
        and any(term in lowered for term in public_safety_terms)
    )


def build_exposure_action_response(request: ChatRequest, run: RunRecord | None, *, mode: str) -> dict[str, Any]:
    exposure_payload = answer_operational_question(request.message, run, request.region_name, request.aoi)
    exposure_answer = _exposure_answer(exposure_payload, request)
    custom_draft = _avoidance_draft(request, run, exposure_answer)
    action_payload = draft_action(
        request.message,
        run,
        request.user_id,
        request.region_name,
        custom_draft=custom_draft,
    )
    action = action_payload.get("action", {}) if isinstance(action_payload.get("action"), dict) else {}
    approval = action_payload.get("approval", {}) if isinstance(action_payload.get("approval"), dict) else {}
    payload = {
        "status": "success",
        "mode": mode,
        "answer": (
            f"{exposure_answer}\n\n"
            f"Created a pending-approval public safety draft: {action.get('draft', custom_draft)} "
            "External publication still requires human approval."
        ),
        "decomposition": ["EXPOSURE_LOOKUP", "ACTION_COMMAND"],
        "exposure": exposure_payload,
        "exposure_answer": exposure_answer,
        "action": action,
        "approval": approval,
        "safety_note": action_payload.get("safety_note", "Draft created only. External execution requires approval."),
        "tool_trace": [
            _trace_item(
                "Main Coordinator",
                "Decomposed mixed request.",
                "Ran exposure lookup before creating an approval-gated public safety draft.",
                mode,
            ),
            _trace_item("Analyst Agent", "Answered roads and assets question.", exposure_payload.get("status"), mode),
            _trace_item(
                "Action Workflow",
                "Created draft action and approval record.",
                action.get("title", "Draft created."),
                mode,
            ),
            _trace_item(
                "Safety Boundary",
                "Blocked direct external publication.",
                approval.get("status", "Human approval required."),
                mode,
            ),
        ],
    }
    response: dict[str, Any] = {"intent": "EXPOSURE_ACTION", "mode": mode, "response": payload}
    if run:
        response["run"] = run
    return response


def _exposure_answer(payload: dict[str, Any], request: ChatRequest) -> str:
    if isinstance(payload.get("answer"), str) and payload["answer"].strip():
        return str(payload["answer"])
    raw_facts = payload.get("facts")
    facts: dict[str, Any] = raw_facts if isinstance(raw_facts, dict) else {}
    raw_current = facts.get("current")
    current: dict[str, Any] = raw_current if isinstance(raw_current, dict) else {}
    raw_spatial = current.get("spatial")
    spatial: dict[str, Any] = raw_spatial if isinstance(raw_spatial, dict) else {}
    region = current.get("region_name") or request.region_name or request.region_id or "the selected AOI"
    critical_assets = [str(item) for item in spatial.get("critical_assets", [])]
    protected_areas = [str(item) for item in spatial.get("protected_areas", [])]
    critical_text = _format_items(critical_assets, "no named critical assets returned")
    protected_text = _format_items(protected_areas, "no named protected or park areas returned")
    return (
        f"For {region}, spatial evidence returned {spatial.get('critical_asset_count', 0)} critical assets and "
        f"{spatial.get('protected_area_count', 0)} protected or park areas. Critical assets: {critical_text}. "
        f"Protected/park areas: {protected_text}. The current exposure tool does not enumerate named road corridors or "
        "town/settlement assets, so I will not claim specific roads or towns from this evidence."
    )


def _avoidance_draft(request: ChatRequest, run: RunRecord | None, exposure_answer: str) -> str:
    region = (run.region_name if run else None) or request.region_name or request.region_id or "the selected AOI"
    risk = f"{run.risk_level} ({run.risk_score}/100)" if run else "unscored"
    return (
        f"Public safety advisory draft for {region}. Current wildfire operational risk is {risk}. "
        "Avoid the affected area unless official emergency services advise otherwise. "
        f"Exposure context: {exposure_answer} "
        "Check official emergency channels for current warnings, road closures, and evacuation instructions. "
        "This draft is pending human approval and official-source verification before release."
    )


def _format_items(items: list[str], empty_text: str) -> str:
    if not items:
        return empty_text
    visible = items[:6]
    suffix = f", plus {len(items) - len(visible)} more" if len(items) > len(visible) else ""
    return "; ".join(visible) + suffix


def _trace_item(called: str, did: str, output: Any, mode: str) -> dict[str, Any]:
    return {
        "called": called,
        "did": did,
        "output": str(output or ""),
        "mode": mode,
        "status": "completed",
    }
