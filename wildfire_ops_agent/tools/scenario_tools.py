"""ADK tools for what-if scenarios, drafted actions, and exposure+action."""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.agents.specialists.what_if_agent import run_what_if
from app.agents.workflows.action_workflow import draft_action
from app.runtime.intent_responses import trace_for_intent
from app.services.mixed_intents import build_exposure_action_response
from wildfire_ops_agent.tools._shared import _chat_request_from_context, _resolve_run, _stash_result


def what_if_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """What-if Workflow: parse scenario changes and compare baseline risk with scenario risk."""
    run = _resolve_run(tool_context)
    request = _chat_request_from_context(
        tool_context,
        user_request,
        region_name=region_name,
        region_id=region_id,
        aoi_center=aoi_center,
        radius_km=radius_km,
        run_id=run_id,
        user_id=user_id,
    )
    payload = run_what_if(user_request, run, request.region_name, request.aoi)
    payload["mode"] = "adk"
    payload["tool_trace"] = trace_for_intent("WHAT_IF", payload, region_name=request.region_name or request.region_id)
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(tool_context, intent="WHAT_IF", payload=payload, run_id=run.run_id if run else None)
    return payload


def action_command_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
    custom_draft: str | None = None,
) -> dict[str, Any]:
    """Action Workflow: draft operator action text and create a pending human approval record."""
    run = _resolve_run(tool_context)
    request = _chat_request_from_context(
        tool_context,
        user_request,
        region_name=region_name,
        region_id=region_id,
        aoi_center=aoi_center,
        radius_km=radius_km,
        run_id=run_id,
        user_id=user_id,
    )
    requested_by = request.user_id or str(tool_context.state.get("app:user_id", "demo_officer"))
    payload = draft_action(user_request, run, requested_by, request.region_name, custom_draft=custom_draft)
    payload["mode"] = "adk"
    action = payload.get("action") or {}
    payload["tool_trace"] = trace_for_intent("ACTION_COMMAND", payload, region_name=request.region_name)
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(
        tool_context,
        intent="ACTION_COMMAND",
        payload=payload,
        run_id=run.run_id if run else None,
        action_id=action.get("action_id"),
    )
    return payload


def exposure_action_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Exposure + Action Tool: look up exposure then create one approval-gated public-safety draft."""
    request = _chat_request_from_context(
        tool_context,
        user_request,
        region_name=region_name,
        region_id=region_id,
        aoi_center=aoi_center,
        radius_km=radius_km,
        run_id=run_id,
        user_id=user_id,
    )
    run = _resolve_run(tool_context)
    response = build_exposure_action_response(request, run, mode="adk")
    payload = response["response"]
    payload["tool_summary"] = payload["tool_trace"][-1]
    action = payload.get("action") or {}
    _stash_result(
        tool_context,
        intent="EXPOSURE_ACTION",
        payload=payload,
        run_id=run.run_id if run else None,
        action_id=action.get("action_id"),
    )
    return payload
