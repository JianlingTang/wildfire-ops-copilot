from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from google.genai import types

from app.agents.specialists.analyst_agent import answer_operational_question
from app.models.schemas import AlertRecord, Aoi, ChatRequest, ReportRecord
from app.runtime.adk import AdkRuntime, _message_with_operational_context, _public_intent
from app.runtime.intents import classify_intent
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


def test_adk_runtime_returns_error_when_runner_fails_for_freeform_question(monkeypatch) -> None:
    class BrokenRunner:
        async def run_async(self, **kwargs):
            del kwargs
            raise RuntimeError("missing vertex credentials")
            yield  # pragma: no cover

    session_service = FakeSessionService()
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: BrokenRunner())
    run = store.create_run("live_australia", "Australia Live Hotspot AOI")
    completed = store.complete_run(run.run_id, {}, {"risk_score": 72, "risk_level": "HIGH"}, ["Inspect first"])

    result = AdkRuntime().route_chat(
        ChatRequest(message="Give me the current operating picture.", run_id=completed.run_id)
    )

    assert result["mode"] == "adk"
    assert result["response"]["status"] == "error"
    assert "missing vertex credentials" in result["response"]["tool_trace"][0]["output"]


def test_adk_runtime_retries_429_resource_exhausted(monkeypatch) -> None:
    class RateLimitedRunner:
        def __init__(self, session_service: FakeSessionService) -> None:
            self.session_service = session_service
            self.call_count = 0

        async def run_async(self, *, user_id: str, session_id: str, new_message, state_delta=None, **kwargs):
            del new_message, kwargs
            self.call_count += 1
            if self.call_count == 1:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            session = await self.session_service.get_session(
                app_name="wildfire_ops_agent",
                user_id=user_id,
                session_id=session_id,
            )
            session.state.update(state_delta or {})
            session.state.update(
                {
                    "last_intent": "ANALYST_QA",
                    "last_response_payload": {
                        "status": "success",
                        "mode": "adk",
                        "answer": "Inspect the focused AOI first after retry.",
                    },
                }
            )
            yield FakeEvent("LLM retry answer")

    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    session_service = FakeSessionService()
    runner = RateLimitedRunner(session_service)
    monkeypatch.setenv("ADK_GEMINI_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("ADK_GEMINI_RETRY_BASE_DELAY_SECONDS", "0.25")
    monkeypatch.setattr("app.runtime.adk.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: runner)
    run = store.create_run("state_nt", "Northern Territory hotspot cluster focus")
    completed = store.complete_run(run.run_id, {}, {"risk_score": 82, "risk_level": "HIGH"}, ["Inspect first"])

    result = AdkRuntime().route_chat(
        ChatRequest(
            message="Which area should we inspect first?",
            run_id=completed.run_id,
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
        )
    )

    assert runner.call_count == 2
    assert delays == [0.25]
    assert result["intent"] == "OPERATIONAL_PRIORITIZATION"
    assert result["response"]["status"] == "success"
    assert result["response"]["answer"] == "LLM retry answer"


def test_public_intent_prefers_deterministic_classifier_for_known_workflows() -> None:
    assert _public_intent("ANALYST_QA", "WHAT_IF") == "WHAT_IF"
    assert _public_intent("ANALYST_QA", "OPERATIONAL_PRIORITIZATION") == "OPERATIONAL_PRIORITIZATION"
    assert _public_intent("ANALYST_QA", "QUESTION") == "ANALYST_QA"


def test_classifier_routes_exposure_lookup_to_analyst_tool() -> None:
    assert classify_intent("What exposed road and town assets are within the selected AOI?") == "EXPOSURE_LOOKUP"


def test_analyst_answers_spatial_exposure_from_run_evidence() -> None:
    run = store.create_run("state_nt", "Northern Territory hotspot cluster focus")
    completed = store.complete_run(
        run.run_id,
        {
            "spatial": {
                "status": "success",
                "source": "OpenStreetMap Nominatim + Overpass APIs",
                "data": {
                    "query_radius_km": 100,
                    "critical_asset_count": 0,
                    "critical_assets": [],
                    "protected_area_count": 2,
                    "protected_areas": ["Bulleringa National Park", "Staaten River National Park"],
                },
            }
        },
        {"risk_score": 51, "risk_level": "MODERATE", "drivers": []},
        ["Inspect first"],
    )

    result = answer_operational_question(
        "What exposed road and town assets are within the selected AOI?",
        completed,
    )

    assert result["status"] == "success"
    assert result["question_type"] == "exposure_lookup"
    assert result["requires_synthesis"] is True
    assert result["facts"]["current"]["spatial"]["critical_asset_count"] == 0
    assert "Bulleringa National Park" in result["facts"]["current"]["spatial"]["protected_areas"]


def test_adk_runtime_validator_corrects_off_target_wind_synthesis(monkeypatch) -> None:
    class GenericSynthesisRunner:
        def __init__(self, session_service: FakeSessionService, run_id: str) -> None:
            self.session_service = session_service
            self.run_id = run_id

        async def run_async(self, *, user_id: str, session_id: str, new_message, state_delta=None, **kwargs):
            del new_message, kwargs
            session = await self.session_service.get_session(
                app_name="wildfire_ops_agent",
                user_id=user_id,
                session_id=session_id,
            )
            session.state.update(state_delta or {})
            session.state.update(
                {
                    "last_intent": "ANALYST_QA",
                    "last_run_id": self.run_id,
                    "last_response_payload": {
                        "status": "success",
                        "mode": "adk",
                        "question_type": "wind_change",
                        "facts": {
                            "current": {
                                "region_name": "Western Australia hotspot cluster focus",
                                "risk_score": 69,
                                "risk_level": "HIGH",
                                "weather": {"wind_gust_kmh": 41},
                            },
                            "previous": None,
                            "deltas": {},
                        },
                        "missing": ["yesterday matched completed analysis run"],
                        "citations": [{"title": "Weather source", "source": "MET Norway Locationforecast API"}],
                        "requires_synthesis": True,
                    },
                }
            )
            yield FakeEvent(
                "Western Australia hotspot cluster focus is currently HIGH at 69/100. "
                "The leading drivers are low_humidity, low_rainfall, recent_hotspots."
            )

    session_service = FakeSessionService()
    run = store.create_run("state_wa", "Western Australia hotspot cluster focus")
    completed = store.complete_run(run.run_id, {}, {"risk_score": 69, "risk_level": "HIGH"}, ["Inspect first"])
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: GenericSynthesisRunner(session_service, completed.run_id))

    result = AdkRuntime().route_chat(
        ChatRequest(
            message="How does wind changed since yesterday?",
            run_id=completed.run_id,
            region_id="state_wa",
            region_name="Western Australia hotspot cluster focus",
        )
    )

    assert result["intent"] == "WIND_CHANGE"
    assert result["response"]["synthesis_source"] == "validator"
    assert "wind changed since yesterday" in result["response"]["answer"]
    assert "yesterday matched completed analysis run" in result["response"]["answer"]


def test_adk_runtime_keeps_valid_wind_synthesis(monkeypatch) -> None:
    class ValidSynthesisRunner:
        def __init__(self, session_service: FakeSessionService, run_id: str) -> None:
            self.session_service = session_service
            self.run_id = run_id

        async def run_async(self, *, user_id: str, session_id: str, new_message, state_delta=None, **kwargs):
            del new_message, kwargs
            session = await self.session_service.get_session(
                app_name="wildfire_ops_agent",
                user_id=user_id,
                session_id=session_id,
            )
            session.state.update(state_delta or {})
            session.state.update(
                {
                    "last_intent": "ANALYST_QA",
                    "last_run_id": self.run_id,
                    "last_response_payload": {
                        "status": "success",
                        "mode": "adk",
                        "question_type": "wind_change",
                        "facts": {"current": {"region_name": "Western Australia hotspot cluster focus"}},
                        "missing": ["yesterday matched completed analysis run"],
                        "requires_synthesis": True,
                    },
                }
            )
            yield FakeEvent(
                "Wind change since yesterday cannot be calculated because the yesterday baseline is missing."
            )

    session_service = FakeSessionService()
    run = store.create_run("state_wa", "Western Australia hotspot cluster focus")
    completed = store.complete_run(run.run_id, {}, {"risk_score": 69, "risk_level": "HIGH"}, ["Inspect first"])
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: ValidSynthesisRunner(session_service, completed.run_id))

    result = AdkRuntime().route_chat(
        ChatRequest(
            message="How does wind changed since yesterday?",
            run_id=completed.run_id,
            region_id="state_wa",
            region_name="Western Australia hotspot cluster focus",
        )
    )

    assert result["intent"] == "WIND_CHANGE"
    assert result["response"]["synthesis_source"] == "llm"
    assert result["response"]["answer"] == (
        "Wind change since yesterday cannot be calculated because the yesterday baseline is missing."
    )


