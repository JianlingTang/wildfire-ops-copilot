import re

from app.models.schemas import Aoi, RunRecord
from app.tools.risk_tools import compute_what_if_risk


def run_what_if(
    message: str,
    run: RunRecord | None,
    region_name: str | None = None,
    aoi: Aoi | None = None,
) -> dict:
    if not run:
        if region_name and aoi:
            delta = _extract_delta(message)
            change = _describe_delta(delta)
            return {
                "status": "success",
                "mode": "focused_aoi_context",
                "answer": (
                    f"For {region_name}, {change} would increase operational concern inside the "
                    f"{int(aoi.radius_km)} km focused AOI. I do not have a completed baseline score yet, "
                    "so this is a qualitative scenario answer: prioritize the densest hotspot cluster, "
                    "downwind access routes, and exposed settlement edges before lower-density detections."
                ),
                "scenario": {
                    "qualitative_risk": "elevated",
                    "delta": delta,
                    "requires_analysis_for_score": True,
                },
            }
        return {
            "status": "needs_context",
            "answer": "No completed run is available for scenario comparison.",
        }
    delta = _extract_delta(message)
    result = compute_what_if_risk(run.evidence, delta)
    return {
        **result,
        "answer": (
            f"Baseline risk is {result['baseline']['risk_level']} ({result['baseline']['risk_score']}/100). "
            f"Scenario risk is {result['scenario']['risk_level']} ({result['scenario']['risk_score']}/100). "
            f"{_scenario_effect_summary(result)}"
        ),
    }


def _extract_delta(message: str) -> dict:
    lowered = message.lower()
    delta: dict[str, float | int] = {}
    percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", lowered)
    if "wind" in lowered and percent_match:
        delta["wind_multiplier"] = _percent_multiplier(
            lowered,
            float(percent_match.group(1)),
            default_direction="increase",
        )
    if "rain" in lowered and percent_match:
        delta["rainfall_multiplier"] = _percent_multiplier(
            lowered,
            float(percent_match.group(1)),
            default_direction="increase",
        )
    humidity_match = re.search(r"humidity.*?(\d+)", lowered)
    if humidity_match:
        delta["humidity_min"] = int(humidity_match.group(1))
    return delta or {"wind_multiplier": 1.2}


def _percent_multiplier(lowered: str, percent: float, *, default_direction: str) -> float:
    if any(term in lowered for term in ["decrease", "decreases", "decreased", "drop", "drops", "less", "lower"]):
        return max(0, 1 - percent / 100)
    if any(term in lowered for term in ["increase", "increases", "increased", "rise", "rises", "more", "higher"]):
        return 1 + percent / 100
    if default_direction == "decrease":
        return max(0, 1 - percent / 100)
    return 1 + percent / 100


def _describe_delta(delta: dict) -> str:
    if "wind_multiplier" in delta:
        change = round((float(delta["wind_multiplier"]) - 1) * 100)
        direction = "increase" if change >= 0 else "decrease"
        return f"a wind {direction} of approximately {abs(change)}%"
    if "rainfall_multiplier" in delta:
        change = round((float(delta["rainfall_multiplier"]) - 1) * 100)
        direction = "increase" if change >= 0 else "decrease"
        return f"a rainfall {direction} of approximately {abs(change)}%"
    if "humidity_min" in delta:
        return f"minimum humidity near {delta['humidity_min']}%"
    return "the requested condition change"


def _scenario_effect_summary(result: dict) -> str:
    weather_delta = result.get("weather_delta") if isinstance(result.get("weather_delta"), dict) else {}
    driver_changes = result.get("driver_changes") if isinstance(result.get("driver_changes"), dict) else {}
    parts: list[str] = []
    if weather_delta:
        weather_parts = [
            f"{key} {change.get('baseline')} -> {change.get('scenario')}"
            for key, change in weather_delta.items()
            if isinstance(change, dict)
        ]
        if weather_parts:
            parts.append("Weather changes: " + "; ".join(weather_parts) + ".")
    if driver_changes:
        driver_parts = [
            f"{factor} {change.get('baseline')} -> {change.get('scenario')}"
            for factor, change in driver_changes.items()
            if isinstance(change, dict)
        ]
        if driver_parts:
            parts.append("Driver changes: " + "; ".join(driver_parts) + ".")
    if parts:
        return " ".join(parts)
    return "No scored driver changed enough to alter the deterministic risk score."
