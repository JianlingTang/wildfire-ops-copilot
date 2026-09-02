"""Stable tool identifiers for evaluation assertions.

Trace entries carry human-readable labels that get renamed during refactors.
Asserting on those labels makes the golden eval break when nothing about agent
behaviour changed -- a label rename once cost 9 false failures.

Golden cases assert a stable ``tool_id``. This registry is the single place that
maps an id to the display labels that satisfy it, including historical aliases,
so renaming a label means editing one tuple here instead of every golden case.
"""

from __future__ import annotations

# tool_id -> display labels accepted as evidence the tool ran.
# A tuple with several entries means the capability is served by any of them:
# either a historical alias, or a tool that was later decomposed.
TOOL_IDS: dict[str, tuple[str, ...]] = {
    "action_workflow": ("Action Workflow",),
    "analyst_qa": ("Analyst Agent", "Gemini Context Answer"),
    "conversation_memory": ("Conversation Memory Tool",),
    "deterministic_calculator": ("Deterministic Python Calculator",),
    "domain_scope_gate": ("Domain Scope Gate",),
    "external_data": ("External Data Tools",),
    "hotspot_visualization": ("Hotspot Density Tool", "Hotspot Visualization Tool"),
    "knowledge_retrieval_required": ("Knowledge Retrieval Required",),
    "main_coordinator": ("Main Coordinator",),
    "monitoring_scheduler": ("Monitoring Scheduler",),
    "report_agent": ("Report Agent",),
    "risk_timeseries": ("Risk Timeseries Tool",),
    "what_if": ("What-if Agent",),
}

# Reverse index for migrating existing golden files off display labels.
LABEL_TO_TOOL_ID: dict[str, str] = {
    label: tool_id for tool_id, labels in TOOL_IDS.items() for label in labels
}


def labels_for(tool_id: str) -> tuple[str, ...]:
    """Display labels that satisfy ``tool_id``. Unknown ids satisfy nothing."""
    return TOOL_IDS.get(tool_id, ())
