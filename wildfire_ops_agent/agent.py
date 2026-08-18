from __future__ import annotations

import os

from google.adk.agents import LlmAgent

from wildfire_ops_agent.tools import (
    action_command_tool,
    analyst_question_tool,
    analyze_and_report_tool,
    conversation_memory_lookup_tool,
    deterministic_calculation_tool,
    exposure_action_tool,
    hotspot_visualization_tool,
    knowledge_retrieval_required_tool,
    monitor_task_tool,
    report_request_tool,
    risk_prediction_tool,
    risk_trend_tool,
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
        "select exactly one provided tool, and return a concise operator-facing answer. Do not invent tools or "
        "data, and never answer from model memory.\n"
        "\n"
        "Decision policy:\n"
        "- Every request must call exactly one tool. Direct, context-only, or model-memory answers are forbidden.\n"
        "- Prefer deterministic tools whenever one can perform the calculation, lookup, workflow, or state change.\n"
        "- Operational judgment and evidence synthesis questions must use their workflow tool even when context_json "
        "contains useful facts. "
        "This includes inspection priority, why risk is high, what changed, wind or weather change since yesterday, "
        "exposed assets, spatial exposure, roads, towns, protected areas, recommendations, or next operational steps.\n"
        "- If no deterministic tool can answer the exact request, call knowledge_retrieval_required_tool. Do not "
        "attempt the answer yourself.\n"
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
        "8. deterministic_calculation_tool: use for arithmetic, percent-change, or circular AOI-area calculations. "
        "Pass the operation and numeric values; do not calculate in the model.\n"
        "9. risk_trend_tool: use for an existing run's deterministic risk trend chart.\n"
        "10. risk_prediction_tool: use for the existing deterministic +5 day risk prediction artifact.\n"
        "11. exposure_action_tool: use for a combined exposure lookup plus public-safety draft request. It creates a "
        "pending approval only.\n"
        "12. knowledge_retrieval_required_tool: use for in-domain policy, procedure, or factual knowledge that none "
        "of the deterministic tools can answer. This is a safe RAG handoff and must not be replaced by model memory.\n"
        "13. conversation_memory_lookup_tool: use for exact conversation or persisted-state questions such as "
        "'what was my last question?', 'what is my selected AOI?', 'what was my report AOI?', or "
        "'what is my last action status?'. Pass exactly one operation: LAST_USER_QUESTION, ACTIVE_AOI, "
        "LATEST_REPORT_AOI, or LAST_ACTION_STATUS. Never infer these values from the compressed summary.\n"
        "\n"
        "Safety rules:\n"
        "- Never execute public communication, email, publishing, or field dispatch directly.\n"
        "- External actions require human approval even if the user asks to bypass approval.\n"
        "- If the request includes Focus AOI context, pass region_id, region_name, aoi_center, radius_km, "
        "run_id, and user_id into the selected workflow tool. Do not replace the selected AOI with another state.\n"
        "- If tool output includes structured facts, synthesize the final answer for the exact requested dimension.\n"
        "- If tool output includes missing baseline data, say what is missing instead of answering a nearby question.\n"
        "- If tool output includes tool_trace, preserve the same facts in your final summary.\n"
        "\n"
        "Return style:\n"
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
        deterministic_calculation_tool,
        risk_trend_tool,
        risk_prediction_tool,
        exposure_action_tool,
        knowledge_retrieval_required_tool,
        conversation_memory_lookup_tool,
    ],
)
