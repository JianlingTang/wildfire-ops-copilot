from app.agents.root_agent import classify_intent


def test_wind_scenario_routes_to_what_if_agent() -> None:
    assert classify_intent("What if wind speed increases by 20% tomorrow?") == "WHAT_IF"


def test_risk_methodology_routes_to_risk_explanation_not_rag() -> None:
    assert classify_intent("How do you calculate risk level? On what basis and equations?") == "RISK_EXPLANATION"
