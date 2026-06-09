from app.models.schemas import RunRecord


def render_daily_report(run: RunRecord) -> str:
    drivers = "\n".join(
        f"- {driver['factor']}: +{driver['contribution']}"
        for driver in run.risk_assessment.get("drivers", [])
    )
    evidence = "\n".join(_format_evidence_lines(run))
    recommendations = "\n".join(f"- {item}" for item in run.recommendations)
    return f"""# Daily Wildfire Operations Brief

Region: {run.region_name}
Run ID: {run.run_id}
Risk: {run.risk_level} ({run.risk_score}/100)

## Top Risk Drivers
{drivers or "- No drivers available."}

## Evidence Used
{evidence or "- No evidence available."}

## Recommended Actions
{recommendations or "- Continue standard monitoring."}

## Limitations
- Vegetation dryness proxy is unavailable in the MVP.
- Elastic MCP may fall back to deterministic demo evidence if the live retrieval path is unavailable.
"""


def _format_evidence_lines(run: RunRecord) -> list[str]:
    lines: list[str] = []
    hotspots = run.evidence.get("hotspots", {})
    weather = run.evidence.get("weather", {})
    official_warnings = run.evidence.get("official_warnings", {})
    spatial = run.evidence.get("spatial", {})
    elastic = run.evidence.get("elastic", {})

    if hotspots:
        lines.append(f"- Hotspots: {hotspots.get('source', 'Hotspot source')}")
    if weather:
        lines.append(f"- Weather: {weather.get('source', 'Weather source')}")
    if official_warnings:
        lines.append(f"- Warnings: {official_warnings.get('source', 'Official warnings')}")
    if spatial:
        lines.append(f"- Exposure: {spatial.get('source', 'Spatial exposure')}")
    if elastic:
        mode = elastic.get("mode", "demo")
        primary_evidence = elastic.get("evidence", [{}])[0]
        source = primary_evidence.get("source", "Elastic MCP")
        title = primary_evidence.get("title", "Elastic MCP evidence")
        lines.append(f"- Elastic MCP evidence: {title} via {source} ({mode} mode)")

    return lines or ["- No evidence available."]
