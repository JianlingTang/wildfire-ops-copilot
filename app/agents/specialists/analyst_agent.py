from app.models.schemas import Aoi, RunRecord


def answer_operational_question(
    message: str,
    run: RunRecord | None,
    region_name: str | None = None,
    aoi: Aoi | None = None,
) -> dict:
    if not run:
        if region_name and aoi:
            return answer_focused_aoi_question(message, region_name, aoi)
        return {
            "status": "needs_context",
            "answer": "No completed run is available yet. Start a manual or daily analysis first.",
        }

    drivers = run.risk_assessment.get("drivers", [])
    top_drivers = ", ".join(driver["factor"] for driver in drivers[:3]) or "no dominant drivers"
    return {
        "status": "success",
        "answer": (
            f"{run.region_name} is currently {run.risk_level} at {run.risk_score}/100. "
            f"The leading drivers are {top_drivers}. The first inspection priority is the recent hotspot cluster "
            "near exposed road and town assets."
        ),
        "evidence_keys": list(run.evidence.keys()),
        "recommendations": run.recommendations,
    }


def answer_focused_aoi_question(message: str, region_name: str, aoi: Aoi) -> dict:
    lowered = message.lower()
    radius = int(aoi.radius_km)
    center_text = _format_center(aoi)

    if "what if" in lowered:
        answer = (
            f"For {region_name}, a wind increase would raise concern inside the {radius} km focused AOI, "
            "especially around the densest hotspot cluster and any exposed road or town assets. "
            "Without a completed risk run I cannot provide a scored baseline comparison yet, but operationally I would "
            "treat stronger wind as a trigger to prioritize perimeter inspection, access routes, and public messaging "
            "readiness."
        )
    elif "changed" in lowered or "since yesterday" in lowered:
        answer = (
            f"{region_name} is focused for review, but this session does not yet have a completed analysis baseline "
            f"to compare against. The agent can still use the selected {radius} km AOI at {center_text} as context; "
            "run analysis when you need a traceable "
            "hotspot, weather, warning, exposure, and Elastic MCP evidence comparison."
        )
    elif "inspect" in lowered or "first" in lowered or "priority" in lowered:
        answer = (
            f"For {region_name}, inspect the most active hotspot cluster inside the {radius} km AOI first, then check "
            "nearby access roads and exposed settlement edges. If conditions worsen, prioritize areas downwind of the "
            "cluster before lower-density detections."
        )
    elif "why" in lowered or "risk" in lowered or "high" in lowered:
        answer = (
            f"{region_name} has enough AOI context for an initial operational answer: the focused area is centered "
            f"at {center_text} with a {radius} km radius around the densest live hotspot cluster. The main "
            "pre-analysis concerns are hotspot density, wind exposure, "
            "low humidity potential, official warning proximity, and nearby roads or town assets."
        )
    else:
        answer = (
            f"{region_name} is the active focused AOI. I can answer operational questions using the selected "
            f"{radius} km radius and hotspot focus context now; run analysis when you need the full scored evidence "
            "package and report."
        )

    return {
        "status": "success",
        "answer": answer,
        "context": {
            "region_name": region_name,
            "center": list(aoi.center) if aoi.center else None,
            "radius_km": aoi.radius_km,
            "source": "focused_aoi_context",
        },
        "recommendations": [
            "Inspect the densest hotspot cluster first.",
            "Check exposed access roads and nearby settlement edges.",
            "Run full analysis before issuing external guidance.",
        ],
    }


def _format_center(aoi: Aoi) -> str:
    if not aoi.center:
        return "the selected map center"
    lat, lon = aoi.center
    return f"{lat:.3f}, {lon:.3f}"