def test_adk_runtime_allows_no_tool_context_answer(monkeypatch) -> None:
    class ContextOnlyRunner:
        def __init__(self, session_service: FakeSessionService) -> None:
            self.session_service = session_service

        async def run_async(self, *, user_id: str, session_id: str, new_message, state_delta=None, **kwargs):
            del new_message, kwargs
            session = await self.session_service.get_session(
                app_name="wildfire_ops_agent",
                user_id=user_id,
                session_id=session_id,
            )
            session.state.update(state_delta or {})
            yield FakeEvent("The AOI center is latitude -11.35 and longitude 132.12. No external tools were called.")

    session_service = FakeSessionService()
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: ContextOnlyRunner(session_service))
    run = store.create_run("state_nt", "Northern Territory hotspot cluster focus")
    completed = store.complete_run(run.run_id, {}, {"risk_score": 82, "risk_level": "HIGH"}, ["Inspect first"])

    result = AdkRuntime().route_chat(
        ChatRequest(
            message="For this AOI, what is the center's longitude and latitude?",
            run_id=completed.run_id,
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
            aoi=Aoi(center=(-11.35, 132.12), radius_km=50),
        )
    )

    assert result["intent"] == "CONTEXT_ANSWER"
    assert result["response"]["status"] == "success"
    assert "No external tools" in result["response"]["answer"]
    assert result["response"]["tool_trace"][0]["called"] == "Context JSON"


