from app.agents.root_agent import classify_intent


def test_change_question_routes_to_change_explanation() -> None:
    assert classify_intent("What changed since yesterday?") == "CHANGE_EXPLANATION"


def test_analysis_command_routes_to_analyze_and_report() -> None:
    assert classify_intent("Analyze Blue Mountains and generate today's report.") == "ANALYZE_AND_REPORT"


def test_high_risk_question_routes_to_risk_explanation() -> None:
    assert classify_intent("Why is this region high risk?") == "RISK_EXPLANATION"


def test_inspection_question_routes_to_operational_prioritization() -> None:
    assert classify_intent("Which area should we inspect first?") == "OPERATIONAL_PRIORITIZATION"


def test_risk_trend_question_routes_to_risk_trend() -> None:
    assert classify_intent("Show the risk trend for this AOI.") == "RISK_TREND"


def test_prediction_question_routes_to_risk_prediction() -> None:
    assert classify_intent("Predict wildfire risk for the next few days.") == "RISK_PREDICTION"
    assert classify_intent("What if wind increases tomorrow?") == "WHAT_IF"
