from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from google.genai import types

from app.models.schemas import AlertRecord, Aoi, ChatRequest, ReportRecord
from app.runtime.adk import AdkRuntime, _public_intent
from app.services.firestore_store import store


class FakeEvent:
    def __init__(self, text: str) -> None:
        self.content = types.Content(role="model", parts=[types.Part(text=text)])

    def is_final_response(self) -> bool:
        return True


class FakeSessionService:
    def __init__(self) -> None:
        self.sessions: dict[tuple[str, str], SimpleNamespace] = {}

    async def get_session(self, *, app_name: str, user_id: str, session_id: str, config=None):
        del config
        return self.sessions.get((user_id, session_id))

    async def create_session(self, *, app_name: str, user_id: str, state=None, session_id: str | None = None):
        session = SimpleNamespace(app_name=app_name, user_id=user_id, id=session_id, state=state or {})
        self.sessions[(user_id, session_id or "default")] = session
        return session


class FakeRunner:
    def __init__(
        self,
        session_service: FakeSessionService,
        *,
        last_intent: str = "ANALYZE_AND_REPORT",
        payload: dict | None = None,
    ) -> None:
        self.session_service = session_service
        self.last_intent = last_intent
        self.payload = payload or {"status": "success", "mode": "adk", "answer": "placeholder"}
        self.called = False

    async def run_async(self, *, user_id: str, session_id: str, new_message, state_delta=None, **kwargs):
        del new_message, kwargs
        self.called = True
        session = await self.session_service.get_session(
            app_name="wildfire_ops_agent",
            user_id=user_id,
            session_id=session_id,
        )
        session.state.update(state_delta or {})
        session.state.update(
            {
                "last_intent": self.last_intent,
                "last_response_payload": self.payload,
                "last_run_id": "run_test",
                "last_report_id": "report_test",
                "last_alert_id": "alert_test",
            }
        )
        yield FakeEvent("LLM operator summary")


def test_adk_runtime_builds_dashboard_payload_from_session_state_for_freeform_question(monkeypatch) -> None:
    session_service = FakeSessionService()
    runner = FakeRunner(session_service)
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: runner)

    run = store.create_run("live_australia", "Australia Live Hotspot AOI")
    completed = store.complete_run(run.run_id, {}, {"risk_score": 72, "risk_level": "HIGH"}, ["Inspect first"])
    store.runs["run_test"] = completed.model_copy(update={"run_id": "run_test"})
    store.reports["report_test"] = ReportRecord(
        report_id="report_test",
        run_id="run_test",
        type="daily_brief",
        title="Daily Wildfire Operations Brief",
        markdown="# report",
        pdf_url=None,
        created_at=datetime.now(UTC),
    )
    store.alerts["alert_test"] = AlertRecord(
        alert_id="alert_test",
        run_id="run_test",
        region_id="live_australia",
        region_name="Australia Live Hotspot AOI",
        severity="HIGH",
        status="active",
        reason="test",
        evidence_ids=[],
        recommended_next_action="review",
        created_at=datetime.now(UTC),
    )

    result = AdkRuntime().route_chat(ChatRequest(message="Give me the current operating picture."))

    assert result["intent"] == "ANALYZE_AND_REPORT"
    assert result["mode"] == "adk"
    assert result["response"]["answer"] == "LLM operator summary"
    assert result["run"].run_id == "run_test"
    assert result["report"].report_id == "report_test"
    assert result["alert"].alert_id == "alert_test"


def test_adk_runtime_falls_back_when_runner_fails_for_freeform_question(monkeypatch) -> None:
    class BrokenRunner:
        async def run_async(self, **kwargs):
            del kwargs
            raise RuntimeError("missing vertex credentials")
            yield  # pragma: no cover

    session_service = FakeSessionService()
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: BrokenRunner())

    result = AdkRuntime().route_chat(ChatRequest(message="Give me the current operating picture."))

    assert result["mode"] == "adk"
    assert result["response"]["status"] == "needs_context"
    assert "missing vertex credentials" in result["response"]["tool_trace"][0]["output"]


def test_public_intent_prefers_deterministic_classifier_for_known_workflows() -> None:
    assert _public_intent("ANALYST_QA", "WHAT_IF") == "WHAT_IF"
    assert _public_intent("ANALYST_QA", "OPERATIONAL_PRIORITIZATION") == "OPERATIONAL_PRIORITIZATION"
    assert _public_intent("ANALYST_QA", "QUESTION") == "ANALYST_QA"