def test_operational_context_message_includes_context_json() -> None:
    message = _message_with_operational_context(
        ChatRequest(
            message="What is the AOI center?",
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
            aoi=Aoi(center=(-11.35, 132.12), radius_km=50),
        )
    )

    assert "context_json" in message
    assert "\"center\": [-11.35, 132.12]" in message


def test_adk_runtime_action_intent_falls_back_when_llm_returns_no_action_payload(monkeypatch) -> None:
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
    run = store.create_run("live_australia", "Australia Live Hotspot AOI")
    completed = store.complete_run(run.run_id, {}, {"risk_score": 72, "risk_level": "HIGH"}, ["Inspect first"])

    result = AdkRuntime().route_chat(
        ChatRequest(message="Draft a public advisory for this alert.", run_id=completed.run_id)
    )

    assert runner.called is True
    assert result["intent"] == "ACTION_COMMAND"
    assert result["response"]["status"] == "success"
    assert result["response"]["action"]["status"] == "pending_approval"
    assert result["response"]["tool_trace"][0]["called"] == "Main Coordinator"
    assert any("Action Workflow" in item["did"] for item in result["response"]["tool_trace"])


def test_adk_runtime_action_intent_falls_back_when_llm_does_not_call_tool(monkeypatch) -> None:
    class NoToolRunner:
        def __init__(self, session_service: FakeSessionService) -> None:
            self.session_service = session_service
            self.called = False
            self.call_count = 0

        async def run_async(self, *, user_id: str, session_id: str, new_message, state_delta=None, **kwargs):
            del new_message, kwargs
            self.called = True
            self.call_count += 1
            session = await self.session_service.get_session(
                app_name="wildfire_ops_agent",
                user_id=user_id,
                session_id=session_id,
            )
            session.state.update(state_delta or {})
            if self.call_count == 2:
                yield FakeEvent("I could not create a public advisory because the required action workflow did not run.")
                return
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
    assert runner.call_count == 1
    assert result["intent"] == "ACTION_COMMAND"
    assert result["response"]["status"] == "success"
    assert result["response"]["action"]["status"] == "pending_approval"
    assert len(store.actions) == 1


