from app.agents.root_agent import classify_intent


def test_wind_scenario_routes_to_what_if_agent() -> None:
    assert classify_intent("What if wind speed increases by 20% tomorrow?") == "WHAT_IF"
