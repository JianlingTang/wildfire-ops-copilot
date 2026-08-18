import math

import pytest

from app.services.deterministic_calculator import calculate


def test_calculator_handles_operational_math_in_python() -> None:
    assert calculate("percent_change", [60, 72]) == 20
    assert calculate("circle_area_km2", [10]) == pytest.approx(math.pi * 100)


def test_calculator_rejects_invalid_operations() -> None:
    with pytest.raises(ValueError, match="division by zero"):
        calculate("divide", [5, 0])

    with pytest.raises(ValueError, match="requires exactly 2"):
        calculate("add", [1])


def test_agent_routes_calculation_requests_to_deterministic_intent() -> None:
    from app.models.schemas import ChatRequest
    from app.runtime.intents import classify_intent
    from app.runtime.mock_demo import MockDemoRuntime
    from app.services.firestore_store import store

    assert classify_intent("Calculate the percent change in wildfire risk from 40 to 55.") == "CALCULATION"

    result = MockDemoRuntime().route_chat(
        ChatRequest(message="Calculate the percent change in wildfire risk from 40 to 55.")
    )

    assert result["intent"] == "CALCULATION"
    assert result["response"]["result"] == 37.5
    assert result["response"]["calculation"]["implementation"] == "python"
    assert store.actions == {}