def test_adk_runtime_repairs_operational_question_when_first_turn_has_no_llm_answer(monkeypatch) -> None:
    class NoToolRunner:
        def __init__(self, session_service: FakeSessionService) -> None:
            self.session_service = session_service
            self.called = False
            self.call_count = 0

        async def run_async(self, *, user_id: str, session_id: str, new_message, state_delta=None, **kwargs):
            del new_message, kwargs
            self.called = True
            self.call_count += 1
            session = await self.session_service.get_session(
                app_name="wildfire_ops_agent",
                user_id=user_id,
                session_id=session_id,
            )
            session.state.update(state_delta or {})
            if self.call_count == 2:
                yield FakeEvent("Inspect the recent hotspot cluster near exposed road and town assets first.")
                return
            if False:
                yield FakeEvent("I need the tool.")

    session_service = FakeSessionService()
    runner = NoToolRunner(session_service)
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: runner)
    run = store.create_run("state_nt", "Northern Territory hotspot cluster focus")
    completed = store.complete_run(
        run.run_id,
        {},
        {"risk_score": 82, "risk_level": "HIGH", "drivers": [{"factor": "recent_hotspots"}]},
        ["Inspect first"],
    )

    result = AdkRuntime().route_chat(
        ChatRequest(
            message="Which area should we inspect first?",
            run_id=completed.run_id,
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
        )
    )

    assert runner.called is True
    assert runner.call_count == 2
    assert result["intent"] == "OPERATIONAL_PRIORITIZATION"
    assert result["response"]["status"] == "success"
    assert "hotspot cluster near exposed road and town assets" in result["response"]["answer"]
    assert result["response"]["tool_trace"][0]["did"] == "Recovered with Gemini repair answer."


def test_adk_runtime_action_guardrail_creates_pending_approval_without_llm(monkeypatch) -> None:
    session_service = FakeSessionService()
    runner = FakeRunner(
        session_service,
        last_intent="ANALYST_QA",
        payload={"status": "success", "mode": "adk", "answer": "This is only an analyst answer."},
    )
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: runner)
    run = store.create_run("state_nt", "Northern Territory hotspot cluster focus")
    completed = store.complete_run(run.run_id, {}, {"risk_score": 82, "risk_level": "HIGH"}, ["Inspect first"])

    result = AdkRuntime().route_chat(
        ChatRequest(
            message="Draft a public advisory for this alert.",
            run_id=completed.run_id,
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
            aoi=Aoi(center=(-11.35, 132.12), radius_km=50),
        )
    )

    assert runner.called is False
    assert result["intent"] == "ACTION_COMMAND"
    assert result["response"]["action"]["status"] == "pending_approval"
    assert "Public Advisory Draft" in result["response"]["action"]["title"]


def test_adk_runtime_action_command_uses_focused_region_name_without_run(monkeypatch) -> None:
    class NoToolRunner:
        def __init__(self) -> None:
            self.call_count = 0

        async def run_async(self, *, user_id: str, session_id: str, new_message, state_delta=None, **kwargs):
            del user_id, session_id, new_message, state_delta, kwargs
            self.call_count += 1
            if self.call_count == 2:
                yield FakeEvent(
                    "I could not create a public advisory because the action workflow did not return a payload."
                )
                return
            yield FakeEvent("No tool result")

    session_service = FakeSessionService()
    monkeypatch.setattr("app.runtime.adk._ensure_vertex_configuration", lambda: None)
    monkeypatch.setattr("app.runtime.adk._get_session_service", lambda: session_service)
    monkeypatch.setattr("app.runtime.adk._get_runner", lambda: NoToolRunner())
    run = store.create_run("state_nt", "Northern Territory hotspot cluster focus")
    store.complete_run(run.run_id, {}, {"risk_score": 82, "risk_level": "HIGH"}, ["Inspect first"])

    result = AdkRuntime().route_chat(
        ChatRequest(
            message="Draft a public advisory for this alert.",
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
            aoi=Aoi(center=(-11.35, 132.12), radius_km=50),
        )
    )

    assert result["intent"] == "ACTION_COMMAND"
    assert result["response"]["status"] == "success"
    assert result["response"]["action"]["status"] == "pending_approval"
    assert "Northern Territory hotspot cluster focus" in result["response"]["action"]["title"]


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
    run = store.create_run("state_nt", "Northern Territory hotspot cluster focus")
    completed = store.complete_run(run.run_id, {}, {"risk_score": 82, "risk_level": "HIGH"}, ["Inspect first"])

    result = AdkRuntime().route_chat(
        ChatRequest(
            message="Which area should we inspect first?",
            run_id=completed.run_id,
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
            aoi=Aoi(center=(-11.35, 132.12), radius_km=50),
        )
    )

    assert runner.called is True
    assert result["intent"] == "OPERATIONAL_PRIORITIZATION"
    assert result["response"]["status"] == "success"
    assert result["response"]["answer"] == "Inspect the focused AOI first."
    assert store.runs
