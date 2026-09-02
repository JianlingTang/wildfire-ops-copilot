"""Plumbing shared by every ADK FunctionTool: building a ChatRequest from the
LlmAgent's ToolContext state, resolving the active run, and stashing the
tool's result back into that state for app.runtime.adk.response to read."""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.models.schemas import Aoi, ChatRequest, RunRecord
from app.services.firestore_store import store


def _chat_request_from_context(
    tool_context: ToolContext,
    message: str,
    *,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> ChatRequest:
    center = aoi_center or tool_context.state.get("aoi_center")
    effective_radius_km = radius_km or tool_context.state.get("aoi_radius_km")
    aoi = None
    if isinstance(center, (list, tuple)) and len(center) == 2 and effective_radius_km:
        aoi = Aoi(center=(float(center[0]), float(center[1])), radius_km=float(effective_radius_km))
    return ChatRequest(
        message=message,
        conversation_id=_normalize_optional_str(tool_context.state.get("conversation_id")),
        run_id=_normalize_optional_str(run_id or tool_context.state.get("run_id")),
        region_id=str(region_id or tool_context.state.get("region_id", "live_australia")),
        region_name=_normalize_optional_str(region_name or tool_context.state.get("region_name")),
        aoi=aoi,
        user_id=str(user_id or tool_context.state.get("user_id", "demo_officer")),
    )


def _resolve_run(tool_context: ToolContext) -> RunRecord | None:
    run_id = _normalize_optional_str(tool_context.state.get("run_id"))
    if run_id and run_id in store.runs:
        return store.runs[run_id]
    region_id = _normalize_optional_str(tool_context.state.get("region_id"))
    return store.get_latest_run(region_id)


def _stash_result(
    tool_context: ToolContext,
    *,
    intent: str,
    payload: dict[str, Any],
    run_id: str | None = None,
    report_id: str | None = None,
    alert_id: str | None = None,
    action_id: str | None = None,
) -> None:
    tool_context.state["last_intent"] = intent
    tool_context.state["last_response_payload"] = payload
    if run_id:
        tool_context.state["last_run_id"] = run_id
        tool_context.state["run_id"] = run_id
    if report_id:
        tool_context.state["last_report_id"] = report_id
    if alert_id:
        tool_context.state["last_alert_id"] = alert_id
    if action_id:
        tool_context.state["last_action_id"] = action_id


def _normalize_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
