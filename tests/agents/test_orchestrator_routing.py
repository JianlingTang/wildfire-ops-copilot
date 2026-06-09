from app.agents.root_agent import classify_intent


def test_change_question_routes_to_change_explanation() -> None:
    assert classify_intent("What changed since yesterday?") == "CHANGE_EXPLANATION"


def test_analysis_command_routes_to_analyze_and_report() -> None:
    assert classify_intent("Analyze Blue Mountains and generate today's report.") == "ANALYZE_AND_REPORT"


def test_high_risk_question_routes_to_risk_explanation() -> None:
    assert classify_intent("Why is this region high risk?") == "RISK_EXPLANATION"


def test_inspection_question_routes_to_operational_prioritization() -> None:
    assert classify_intent("Which area should we inspect first?") == "OPERATIONAL_PRIORITIZATION"
