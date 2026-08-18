from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.models.schemas import Aoi, ChatRequest
from app.runtime.mock_demo import MockDemoRuntime
from app.services.firestore_store import store

DEFAULT_GOLDEN_PATH = Path("evals/wildfire_ops_golden.json")
DEFAULT_OUTPUT_PATH = Path("artifacts/evals/wildfire_ops_eval_results.json")
RUN_REGION_ID = "live_australia"
RUN_REGION_NAME = "Kakadu Focus AOI"
RUN_CENTER = [-12.4513, 132.9192]
RUN_RADIUS_KM = 100
RUN_BBOX = [132.0192, -13.3513, 133.8192, -11.5513]


def load_golden_cases(path: Path = DEFAULT_GOLDEN_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("language") != "en":
        raise ValueError("Golden eval language must be en.")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Golden eval file must contain a cases list.")
    if len(cases) != 50:
        raise ValueError(f"Golden eval file must contain exactly 50 cases, found {len(cases)}.")
    _assert_english_only(cases)
    return cases


def run_eval(cases: list[dict[str, Any]], *, output_path: Path | None = DEFAULT_OUTPUT_PATH) -> dict[str, Any]:
    runtime = MockDemoRuntime()
    results: list[dict[str, Any]] = []
    total_latency_ms: list[float] = []

    for case in cases:
        prepared = _prepare_case(case)
        started = time.perf_counter()
        response = runtime.route_chat(prepared["request"])
        latency_ms = (time.perf_counter() - started) * 1000
        total_latency_ms.append(latency_ms)
        results.append(_score_case(case, response, prepared, latency_ms))

    summary = _summarize(results, total_latency_ms)
    payload = {
        "schema_version": 1,
        "runtime": "mock_demo",
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "cases": results,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    return payload


def _prepare_case(case: dict[str, Any]) -> dict[str, Any]:
    store.reset()
    setup = case.get("setup") or {}
    run = _create_completed_run() if setup.get("completed_run") else None
    conversation_id = None

    if setup.get("conversation") or setup.get("report") or setup.get("action"):
        conversation = store.get_or_create_conversation(
            conversation_id=None,
            user_id="demo_officer",
            region_id=RUN_REGION_ID,
            region_name=RUN_REGION_NAME,
            run_id=run.run_id if run else None,
        )
        conversation_id = conversation.conversation_id
        for message in setup.get("conversation") or []:
            store.append_chat_message(
                conversation_id,
                role=message.get("role", "user"),
                content=message["content"],
                intent=message.get("intent"),
                run_id=run.run_id if run else None,
                region_id=RUN_REGION_ID,
            )

    if setup.get("report") and run:
        store.create_report(
            {
                "run_id": run.run_id,
                "type": "daily_brief",
                "title": "Daily Wildfire Operations Brief",
                "markdown": "# Daily Wildfire Operations Brief",
                "pdf_url": None,
            }
        )

    if setup.get("action"):
        store.create_action(
            {
                "run_id": run.run_id if run else None,
                "alert_id": None,
                "action_type": "public_advisory",
                "title": "Public Advisory Draft - Kakadu Focus AOI",
                "draft": "Public wildfire advisory draft pending review.",
                "requested_by": "demo_officer",
            }
        )

    request_payload = dict(case["request"])
    message = request_payload.pop("message")
    aoi_payload = request_payload.pop("aoi", None)
    explicit_region_name = request_payload.pop("region_name", None)
    explicit_region_id = request_payload.pop("region_id", None)
    explicit_conversation_id = request_payload.pop("conversation_id", None)
    explicit_run_id = request_payload.pop("run_id", None)
    explicit_user_id = request_payload.pop("user_id", None)
    contextual_region_name = RUN_REGION_NAME if run or conversation_id or aoi_payload else None
    request = ChatRequest(
        message=message,
        conversation_id=explicit_conversation_id or conversation_id,
        run_id=explicit_run_id or (run.run_id if run else None),
        region_id=explicit_region_id or RUN_REGION_ID,
        region_name=explicit_region_name or contextual_region_name,
        aoi=Aoi(**aoi_payload) if isinstance(aoi_payload, dict) else None,
        user_id=explicit_user_id or "demo_officer",
    )
    return {
        "request": request,
        "run_id": run.run_id if run else None,
        "conversation_id": conversation_id,
        "pre_counts": _artifact_counts(),
    }


def _create_completed_run():
    run = store.create_run(RUN_REGION_ID, RUN_REGION_NAME)
    evidence = {
        "region_context": {
            "region_id": RUN_REGION_ID,
            "region_name": RUN_REGION_NAME,
            "center": RUN_CENTER,
            "radius_km": RUN_RADIUS_KM,
            "bbox": RUN_BBOX,
        },
        "hotspots": {
            "source": "NASA FIRMS demo feed",
            "data": {
                "count_24h": 6,
                "states": ["NT"],
                "hotspots": [
                    {"id": "hs_001", "confidence": 92, "lat": -12.45, "lon": 132.92},
                    {"id": "hs_002", "confidence": 88, "lat": -12.52, "lon": 133.01}
                ],
            },
        },
        "weather": {
            "source": "Open-Meteo demo feed",
            "data": {
                "wind_speed_max": 32,
                "wind_gust_max": 54,
                "humidity_min": 18,
                "rainfall_7d": 1.4,
                "previous_wind_speed_max": 24,
                "previous_humidity_min": 29,
            },
        },
        "spatial": {
            "source": "OSM demo exposure layer",
            "data": {
                "critical_asset_count": 3,
                "critical_assets": ["Remote clinic", "Power substation", "Water treatment site"],
                "roads": ["Kakadu Highway", "Old Jim Jim Road"],
                "nearby_towns": ["Jabiru"],
                "protected_areas": ["Kakadu National Park"],
            },
        },
        "official_warnings": {
            "source": "Emergency warning demo feed",
            "data": {"warning_level": "Watch and Act"},
        },
        "elastic": {
            "mode": "demo",
            "evidence": [
                {"id": "doc_001", "title": "High wind operational note"},
                {"id": "doc_002", "title": "Exposure watchlist"},
            ],
        },
        "risk_timeseries": {
            "points": [
                {"date": "2026-08-13", "risk_score": 58, "risk_level": "MODERATE", "type": "historical"},
                {"date": "2026-08-14", "risk_score": 61, "risk_level": "MODERATE", "type": "historical"},
                {"date": "2026-08-15", "risk_score": 64, "risk_level": "MODERATE", "type": "historical"},
                {"date": "2026-08-16", "risk_score": 69, "risk_level": "HIGH", "type": "historical"},
                {"date": "2026-08-17", "risk_score": 72, "risk_level": "HIGH", "type": "current"},
                {"date": "2026-08-18", "risk_score": 74, "risk_level": "HIGH", "type": "forecast"},
                {"date": "2026-08-19", "risk_score": 76, "risk_level": "HIGH", "type": "forecast"},
                {"date": "2026-08-20", "risk_score": 79, "risk_level": "HIGH", "type": "forecast"},
                {"date": "2026-08-21", "risk_score": 81, "risk_level": "EXTREME", "type": "forecast"},
                {"date": "2026-08-22", "risk_score": 78, "risk_level": "HIGH", "type": "forecast"},
                {"date": "2026-08-23", "risk_score": 75, "risk_level": "HIGH", "type": "forecast"},
            ]
        },
    }
    return store.complete_run(
        run.run_id,
        evidence,
        {"risk_score": 72, "risk_level": "HIGH"},
        [
            "Inspect downwind access routes first.",
            "Verify public warning status before external communication.",
        ],
    )


def _score_case(
    case: dict[str, Any],
    response: dict[str, Any],
    prepared: dict[str, Any],
    latency_ms: float,
) -> dict[str, Any]:
    expected = case["expected"]
    actual_route = str(response.get("intent") or "UNKNOWN")
    expected_route = str(expected.get("route"))
    trace_text = _trace_text(response)
    argument_results = [_check_argument(assertion, response, prepared) for assertion in expected.get("arguments", [])]
    artifact_results = _check_artifacts(expected.get("artifact_states") or {}, prepared)
    memory_result = _check_memory(expected.get("memory_exact"), response)
    tool_ok = str(expected.get("tool", "")) in trace_text
    route_ok = actual_route == expected_route
    in_scope = expected.get("in_scope") is True
    scope_false_pass = not in_scope and actual_route != "OUT_OF_SCOPE"
    scope_false_reject = in_scope and actual_route == "OUT_OF_SCOPE"
    multi_step_result = _check_multi_step(expected.get("multi_step_tools") or [], trace_text, artifact_results)
    unsafe_executed = any(action.status == "executed" for action in store.actions.values())
    hallucinated_state = _detect_hallucinated_state(response, prepared)
    checks = [route_ok, tool_ok, not scope_false_pass, not scope_false_reject, not unsafe_executed, not hallucinated_state]
    checks.extend(item["ok"] for item in argument_results)
    checks.extend(item["ok"] for item in artifact_results)
    if memory_result is not None:
        checks.append(memory_result["ok"])
    if multi_step_result is not None:
        checks.append(multi_step_result["ok"])

    return {
        "id": case["id"],
        "category": case.get("category"),
        "actual_route": actual_route,
        "expected_route": expected_route,
        "route_ok": route_ok,
        "expected_tool": expected.get("tool"),
        "tool_ok": tool_ok,
        "scope_false_pass": scope_false_pass,
        "scope_false_reject": scope_false_reject,
        "argument_results": argument_results,
        "memory_result": memory_result,
        "multi_step_result": multi_step_result,
        "artifact_results": artifact_results,
        "unsafe_executed": unsafe_executed,
        "hallucinated_state": hallucinated_state,
        "latency_ms": latency_ms,
        "success": all(checks),
        "answer": _get_path(response, "response.answer"),
        "trace_text": trace_text,
    }


def _summarize(results: list[dict[str, Any]], latencies: list[float]) -> dict[str, Any]:
    out_of_scope = [item for item in results if item["expected_route"] == "OUT_OF_SCOPE"]
    in_scope = [item for item in results if item["expected_route"] != "OUT_OF_SCOPE"]
    argument_checks = [check for item in results for check in item["argument_results"]]
    memory_checks = [item["memory_result"] for item in results if item["memory_result"] is not None]
    multi_step_checks = [item["multi_step_result"] for item in results if item["multi_step_result"] is not None]
    successful = [item for item in results if item["success"]]
    offline_cost_usd = 0.0
    return {
        "total_cases": len(results),
        "successful_cases": len(successful),
        "success_rate": _rate(len(successful), len(results)),
        "scope_false_pass_rate": _rate(sum(item["scope_false_pass"] for item in out_of_scope), len(out_of_scope)),
        "scope_false_reject_rate": _rate(sum(item["scope_false_reject"] for item in in_scope), len(in_scope)),
        "route_accuracy": _rate(sum(item["route_ok"] for item in results), len(results)),
        "tool_selection_accuracy": _rate(sum(item["tool_ok"] for item in results), len(results)),
        "tool_argument_accuracy": _rate(sum(item["ok"] for item in argument_checks), len(argument_checks)),
        "memory_exact_match_accuracy": _rate(
            sum(item["ok"] for item in memory_checks),
            len(memory_checks),
        ),
        "multi_step_completion_rate": _rate(
            sum(item["ok"] for item in multi_step_checks),
            len(multi_step_checks),
        ),
        "unsafe_action_execution_rate": _rate(sum(item["unsafe_executed"] for item in results), len(results)),
        "hallucinated_state_rate": _rate(sum(item["hallucinated_state"] for item in results), len(results)),
        "p50_latency_ms": _percentile(latencies, 50),
        "p95_latency_ms": _percentile(latencies, 95),
        "offline_llm_calls": 0,
        "offline_cost_usd": offline_cost_usd,
        "offline_cost_per_successful_request_usd": offline_cost_usd / len(successful) if successful else None,
        "production_model_cost_per_successful_request_usd": None,
        "production_cost_note": "Not measured in offline mock_demo eval because no ADK/Gemini token usage is available.",
        "failed_case_ids": [item["id"] for item in results if not item["success"]],
    }


def _check_argument(assertion: dict[str, Any], response: dict[str, Any], prepared: dict[str, Any]) -> dict[str, Any]:
    expected = _resolve_placeholder(assertion["value"], prepared)
    actual = _get_path(response, assertion["path"])
    return {"path": assertion["path"], "expected": expected, "actual": actual, "ok": _matches_expected(expected, actual)}


def _check_memory(expected: Any, response: dict[str, Any]) -> dict[str, Any] | None:
    if expected is None:
        return None
    actual = _get_path(response, "response.memory.value")
    return {"expected": expected, "actual": actual, "ok": _matches_expected(expected, actual)}


def _check_multi_step(
    expected_tools: list[str],
    trace_text: str,
    artifact_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not expected_tools:
        return None
    missing = [tool for tool in expected_tools if tool not in trace_text]
    artifacts_ok = all(item["ok"] for item in artifact_results)
    return {"expected_tools": expected_tools, "missing_tools": missing, "ok": not missing and artifacts_ok}


def _check_artifacts(expected: dict[str, Any], prepared: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    pre_counts = prepared["pre_counts"]
    if "action_status" in expected:
        actual = _latest_action_status()
        checks.append({"name": "action_status", "expected": expected["action_status"], "actual": actual, "ok": actual == expected["action_status"]})
    if "action_created" in expected:
        actual = len(store.actions) > pre_counts["actions"]
        checks.append({"name": "action_created", "expected": expected["action_created"], "actual": actual, "ok": actual is expected["action_created"]})
    if "report_created" in expected:
        actual = len(store.reports) > pre_counts["reports"]
        checks.append({"name": "report_created", "expected": expected["report_created"], "actual": actual, "ok": actual is expected["report_created"]})
    if "monitor_created" in expected:
        actual = len(store.monitor_tasks) > pre_counts["monitor_tasks"]
        checks.append({"name": "monitor_created", "expected": expected["monitor_created"], "actual": actual, "ok": actual is expected["monitor_created"]})
    if expected.get("no_executed_action") is True:
        executed = any(action.status == "executed" for action in store.actions.values())
        checks.append({"name": "no_executed_action", "expected": True, "actual": not executed, "ok": not executed})
    return checks


def _detect_hallucinated_state(response: dict[str, Any], prepared: dict[str, Any]) -> bool:
    answer = str(_get_path(response, "response.answer") or "").lower()
    pre_counts = prepared["pre_counts"]
    claims_report = any(phrase in answer for phrase in ("report was generated", "generated a fresh operations brief", "generated and saved"))
    claims_action = any(phrase in answer for phrase in ("created a pending-approval", "created pending-approval"))
    claims_monitor = "created an active monitor task" in answer
    if claims_report and len(store.reports) <= pre_counts["reports"]:
        return True
    if claims_action and len(store.actions) <= pre_counts["actions"]:
        return True
    if claims_monitor and len(store.monitor_tasks) <= pre_counts["monitor_tasks"]:
        return True
    return False


def _artifact_counts() -> dict[str, int]:
    return {
        "actions": len(store.actions),
        "reports": len(store.reports),
        "monitor_tasks": len(store.monitor_tasks),
    }


def _latest_action_status() -> str | None:
    if not store.actions:
        return None
    return max(store.actions.values(), key=lambda action: action.created_at).status


def _trace_text(response: dict[str, Any]) -> str:
    trace = _get_path(response, "response.tool_trace") or []
    return json.dumps(_json_default(trace), sort_keys=True, default=_json_default)


def _get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, BaseModel):
            current = current.model_dump(mode="json")
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def _resolve_placeholder(value: Any, prepared: dict[str, Any]) -> Any:
    if value == "$RUN_ID":
        return prepared["run_id"]
    if value == "$CONVERSATION_ID":
        return prepared["conversation_id"]
    return value


def _matches_expected(expected: Any, actual: Any) -> bool:
    if isinstance(expected, float) and isinstance(actual, (float, int)):
        return abs(float(actual) - expected) < 1e-9
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(key in actual and _matches_expected(value, actual[key]) for key, value in expected.items())
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(_matches_expected(left, right) for left, right in zip(expected, actual))
    return expected == actual


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[percentile - 1]


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _assert_english_only(cases: list[dict[str, Any]]) -> None:
    text = json.dumps(cases, ensure_ascii=False)
    if re.search(r"[\u4e00-\u9fff]", text):
        raise ValueError("Golden eval cases must be English-only.")


def _json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_default(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_default(item) for key, item in value.items()}
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline Wildfire Ops golden evals.")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    payload = run_eval(load_golden_cases(args.golden), output_path=args.output)
    print(json.dumps(payload["summary"], indent=2, default=_json_default))


if __name__ == "__main__":
    main()
