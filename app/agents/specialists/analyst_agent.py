from typing import Any

from app.models.schemas import Aoi, RunRecord
from app.services.firestore_store import store


def answer_operational_question(
    message: str,
    run: RunRecord | None,
    region_name: str | None = None,
    aoi: Aoi | None = None,
) -> dict:
    lowered = message.lower()
    question_type = _question_type(lowered)
    if not run:
        if region_name and aoi:
            return answer_focused_aoi_question(message, region_name, aoi, question_type)
        return {
            "status": "missing_context",
            "question_type": question_type,
            "facts": {},
            "missing": ["completed analysis run", "selected AOI"],
            "citations": [],
            "requires_synthesis": True,
        }

    current = _run_facts(run)
    previous = _previous_completed_run(run)
    previous_facts = _run_facts(previous) if previous else None
    missing: list[str] = []
    if question_type in {"overall_change", "wind_change", "weather_change"} and not previous_facts:
        missing.append("yesterday matched completed analysis run")
    if question_type == "wind_change" and current.get("weather", {}).get("wind_gust_kmh") is None:
        missing.append("current wind gust evidence")
    if (
        question_type == "wind_change"
        and previous_facts
        and previous_facts.get("weather", {}).get("wind_gust_kmh") is None
    ):
        missing.append("yesterday wind gust evidence")

    return {
        "status": "success",
        "question_type": question_type,
        "facts": {
            "current": current,
            "previous": previous_facts,
            "deltas": _deltas(current, previous_facts),
        },
        "missing": missing,
        "citations": _citations_for_run(run),
        "evidence_keys": list(run.evidence.keys()),
        "recommendations": run.recommendations,
        "requires_synthesis": True,
    }


def answer_focused_aoi_question(message: str, region_name: str, aoi: Aoi, question_type: str | None = None) -> dict:
    del message
    return {
        "status": "missing_context",
        "question_type": question_type or "operational_summary",
        "facts": {
            "region_name": region_name,
            "center": list(aoi.center) if aoi.center else None,
            "radius_km": aoi.radius_km,
            "source": "focused_aoi_context",
        },
        "missing": ["completed analysis run"],
        "citations": [{"title": "Focused AOI context", "source": "current selection"}],
        "recommendations": [
            "Inspect the densest hotspot cluster first.",
            "Check exposed access roads and nearby settlement edges.",
            "Run full analysis before issuing external guidance.",
        ],
        "requires_synthesis": True,
    }


def _format_center(aoi: Aoi) -> str:
    if not aoi.center:
        return "the selected map center"
    lat, lon = aoi.center
    return f"{lat:.3f}, {lon:.3f}"


def _question_type(lowered: str) -> str:
    if "wind" in lowered and any(term in lowered for term in ["changed", "change", "since yesterday", "yesterday"]):
        return "wind_change"
    if "weather" in lowered and any(term in lowered for term in ["changed", "change", "since yesterday", "yesterday"]):
        return "weather_change"
    if "changed" in lowered or "since yesterday" in lowered:
        return "overall_change"
    if _is_spatial_exposure_question(lowered):
        return "exposure_lookup"
    if "inspect" in lowered or "first" in lowered or "priority" in lowered:
        return "inspection_priority"
    if "why" in lowered or "risk" in lowered or "evidence" in lowered:
        return "risk_explanation"
    return "operational_summary"


def _is_spatial_exposure_question(lowered: str) -> bool:
    exposure_terms = [
        "exposed",
        "exposure",
        "asset",
        "assets",
        "critical",
        "road",
        "roads",
        "town",
        "towns",
        "settlement",
        "settlements",
        "protected",
        "park",
        "parks",
    ]
    lookup_terms = ["what", "which", "list", "show", "within", "inside", "near", "nearby", "aoi"]
    return any(term in lowered for term in exposure_terms) and any(term in lowered for term in lookup_terms)


