"""Deterministic, LLM-free synthesis of an operator answer from evidence facts.

Used as the fallback when the LLM's final text is missing or fails
_valid_synthesis_answer's on-target check (see app.runtime.adk.response).
"""

from __future__ import annotations

from typing import Any

from app.models.schemas import ChatRequest


def _safe_synthesis_answer(payload: dict[str, Any], request: ChatRequest) -> str:
    current, previous, deltas, missing = _synthesis_facts(payload)
    region = current.get("region_name") or request.region_name or request.region_id or "the selected AOI"
    if payload.get("status") == "missing_context" and not current:
        missing_text = ", ".join(missing) or "completed analysis context"
        return f"I need {missing_text} before I can answer this operational question for {region}."
    question_type = str(payload.get("question_type") or "operational_summary")
    return _answer_for_question_type(question_type, region, current, previous, deltas, missing, payload)


def _synthesis_facts(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any], list[str]]:
    raw_facts = payload.get("facts")
    facts: dict[str, Any] = raw_facts if isinstance(raw_facts, dict) else {}
    raw_current = facts.get("current")
    current: dict[str, Any] = raw_current if isinstance(raw_current, dict) else {}
    raw_previous = facts.get("previous")
    previous: dict[str, Any] | None = raw_previous if isinstance(raw_previous, dict) else None
    raw_deltas = facts.get("deltas")
    deltas: dict[str, Any] = raw_deltas if isinstance(raw_deltas, dict) else {}
    missing = [str(item) for item in payload.get("missing", [])]
    return current, previous, deltas, missing


def _answer_for_question_type(
    question_type: str,
    region: str,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    deltas: dict[str, Any],
    missing: list[str],
    payload: dict[str, Any],
) -> str:
    if question_type == "wind_change":
        return _wind_change_answer(region, current, previous, deltas, missing)
    if question_type == "weather_change":
        return _weather_change_answer(region, current, previous, deltas, missing)
    if question_type == "overall_change":
        return _overall_change_answer(region, current, previous, deltas, missing)
    if question_type == "exposure_lookup":
        return _exposure_lookup_answer(region, current)
    if question_type == "inspection_priority":
        return _inspection_priority_answer(region, payload)
    if question_type == "risk_explanation":
        return _risk_explanation_answer(region, current)
    return f"{region} is {_risk_text(current)} based on the latest completed analysis run."


def _inspection_priority_answer(region: str, payload: dict[str, Any]) -> str:
    recommendations = payload.get("recommendations") or []
    first = str(recommendations[0]) if recommendations else "inspect the densest active hotspot cluster first"
    return (
        f"For {region}, inspect this first: {first}. This is based on the latest run drivers and spatial exposure "
        "evidence."
    )


def _risk_explanation_answer(region: str, current: dict[str, Any]) -> str:
    drivers = _driver_names(current)
    risk = _risk_text(current)
    return (
        f"{region} is {risk}. The leading drivers are {drivers}, supported by the latest hotspot, weather, "
        "spatial, and Elastic evidence."
    )


def _wind_change_answer(
    region: str,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    deltas: dict[str, Any],
    missing: list[str],
) -> str:
    current_wind = current.get("weather", {}).get("wind_gust_kmh")
    delta = deltas.get("wind_gust_kmh")
    if missing or not previous or not delta:
        missing_text = ", ".join(missing or ["yesterday wind baseline"])
        current_text = f" Current wind gust evidence is {current_wind} km/h." if current_wind is not None else ""
        return (
            f"I cannot calculate how wind changed since yesterday for {region} because {missing_text} is "
            f"missing.{current_text}"
        )
    return (
        f"Wind changed since yesterday in {region}: gusts are {delta['current']:g} km/h now versus "
        f"{delta['previous']:g} km/h previously, a {delta['delta']:+g} km/h change."
    )


def _weather_change_answer(
    region: str,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    deltas: dict[str, Any],
    missing: list[str],
) -> str:
    if missing or not previous:
        return _weather_change_missing_answer(region, current, missing)
    parts = []
    wind = deltas.get("wind_gust_kmh")
    humidity = deltas.get("humidity_min")
    if wind:
        parts.append(f"wind gusts {wind['delta']:+g} km/h")
    if humidity:
        parts.append(f"minimum humidity {humidity['delta']:+g} points")
    return (
        f"Weather changed since yesterday in {region}: "
        f"{', '.join(parts) or 'no comparable weather deltas were available'}."
    )


def _weather_change_missing_answer(region: str, current: dict[str, Any], missing: list[str]) -> str:
    missing_text = ", ".join(missing or ["yesterday matched completed analysis run"])
    weather = current.get("weather", {})
    return (
        f"I cannot calculate weather change since yesterday for {region} because {missing_text} is missing. "
        f"Current evidence shows wind gusts {weather.get('wind_gust_kmh', 'unknown')} km/h, "
        f"minimum humidity {weather.get('humidity_min', 'unknown')}%, and seven-day rainfall "
        f"{weather.get('rainfall_7d', 'unknown')} mm."
    )


def _overall_change_answer(
    region: str,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    deltas: dict[str, Any],
    missing: list[str],
) -> str:
    if missing or not previous:
        missing_text = ", ".join(missing or ["yesterday matched completed analysis run"])
        return (
            f"I cannot compute what changed since yesterday for {region} because {missing_text} is missing. "
            f"The current run shows {_risk_text(current)} with leading drivers {_driver_names(current)}."
        )
    risk_delta = deltas.get("risk_score")
    hotspot_delta = deltas.get("hotspot_count_24h")
    parts = []
    if risk_delta:
        parts.append(f"risk score {risk_delta['previous']:g} -> {risk_delta['current']:g} ({risk_delta['delta']:+g})")
    if hotspot_delta:
        parts.append(
            f"24h hotspots {hotspot_delta['previous']:g} -> {hotspot_delta['current']:g} ({hotspot_delta['delta']:+g})"
        )
    return f"Since yesterday in {region}, {', '.join(parts) or 'no comparable numeric deltas were available'}."


def _exposure_lookup_answer(region: str, current: dict[str, Any]) -> str:
    spatial = current.get("spatial", {})
    critical_assets = [str(item) for item in spatial.get("critical_assets", [])]
    protected_areas = [str(item) for item in spatial.get("protected_areas", [])]
    critical_text = _format_items(critical_assets, "no named critical assets returned")
    protected_text = _format_items(protected_areas, "no named protected or park areas returned")
    return (
        f"For {region}, spatial evidence returned {spatial.get('critical_asset_count', 0)} critical assets and "
        f"{spatial.get('protected_area_count', 0)} protected or park areas. Critical assets: {critical_text}. "
        f"Protected/park areas: {protected_text}. The current exposure tool does not enumerate named road corridors or "
        "town/settlement assets, so I will not claim specific roads or towns from this evidence."
    )


def _risk_text(current: dict[str, Any]) -> str:
    level = current.get("risk_level") or "unknown risk"
    score = current.get("risk_score")
    return f"{level} at {score}/100" if score is not None else str(level)


def _driver_names(current: dict[str, Any]) -> str:
    drivers = current.get("drivers", [])
    names = [str(item.get("factor")) for item in drivers if isinstance(item, dict) and item.get("factor")]
    return ", ".join(names[:3]) if names else "no dominant drivers"


def _format_items(items: list[str], empty: str) -> str:
    if not items:
        return empty
    visible = items[:5]
    suffix = f", plus {len(items) - len(visible)} more" if len(items) > len(visible) else ""
    return "; ".join(visible) + suffix
