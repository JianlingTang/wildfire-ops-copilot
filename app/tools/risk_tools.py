from typing import Any

from app.services.risk_scoring import compute_wildfire_risk_score as score_evidence


def compute_wildfire_risk_score(evidence: dict[str, Any]) -> dict:
    return score_evidence(evidence)


def compute_what_if_risk(current_evidence: dict[str, Any], scenario_delta: dict[str, Any]) -> dict:
    scenario_evidence = dict(current_evidence)
    weather = dict(scenario_evidence.get("weather", {}))
    weather_data = dict(weather.get("data", {}))

    wind_multiplier = scenario_delta.get("wind_multiplier")
    if wind_multiplier:
        weather_data["wind_speed_max"] = round(weather_data.get("wind_speed_max", 0) * wind_multiplier, 1)
        weather_data["wind_gust_max"] = round(weather_data.get("wind_gust_max", 0) * wind_multiplier, 1)

    humidity_floor = scenario_delta.get("humidity_min")
    if humidity_floor:
        weather_data["humidity_min"] = humidity_floor

    rainfall_multiplier = scenario_delta.get("rainfall_multiplier")
    if rainfall_multiplier is not None:
        weather_data["rainfall_7d"] = round(weather_data.get("rainfall_7d", 0) * rainfall_multiplier, 1)

    weather["data"] = weather_data
    scenario_evidence["weather"] = weather
    scenario_score = score_evidence(scenario_evidence)
    baseline_score = score_evidence(current_evidence)
    return {
        "status": "success",
        "baseline": baseline_score,
        "scenario": scenario_score,
        "scenario_delta": scenario_delta,
    }