def _previous_completed_run(run: RunRecord) -> RunRecord | None:
    candidates = [
        candidate
        for candidate in store.runs.values()
        if candidate.run_id != run.run_id
        and candidate.region_id == run.region_id
        and candidate.status == "completed"
        and candidate.completed_at
    ]
    if not candidates:
        return None
    current_time = run.completed_at or run.created_at
    older = [candidate for candidate in candidates if (candidate.completed_at or candidate.created_at) < current_time]
    return max(older or candidates, key=lambda candidate: candidate.completed_at or candidate.created_at)


def _run_facts(run: RunRecord | None) -> dict[str, Any]:
    if not run:
        return {}
    drivers = run.risk_assessment.get("drivers", [])
    hotspots = _data(run.evidence.get("hotspots"))
    weather = _data(run.evidence.get("weather"))
    spatial = _data(run.evidence.get("spatial"))
    warnings = _data(run.evidence.get("official_warnings"))
    return {
        "run_id": run.run_id,
        "region_id": run.region_id,
        "region_name": run.region_name,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "risk_score": run.risk_score,
        "risk_level": run.risk_level,
        "drivers": drivers[:5],
        "hotspots": {
            "count_24h": hotspots.get("count_24h") or hotspots.get("total_count_24h") or hotspots.get("count"),
            "states": hotspots.get("states", []),
        },
        "weather": {
            "wind_gust_kmh": weather.get("wind_gust_max"),
            "wind_speed_kmh": weather.get("wind_speed_max"),
            "humidity_min": weather.get("humidity_min"),
            "rainfall_7d": weather.get("rainfall_7d"),
        },
        "spatial": {
            "query_radius_km": spatial.get("query_radius_km"),
            "critical_asset_count": spatial.get("critical_asset_count", 0),
            "critical_assets": spatial.get("critical_assets", []),
            "protected_area_count": spatial.get("protected_area_count", 0),
            "protected_areas": spatial.get("protected_areas", []),
            "road_town_inventory_available": False,
        },
        "official_warnings": {
            "incident_count": warnings.get("incident_count", 0),
        },
    }


def _data(evidence: Any) -> dict[str, Any]:
    return evidence.get("data", {}) if isinstance(evidence, dict) else {}


def _deltas(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return {}
    return {
        "risk_score": _numeric_delta(current.get("risk_score"), previous.get("risk_score")),
        "hotspot_count_24h": _numeric_delta(
            current.get("hotspots", {}).get("count_24h"),
            previous.get("hotspots", {}).get("count_24h"),
        ),
        "wind_gust_kmh": _numeric_delta(
            current.get("weather", {}).get("wind_gust_kmh"),
            previous.get("weather", {}).get("wind_gust_kmh"),
        ),
        "humidity_min": _numeric_delta(
            current.get("weather", {}).get("humidity_min"),
            previous.get("weather", {}).get("humidity_min"),
        ),
    }


def _numeric_delta(current: Any, previous: Any) -> dict[str, Any] | None:
    if current is None or previous is None:
        return None
    try:
        current_number = float(current)
        previous_number = float(previous)
    except (TypeError, ValueError):
        return None
    return {"current": current_number, "previous": previous_number, "delta": current_number - previous_number}


def _citations_for_run(run: RunRecord) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = [{"title": "Latest completed analysis run", "source": run.run_id}]
    for key, label in [
        ("hotspots", "Hotspot feed"),
        ("weather", "Weather source"),
        ("spatial", "Spatial exposure source"),
        ("official_warnings", "Official warnings"),
    ]:
        evidence = run.evidence.get(key, {})
        if isinstance(evidence, dict):
            citations.append({"title": label, "source": evidence.get("source", key)})
    elastic = run.evidence.get("elastic", {})
    if isinstance(elastic, dict):
        for item in elastic.get("evidence", [])[:3]:
            if isinstance(item, dict):
                citations.append({"title": item.get("title") or item.get("id"), "source": "Elastic MCP"})
    return citations


def _format_named_items(items: list[str], *, empty: str) -> str:
    if not items:
        return empty
    visible = items[:5]
    suffix = f", plus {len(items) - len(visible)} more" if len(items) > len(visible) else ""
    return "; ".join(visible) + suffix
