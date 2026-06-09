from __future__ import annotations

from app.agents.specialists.analyst_agent import answer_operational_question
from app.agents.specialists.report_agent import create_report_for_run
from app.agents.specialists.what_if_agent import run_what_if
from app.agents.workflows.action_workflow import draft_action
from app.agents.workflows.daily_intelligence import run_daily_intelligence
from app.config.settings import settings
from app.models.schemas import ChatRequest, ManualRunRequest, RunRecord
from app.runtime.analysis import execute_analysis_request
from app.runtime.base import AgentRuntime
from app.runtime.intents import classify_intent
from app.services.firestore_store import store
from app.services.hotspot_visualization import build_hotspot_visualization
from app.services.monitoring_tasks import create_monitor_task_from_chat


class MockDemoRuntime(AgentRuntime):
    def run_daily(self) -> dict:
        request = ManualRunRequest(region_id=settings.demo_region_id, region_name=settings.demo_region_name)
        return run_daily_intelligence(request, trigger_type="daily")

    def run_manual(self, request: ManualRunRequest) -> dict:
        return run_daily_intelligence(request, trigger_type="manual")

    def route_chat(self, request: ChatRequest) -> dict:
        intent = classify_intent(request.message)
        run = store.runs.get(request.run_id) if request.run_id else store.get_latest_run(request.region_id)
        if run is None and request.region_id == settings.demo_region_id:
            run = store.get_latest_run()

        if intent == "ANALYZE_AND_REPORT":
            return self._analyze_and_report(request)
        if intent == "HOTSPOT_VISUALIZATION":
            visualization = build_hotspot_visualization(request)
            return {
                "intent": intent,
                "mode": "demo",
                "response": {
                    "status": "success",
                    "mode": "demo",
                    "answer": (
                        f"Generated hotspot heatmap and contour analysis for "
                        f"{visualization['region']['region_name']}. "
                        f"{visualization['interpretation']['summary']} The visualization is ready to download."
                    ),
                    "visualization": visualization,
                    "tool_trace": [
                        {
                            "called": "Hotspot Visualization Tool",
                            "did": "Generated heatmap cells and contour bands.",
                            "output": visualization["interpretation"]["priority"],
                            "mode": "demo",
                            "status": "completed",
                        }
                    ],
                },
            }
        if intent == "MONITOR_TASK":
            payload = create_monitor_task_from_chat(request)
            payload["mode"] = "demo"
            return {"intent": intent, "mode": "demo", "response": payload}
        if intent == "WHAT_IF":
            return {
                "intent": intent,
                "mode": "demo",
                "response": run_what_if(request.message, run, request.region_name, request.aoi),
            }
        if intent == "ACTION_COMMAND":
            return {
                "intent": intent,
                "mode": "demo",
                "response": draft_action(request.message, run, request.user_id, request.region_name),
            }
        if intent == "REPORT_REQUEST":
            result = create_report_for_run(run)
            if result.get("status") == "success":
                result["answer"] = "Generated a fresh operations brief from the latest completed run in demo mode."
                return {"intent": intent, "mode": "demo", "response": result, "report": result["report"]}
            return {"intent": intent, "mode": "demo", "response": result}
        return {
            "intent": intent,
            "mode": "demo",
            "response": answer_operational_question(request.message, run, request.region_name, request.aoi),
        }

    def _analyze_and_report(self, request: ChatRequest) -> dict:
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
            },
            "run": artifacts.run,
            "report": artifacts.report,
            "alert": artifacts.alert,
        }


def _operator_summary(run_record: RunRecord, report: dict, alert: dict | None) -> str:
    alert_sentence = (
        "A high-risk alert was created for operator review."
        if alert
        else "No alert was created in this demo run."
    )
    return (
        f"{run_record.region_name} is currently {run_record.risk_level} at {run_record.risk_score}/100 "
        "after a chat-driven demo analysis. "
        "Elastic MCP demo evidence was queried as an operational evidence source alongside current "
        "hotspot, weather, warning, and exposure inputs. "
        f"The top recommendation is to {run_record.recommendations[0].lower()} "
        f"{report['title']} was generated and saved to the dashboard. {alert_sentence}"
    )
