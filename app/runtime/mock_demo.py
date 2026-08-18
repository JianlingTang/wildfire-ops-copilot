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
from app.services.agent_events import new_trace_id, publish_agent_event
from app.services.chat_conversations import (
    analysis_required_response,
    finalize_chat_response,
    prepare_conversation,
    should_block_for_analysis,
)
from app.services.conversation_memory import lookup_conversation_memory, memory_operation_for_message
from app.services.deterministic_calculator import calculation_response_from_message
from app.services.firestore_store import store
from app.services.hotspot_visualization import build_hotspot_visualization
from app.services.mixed_intents import build_exposure_action_response, is_exposure_action_request
from app.services.monitoring_tasks import create_monitor_task_from_chat
from app.services.request_scope import is_wildfire_operations_request, out_of_scope_response
from app.services.risk_trend import build_risk_prediction_response, build_risk_trend_response


class MockDemoRuntime(AgentRuntime):
    def run_daily(self) -> dict:
        request = ManualRunRequest(region_id=settings.demo_region_id, region_name=settings.demo_region_name)
        return run_daily_intelligence(request, trigger_type="daily")

    def run_manual(self, request: ManualRunRequest) -> dict:
        return run_daily_intelligence(request, trigger_type="manual")

    def route_chat(self, request: ChatRequest) -> dict:
        if not is_wildfire_operations_request(request):
            return out_of_scope_response(mode="demo")
        conversation, request = prepare_conversation(request)
        trace_id = new_trace_id()
        intent = classify_intent(request.message)
        _publish_chat_event(
            trace_id, request, conversation.conversation_id, "started", "Coordinator received chat request.", intent
        )
        _publish_chat_event(
            trace_id, request, conversation.conversation_id, "completed", f"Intent classified: {intent}.", intent
        )
        if should_block_for_analysis(intent, request, conversation):
            _publish_chat_event(
                trace_id,
                request,
                conversation.conversation_id,
                "blocked",
                "Analysis gate blocked request before workflow tool calls.",
                intent,
            )
            return analysis_required_response(request, conversation, intent, mode="demo", trace_id=trace_id)
        _publish_chat_event(
            trace_id, request, conversation.conversation_id, "completed", "Analysis gate passed.", intent
        )

        run = store.runs.get(request.run_id) if request.run_id else store.get_latest_run(request.region_id)
        if run is None and request.region_id == settings.demo_region_id:
            run = store.get_latest_run()

        if intent == "MEMORY_LOOKUP":
            operation = memory_operation_for_message(request.message)
            if operation is None:
                payload: dict = {
                    "status": "invalid_input",
                    "answer": "No supported deterministic memory lookup matched this request.",
                    "memory": None,
                    "tool_trace": [],
                }
            else:
                payload = lookup_conversation_memory(request, operation)
            payload["mode"] = "demo"
            return finalize_chat_response(
                request,
                conversation,
                {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id},
            )

        if intent == "CALCULATION":
            payload = calculation_response_from_message(request.message, mode="demo")
            return finalize_chat_response(
                request,
                conversation,
                {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id},
            )

        if intent == "KNOWLEDGE_REQUIRED":
            payload = _knowledge_required_response(request.message, mode="demo")
            return finalize_chat_response(
                request,
                conversation,
                {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id},
            )

        if is_exposure_action_request(request.message):
            response = build_exposure_action_response(request, run, mode="demo")
            response["trace_id"] = trace_id
            _publish_artifact_event(
                trace_id,
                request,
                conversation.conversation_id,
                "approval",
                "Approval requested for mixed exposure/action request.",
                "EXPOSURE_ACTION",
            )
            return finalize_chat_response(request, conversation, response)

        if intent == "ANALYZE_AND_REPORT":
            _publish_artifact_event(
                trace_id, request, conversation.conversation_id, "analysis", "Analysis workflow started.", intent
            )
            response = self._analyze_and_report(request)
            response["trace_id"] = trace_id
            return finalize_chat_response(request, conversation, response)
        if intent == "RISK_TREND":
            payload = build_risk_trend_response(request, run, mode="demo")
            _publish_artifact_event(
                trace_id, request, conversation.conversation_id, "visualization", "Risk trend chart generated.", intent
            )
            return finalize_chat_response(
                request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
            )
        if intent == "RISK_PREDICTION":
            payload = build_risk_prediction_response(request, run, mode="demo")
            _publish_artifact_event(
                trace_id, request, conversation.conversation_id, "risk", "Risk prediction generated.", intent
            )
            return finalize_chat_response(
                request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
            )
        if intent == "HOTSPOT_VISUALIZATION":
            visualization = build_hotspot_visualization(request)
            response = {
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
            _publish_artifact_event(
                trace_id,
                request,
                conversation.conversation_id,
                "visualization",
                "Hotspot visualization artifact generated.",
                intent,
            )
            response["trace_id"] = trace_id
            return finalize_chat_response(request, conversation, response)
        if intent == "MONITOR_TASK":
            payload = create_monitor_task_from_chat(request)
            payload["mode"] = "demo"
            _publish_artifact_event(
                trace_id, request, conversation.conversation_id, "monitor", "Monitor task created.", intent
            )
            return finalize_chat_response(
                request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
            )
        if intent == "WHAT_IF":
            payload = run_what_if(request.message, run, request.region_name, request.aoi)
            payload.setdefault(
                "tool_trace",
                _tool_trace_for_demo_question("What-if Agent", str(payload.get("answer") or "scenario complete")),
            )
            return finalize_chat_response(request, conversation, {
                "intent": intent,
                "mode": "demo",
                "response": payload,
                "trace_id": trace_id,
            })
        if intent == "ACTION_COMMAND":
            payload = draft_action(request.message, run, request.user_id, request.region_name)
            payload.setdefault(
                "tool_trace",
                _tool_trace_for_demo_question("Action Workflow", str(payload.get("safety_note") or "draft created")),
            )
            _publish_artifact_event(
                trace_id,
                request,
                conversation.conversation_id,
                "approval",
                "Approval requested for drafted action.",
                intent,
            )
            return finalize_chat_response(request, conversation, {
                "intent": intent,
                "mode": "demo",
                "response": payload,
                "trace_id": trace_id,
            })
        if intent == "REPORT_REQUEST":
            result = create_report_for_run(run)
            result.setdefault(
                "tool_trace", _tool_trace_for_demo_question("Report Agent", result.get("status", "report request"))
            )
            if result.get("status") == "success":
                result["answer"] = "Generated a fresh operations brief from the latest completed run in demo mode."
                return finalize_chat_response(
                    request,
                    conversation,
                    {
                        "intent": intent,
                        "mode": "demo",
                        "response": result,
                        "report": result["report"],
                        "trace_id": trace_id,
                    },
                )
            return finalize_chat_response(
                request, conversation, {"intent": intent, "mode": "demo", "response": result, "trace_id": trace_id}
            )
        payload = answer_operational_question(request.message, run, request.region_name, request.aoi)
        payload.setdefault(
            "tool_trace",
            _tool_trace_for_demo_question("Gemini Context Answer", str(payload.get("status") or "success")),
        )
        return finalize_chat_response(request, conversation, {
            "intent": intent,
            "mode": "demo",
            "response": payload,
            "trace_id": trace_id,
        })

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
                "tool_trace": [
                    {
                        "called": "Main Coordinator",
                        "did": "Selected Analysis Workflow.",
                        "output": artifacts.run.region_name,
                        "mode": "demo",
                        "status": "completed",
                    },
                    {
                        "called": "External Data Tools",
                        "did": "Called hotspot, weather, warning, and exposure tools.",
                        "output": f"{artifacts.run.risk_level} {artifacts.run.risk_score}/100.",
                        "mode": "demo",
                        "status": "completed",
                    },
                    {
                        "called": "Elastic MCP Tool",
                        "did": "Queried operational evidence.",
                        "output": "Elastic MCP demo evidence.",
                        "mode": "demo",
                        "status": "completed",
                    },
                ],
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


def _knowledge_required_response(message: str, *, mode: str) -> dict:
    return {
        "status": "knowledge_required",
        "mode": mode,
        "answer": (
            "This wildfire question requires verified document retrieval, but the production RAG pipeline is not "
            "enabled in this phase. I will not answer from model memory."
        ),
        "requires_rag": True,
        "query": message,
        "tool_trace": [
            {
                "called": "Knowledge Retrieval Required",
                "did": "Stopped before generation because no deterministic tool can answer the request.",
                "output": "Verified document retrieval is required.",
                "mode": mode,
                "status": "blocked",
            }
        ],
    }


def _tool_trace_for_demo_question(agent: str, output: str) -> list[dict]:
    return [
        {
            "called": "Main Coordinator",
            "did": f"Selected {agent}.",
            "output": output,
            "mode": "demo",
            "status": "completed",
        }
    ]


def _publish_chat_event(
    trace_id: str,
    request: ChatRequest,
    conversation_id: str,
    status: str,
    message: str,
    intent: str,
) -> None:
    publish_agent_event(
        trace_id=trace_id,
        conversation_id=conversation_id,
        run_id=request.run_id,
        region_id=request.region_id,
        agent_type="coordinator",
        status=status,
        message=message,
        data={"intent": intent, "mode": "demo"},
    )


def _publish_artifact_event(
    trace_id: str,
    request: ChatRequest,
    conversation_id: str,
    agent_type: str,
    message: str,
    intent: str,
) -> None:
    publish_agent_event(
        trace_id=trace_id,
        conversation_id=conversation_id,
        run_id=request.run_id,
        region_id=request.region_id,
        agent_type=agent_type,
        status="completed",
        message=message,
        data={"intent": intent, "mode": "demo"},
    )
