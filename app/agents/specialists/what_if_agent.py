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
            f"Scenario risk is {result['scenario']['risk_level']} ({result['scenario']['risk_score']}/100)."
        ),
    }


def _extract_delta(message: str) -> dict:
    lowered = message.lower()
    delta: dict[str, float | int] = {}
    percent_match = re.search(r"(\d+)\s*%", lowered)
    if "wind" in lowered and percent_match:
        delta["wind_multiplier"] = 1 + int(percent_match.group(1)) / 100
    if "rain" in lowered and percent_match:
        delta["rainfall_multiplier"] = max(0, 1 - int(percent_match.group(1)) / 100)
    humidity_match = re.search(r"humidity.*?(\d+)", lowered)
    if humidity_match:
        delta["humidity_min"] = int(humidity_match.group(1))
    return delta or {"wind_multiplier": 1.2}


def _describe_delta(delta: dict) -> str:
    if "wind_multiplier" in delta:
        return f"a wind increase of approximately {round((float(delta['wind_multiplier']) - 1) * 100)}%"
    if "rainfall_multiplier" in delta:
        return "reduced rainfall relief"
    if "humidity_min" in delta:
        return f"minimum humidity near {delta['humidity_min']}%"
    return "the requested condition change"
