from __future__ import annotations

import math
import re
from typing import Any, Literal

CalculationOperation = Literal[
    "add",
    "subtract",
    "multiply",
    "divide",
    "percent_change",
    "circle_area_km2",
]


def calculate(operation: CalculationOperation, values: list[float]) -> float:
    """Perform a small, audited set of deterministic operational calculations."""
    if operation == "circle_area_km2":
        _require_count(operation, values, 1)
        if values[0] < 0:
            raise ValueError("radius must be non-negative")
        return math.pi * values[0] ** 2

    _require_count(operation, values, 2)
    left, right = values
    if operation == "add":
        return left + right
    if operation == "subtract":
        return left - right
    if operation == "multiply":
        return left * right
    if operation == "divide":
        if right == 0:
            raise ValueError("division by zero is not allowed")
        return left / right
    if operation == "percent_change":
        if left == 0:
            raise ValueError("percent change from zero is undefined")
        return ((right - left) / abs(left)) * 100
    raise ValueError(f"unsupported calculation operation: {operation}")


def calculation_request_from_message(message: str) -> tuple[CalculationOperation, list[float]] | None:
    """Extract a conservative calculation request without model inference."""
    lowered = message.lower()
    numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", lowered)]
    if "percent change" in lowered and len(numbers) >= 2:
        return "percent_change", numbers[-2:]
    if any(term in lowered for term in ("area", "square kilometre", "square kilometer", "km2")):
        radius_match = re.search(r"radius\s+(-?\d+(?:\.\d+)?)", lowered)
        if radius_match:
            return "circle_area_km2", [float(radius_match.group(1))]
    return None


def calculation_response_from_message(message: str, *, mode: str) -> dict[str, Any]:
    request = calculation_request_from_message(message)
    if request is None:
        payload: dict[str, Any] = {
            "status": "invalid_input",
            "mode": mode,
            "answer": "No supported deterministic calculation could be extracted from the request.",
            "calculation": None,
        }
        payload["tool_trace"] = [
            _trace_item(
                "Deterministic Python Calculator",
                "Rejected unsupported calculation request.",
                "unsupported_operation",
                mode,
                status="failed",
            )
        ]
        return payload

    operation, values = request
    try:
        result = calculate(operation, values)
    except ValueError as exc:
        payload = {
            "status": "invalid_input",
            "mode": mode,
            "answer": f"The deterministic calculation could not run: {exc}.",
            "calculation": {"operation": operation, "values": values},
        }
        payload["tool_trace"] = [
            _trace_item(
                "Deterministic Python Calculator",
                f"Rejected invalid {operation} inputs.",
                str(exc),
                mode,
                status="failed",
            )
        ]
        return payload

    return {
        "status": "success",
        "mode": mode,
        "answer": f"Deterministic calculation result: {result:.6g}.",
        "result": result,
        "calculation": {
            "operation": operation,
            "values": values,
            "result": result,
            "implementation": "python",
        },
        "tool_trace": [
            _trace_item(
                "Deterministic Python Calculator",
                f"Executed {operation} without model arithmetic.",
                result,
                mode,
            )
        ],
    }


def _require_count(operation: str, values: list[float], expected: int) -> None:
    if len(values) != expected:
        raise ValueError(f"{operation} requires exactly {expected} value(s)")


def _trace_item(called: str, did: str, output: Any, mode: str, *, status: str = "completed") -> dict[str, Any]:
    return {"called": called, "did": did, "output": str(output), "mode": mode, "status": status}
