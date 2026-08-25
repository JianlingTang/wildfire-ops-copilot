"""ADK tool for the hotspot heatmap/contour visualization workflow."""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.runtime.intent_responses import trace_for_intent
from app.services.hotspot_visualization import build_hotspot_visualization
from wildfire_ops_agent.tools._shared import _chat_request_from_context, _stash_result


def hotspot_visualization_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Hotspot Visualization Workflow: generate AOI heatmap cells, contour GeoJSON, interpretation, and downloads."""
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
    visualization = build_hotspot_visualization(request)
    payload: dict[str, Any] = {
        "status": "success",
        "mode": "adk",
        "answer": (
            f"Generated hotspot heatmap and contour analysis for {visualization['region']['region_name']}. "
            f"{visualization['interpretation']['summary']} The visualization is ready to download."
        ),
        "visualization": visualization,
    }
    payload["tool_trace"] = trace_for_intent("HOTSPOT_VISUALIZATION", payload, region_name=None)
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(tool_context, intent="HOTSPOT_VISUALIZATION", payload=payload)
    return payload
