from pathlib import Path

from scripts.run_agent_evals import load_golden_cases, run_eval


def test_golden_eval_set_has_50_english_cases() -> None:
    cases = load_golden_cases(Path("evals/wildfire_ops_golden.json"))

    assert len(cases) == 50
    assert all(case["request"]["message"].isascii() for case in cases)


def test_eval_harness_reports_required_metrics(tmp_path) -> None:
    cases = load_golden_cases(Path("evals/wildfire_ops_golden.json"))
    result = run_eval(cases, output_path=tmp_path / "results.json")
    summary = result["summary"]

    for metric in [
        "scope_false_pass_rate",
        "scope_false_reject_rate",
        "route_accuracy",
        "tool_selection_accuracy",
        "tool_argument_accuracy",
        "memory_exact_match_accuracy",
        "multi_step_completion_rate",
        "unsafe_action_execution_rate",
        "hallucinated_state_rate",
        "p50_latency_ms",
        "p95_latency_ms",
        "offline_cost_per_successful_request_usd",
    ]:
        assert metric in summary

    assert summary["total_cases"] == 50
    assert summary["unsafe_action_execution_rate"] == 0
