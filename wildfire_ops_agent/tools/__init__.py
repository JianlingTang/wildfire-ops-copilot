"""The 13 Google ADK FunctionTool implementations exposed to root_agent
(wildfire_ops_agent/agent.py). Grouped by family:

- analysis_tools.py: analyze_and_report, report_request, analyst_question,
  deterministic_calculation, risk_trend, risk_prediction,
  knowledge_retrieval_required.
- scenario_tools.py: what_if, action_command, exposure_action.
- visualization_tools.py: hotspot_visualization.
- memory_and_monitor_tools.py: conversation_memory_lookup, monitor_task.
- _shared.py: the request-building/state-stashing plumbing every tool uses.
"""

from __future__ import annotations

from wildfire_ops_agent.tools.analysis_tools import (
    analyst_question_tool,
    analyze_and_report_tool,
    deterministic_calculation_tool,
    knowledge_retrieval_required_tool,
    report_request_tool,
    risk_prediction_tool,
    risk_trend_tool,
)
from wildfire_ops_agent.tools.memory_and_monitor_tools import conversation_memory_lookup_tool, monitor_task_tool
from wildfire_ops_agent.tools.scenario_tools import action_command_tool, exposure_action_tool, what_if_tool
from wildfire_ops_agent.tools.visualization_tools import hotspot_visualization_tool

__all__ = [
    "analyze_and_report_tool",
    "what_if_tool",
    "action_command_tool",
    "report_request_tool",
    "analyst_question_tool",
    "deterministic_calculation_tool",
    "conversation_memory_lookup_tool",
    "risk_trend_tool",
    "risk_prediction_tool",
    "exposure_action_tool",
    "knowledge_retrieval_required_tool",
    "hotspot_visualization_tool",
    "monitor_task_tool",
]
