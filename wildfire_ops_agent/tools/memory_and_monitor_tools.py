"""ADK tools for exact conversation-memory lookups and monitor-task creation."""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.services.conversation_memory import MemoryOperation, lookup_conversation_memory
from app.services.monitoring_tasks import create_monitor_task_from_chat
from wildfire_ops_agent.tools._shared import _chat_request_from_context, _stash_result


def conversation_memory_lookup_tool(
    user_request: str,
    operation: MemoryOperation,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Conversation Memory Tool: read exact prior-question, AOI, report, or action state without model inference."""
    request = _chat_request_from_context(tool_context, user_request)
    payload = lookup_conversation_memory(request, operation)
    payload["mode"] = "adk"
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(tool_context, intent="MEMORY_LOOKUP", payload=payload, run_id=request.run_id)
    return payload


def monitor_task_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Monitor Task Workflow: create a low-risk recurring AOI risk monitor with alert-on-change behavior."""
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
    payload = create_monitor_task_from_chat(request)
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(tool_context, intent="MONITOR_TASK", payload=payload)
    return payload