def test_adk_runtime_calls_root_runner_for_known_action_intent(monkeypatch) -> None:
    session_service = FakeSessionService()
    runner = FakeRunner(
        session_service,
        last_intent="ACTION_COMMAND",
        payload={
            "status": "success",
            "mode": "adk",
            "answer": "LLM selected Action Workflow.",
            "tool_trace": [
                {
                    "called": "Main Coordinator",
                    "did": "Selected Action Workflow.",
                    "output": "public_advisory",
                    "mode": "adk",
                    "status": "completed",
                }
            ],
        },
    )
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: runner)

    result = AdkRuntime().route_chat(ChatRequest(message="Draft a public advisory for this alert."))

    assert runner.called is True
    assert result["intent"] == "ACTION_COMMAND"
    assert result["response"]["answer"] == "LLM operator summary"
    assert result["response"]["tool_trace"][0]["called"] == "Main Coordinator"


def test_adk_runtime_falls_back_to_action_when_llm_does_not_call_tool(monkeypatch) -> None:
    class NoToolRunner:
        def __init__(self, session_service: FakeSessionService) -> None:
            self.session_service = session_service
            self.called = False

        async def run_async(self, *, user_id: str, session_id: str, new_message, state_delta=None, **kwargs):
            del new_message, kwargs
            self.called = True
            session = await self.session_service.get_session(
                app_name="wildfire_ops_agent",
                user_id=user_id,
                session_id=session_id,
            )
            session.state.update(state_delta or {})
            yield FakeEvent("I can draft that.")

    session_service = FakeSessionService()
    runner = NoToolRunner(session_service)
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: runner)
    run = store.create_run("state_nt", "Northern Territory hotspot cluster focus")
    completed = store.complete_run(run.run_id, {}, {"risk_score": 82, "risk_level": "HIGH"}, ["Inspect first"])

    result = AdkRuntime().route_chat(
        ChatRequest(message="Draft a public advisory for this alert.", run_id=completed.run_id)
    )

    assert runner.called is True
    assert result["intent"] == "ACTION_COMMAND"
    assert result["response"]["action"]["status"] == "pending_approval"
    assert result["response"]["approval"]["status"] == "pending_approval"
    assert "LLM did not call" in result["response"]["tool_trace"][0]["output"]
    assert len(store.actions) == 1


def test_adk_runtime_corrects_action_misroute_to_pending_approval(monkeypatch) -> None:
    session_service = FakeSessionService()
    runner = FakeRunner(
        session_service,
        last_intent="ANALYST_QA",
        payload={"status": "success", "mode": "adk", "answer": "This is only an analyst answer."},
    )
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: runner)

    result = AdkRuntime().route_chat(
        ChatRequest(
            message="Draft a public advisory for this alert.",
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
            aoi=Aoi(center=(-11.35, 132.12), radius_km=50),
        )
    )

    assert runner.called is True
    assert result["intent"] == "ACTION_COMMAND"
    assert result["response"]["action"]["status"] == "pending_approval"
    assert "corrected route" in result["response"]["tool_trace"][0]["output"]


def test_adk_runtime_action_command_uses_focused_region_name_without_run(monkeypatch) -> None:
    class NoToolRunner:
        async def run_async(self, *, user_id: str, session_id: str, new_message, state_delta=None, **kwargs):
            del user_id, session_id, new_message, state_delta, kwargs
            yield FakeEvent("No tool result")

    session_service = FakeSessionService()
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: NoToolRunner())

    result = AdkRuntime().route_chat(
        ChatRequest(
            message="Draft a public advisory for this alert.",
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
            aoi=Aoi(center=(-11.35, 132.12), radius_km=50),
        )
    )

    assert result["intent"] == "ACTION_COMMAND"
    assert result["response"]["action"]["title"] == "Public Advisory Draft - Northern Territory hotspot cluster focus"
    assert result["response"]["action"]["status"] == "pending_approval"


def test_adk_runtime_operational_prioritization_does_not_trigger_analysis(monkeypatch) -> None:
    session_service = FakeSessionService()
    runner = FakeRunner(
        session_service,
        last_intent="ANALYST_QA",
        payload={
            "status": "success",
            "mode": "adk",
            "answer": "Inspect the focused AOI first.",
            "tool_trace": [
                {
                    "called": "Analyst Agent",
                    "did": "Answered from Focus AOI context.",
                    "output": "success",
                    "mode": "adk",
                    "status": "completed",
                }
            ],
        },
    )

    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: runner)

    result = AdkRuntime().route_chat(
        ChatRequest(
            message="Which area should we inspect first?",
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
            aoi=Aoi(center=(-11.35, 132.12), radius_km=50),
        )
    )

    assert runner.called is True
    assert result["intent"] == "OPERATIONAL_PRIORITIZATION"
    assert result["response"]["status"] == "success"
    assert result["response"]["answer"] == "LLM operator summary"
    assert "run" not in result
    assert not store.runs
