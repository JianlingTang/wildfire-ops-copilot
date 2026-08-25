"""The ANALYZE_AND_REPORT handler for the demo runtime."""

from __future__ import annotations

from typing import Any

from app.models.schemas import ChatRequest, RunRecord
from app.runtime.analysis import execute_analysis_request
from app.runtime.intent_responses import analysis_trace
from app.services.firestore_store import store


def _analyze_and_report(request: ChatRequest) -> dict[str, Any]:
    artifacts = execute_analysis_request(request, route_label="mock_demo_runtime")
    answer = _operator_summary(
        artifacts.run,
        artifacts.report.model_dump(),
        artifacts.alert.model_dump() if artifacts.alert else None,
    )
    store.add_event(
        artifacts.run.run_id,
        "mock_demo_runtime",
        "return_operator_summary",
        "completed",
        "Returned the operator summary and dashboard payload.",
    )
    return {
        "intent": "ANALYZE_AND_REPORT",
        "mode": "demo",
        "response": {
            "status": "success",
            "mode": "demo",
            "answer": answer,
            "recommendations": artifacts.run.recommendations,
            "evidence_source": "Elastic MCP demo evidence",
            "tool_trace": analysis_trace(artifacts.run, mode="demo"),
        },
        "run": artifacts.run,
        "report": artifacts.report,
        "alert": artifacts.alert,
    }


def _operator_summary(run_record: RunRecord, report: dict, alert: dict | None) -> str:
    alert_sentence = (
        "A high-risk alert was created for operator review." if alert else "No alert was created in this demo run."
    )
    return (
        f"{run_record.region_name} is currently {run_record.risk_level} at {run_record.risk_score}/100 "
        "after a chat-driven demo analysis. "
        "Elastic MCP demo evidence was queried as an operational evidence source alongside current "
        "hotspot, weather, warning, and exposure inputs. "
        f"The top recommendation is to {run_record.recommendations[0].lower()} "
        f"{report['title']} was generated and saved to the dashboard. {alert_sentence}"
    )
