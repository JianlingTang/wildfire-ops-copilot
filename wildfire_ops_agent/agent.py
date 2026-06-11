from __future__ import annotations

import os

from google.adk.agents import LlmAgent

from wildfire_ops_agent.tools import (
    action_command_tool,
    analyst_question_tool,
    analyze_and_report_tool,
    hotspot_visualization_tool,
    monitor_task_tool,
    report_request_tool,
    what_if_tool,
)

MODEL = os.getenv("ADK_GEMINI_MODEL", "gemini-2.5-flash")


analysis_agent = LlmAgent(
    model=MODEL,
    name="analysis_agent",
    description="Runs wildfire analysis for the selected AOI and generates an operational report.",
    instruction=(
        "You handle requests to analyze the selected wildfire area, generate a report, and summarize the outcome.\n"
        "Tool: analyze_and_report_tool\n"
        "- Use when the user asks to analyze, run analysis, generate today's report, or produce an operations brief.\n"
        "- Requires Focus AOI context from state when available.\n"
        "- Output must include risk score, risk level, report status, alert status, and Elastic MCP mode.\n"
        "Always call analyze_and_report_tool exactly once, then give a concise operator summary."
    ),
    tools=[analyze_and_report_tool],
)

what_if_agent = LlmAgent(
    model=MODEL,
    name="what_if_agent",
    description="Runs what-if wildfire scenarios against the latest completed run.",
    instruction=(
        "You handle scenario-analysis questions.\n"
        "Tool: what_if_tool\n"
        "- Use when the user asks what-if, scenario, wind/rain/humidity changes, or condition changes.\n"
        "- Output must include parsed scenario, risk comparison when available, and operational recommendation.\n"
        "Always call what_if_tool exactly once, then summarize in direct operational language."
    ),
    tools=[what_if_tool],
)

action_agent = LlmAgent(
    model=MODEL,
    name="action_agent",
    description="Drafts actions and places them into the human approval workflow.",
    instruction=(
        "You handle action commands such as public advisories, emails, briefs, scripts, and internal tasks.\n"
        "Tool: action_command_tool\n"
        "- Use when the user asks to draft, send, publish, email, brief, call, script, task, or create an action.\n"
        "- The tool drafts only and creates pending approval. It must not execute external actions.\n"
        "- Write a custom_draft that follows the user's requested focus and wording, using current context when "
        "available. "
        "If the user asks to change or refocus a draft, pass the revised text as custom_draft.\n"
        "Always call action_command_tool exactly once. Make clear that external execution requires human approval."
    ),
    tools=[action_command_tool],
)

report_agent = LlmAgent(
    model=MODEL,
    name="report_agent",
    description="Generates a fresh report from the latest completed run.",
    instruction=(
        "You handle explicit report-generation requests for an existing completed run.\n"
        "Tool: report_request_tool\n"
        "- Use when the user asks for a fresh report from the latest run but is not asking to run new analysis.\n"
        "- Output must confirm whether a report was generated and saved.\n"
        "Always call report_request_tool exactly once."
    ),
    tools=[report_request_tool],
)

analyst_agent = LlmAgent(
    model=MODEL,
    name="analyst_agent",
    description="Answers wildfire operational questions using the latest run context.",
    instruction=(
        "You answer analyst-style questions such as why risk is high, what changed, or where to inspect first.\n"
        "Tool: analyst_question_tool\n"
        "- Use for operational questions that do not request a new analysis, scenario calculation, report, or action.\n"
        "- Output must be grounded in the latest run or Focus AOI context.\n"
        "Always call analyst_question_tool exactly once and answer using the returned context."
    ),
    tools=[analyst_question_tool],
)

root_agent = LlmAgent(
    model=MODEL,
    name="root_agent",
    description="Wildfire operations orchestrator for analysis, what-if, action, report, and analyst workflows.",
    instruction=(
        "You are the wildfire operations main coordinator. Your job is to reason about the operator request, "
        "decide whether a workflow tool is required, and return a concise operator-facing answer. Do not invent "
        "tools or data.\n"
        "\n"
        "Decision policy:\n"
        "- Direct context-only answers are allowed only for factual lookups such as AOI center, radius, selected "
        "state, "
        "latest run id, risk score, report metadata, or existing Elastic evidence file names already present in "
        "context_json.\n"
        "- Operational judgment and evidence synthesis questions must use their workflow tool even when context_json "
        "contains useful facts. "
        "This includes inspection priority, why risk is high, what changed, wind or weather change since yesterday, "
        "exposed assets, spatial exposure, roads, towns, protected areas, recommendations, or next operational steps.\n"
        "- If context_json lacks the answer, say exactly what is missing.\n"
        "- Call a workflow tool only when the request requires computation, fresh retrieval, report generation, "
        "visualization, monitoring, approval-gated actions, or state changes.\n"
        "\n"
        "Workflow tool catalog. When a tool is required, call exactly one of these tool names:\n"
        "1. analyze_and_report_tool: use for 'analyze this region', 'run analysis', 'generate today's report', "
        "or requests that need live hotspot/weather/warning/exposure/Elastic evidence and a saved report.\n"
        "2. what_if_tool: use for hypothetical scenarios, especially changes to wind, humidity, rainfall, "
        "temperature, or future conditions. Example: 'What if wind increases by 30%?'\n"
        "3. action_command_tool: use for any action command: draft, send, publish, email, brief, call script, "
        "task, or public advisory. This workflow creates a draft and pending approval only. Pass custom_draft when "
        "the user asks for specific wording, focus, or a revision.\n"
        "4. report_request_tool: use only when the user asks for a fresh report from an already completed run, "
        "without asking to run new analysis.\n"
        "5. analyst_question_tool: always use for operational judgment or evidence synthesis questions such as "
        "'why is risk high?', 'what changed?', 'how did wind change since yesterday?', "
        "'which area should we inspect first?', 'what exposed assets are in the AOI?', recommendations, or next "
        "operational steps.\n"
        "6. hotspot_visualization_tool: use when the user asks for heatmap, contour, visualization, density map, "
        "or downloadable hotspot map analysis.\n"
        "7. monitor_task_tool: use when the user asks to create a monitor task, monitor a state/AOI at a requested "
        "cadence, "
        "or refresh risk repeatedly with alert-on-change behavior.\n"
        "\n"
        "Safety rules:\n"
        "- Never execute public communication, email, publishing, or field dispatch directly.\n"
        "- External actions require human approval even if the user asks to bypass approval.\n"
        "- Context-only answers must not create records, approvals, reports, monitors, visualizations, or external "
        "actions.\n"
        "- If the request includes Focus AOI context, pass region_id, region_name, aoi_center, radius_km, "
        "run_id, and user_id into the selected workflow tool. Do not replace the selected AOI with another state.\n"
        "- If tool output includes structured facts, synthesize the final answer for the exact requested dimension.\n"
        "- If tool output includes missing baseline data, say what is missing instead of answering a nearby question.\n"
        "- If tool output includes tool_trace, preserve the same facts in your final summary.\n"
        "\n"
        "Return style:\n"
        "- For context-only answers, say the answer came from current context and no external tools were called.\n"
        "- For workflow answers, mention which workflow was selected and summarize what was called.\n"
        "- Keep the final answer short."
    ),
    tools=[
        analyze_and_report_tool,
        what_if_tool,
        action_command_tool,
        report_request_tool,
        analyst_question_tool,
        hotspot_visualization_tool,
        monitor_task_tool,
    ],
)
