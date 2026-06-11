from app.models.schemas import RunRecord


def render_daily_report(run: RunRecord) -> str:
    drivers = "\n".join(
        f"- {driver['factor']}: +{driver['contribution']}"
        for driver in run.risk_assessment.get("drivers", [])
    )
    evidence = "\n".join(_format_evidence_lines(run))
    elastic_files = "\n".join(_format_elastic_file_lines(run))
    assets_monitoring = "\n".join(_format_assets_monitoring_lines(run))
    recommendations = "\n".join(f"- {item}" for item in run.recommendations)
    return f"""# Daily Wildfire Operations Brief

Region: {run.region_name}
Run ID: {run.run_id}
Risk: {run.risk_level} ({run.risk_score}/100)

## Top Risk Drivers
{drivers or "- No drivers available."}

## Evidence Used
{evidence or "- No evidence available."}

## Assets and Monitoring
{assets_monitoring or "- No spatial assets or protected areas were returned for this AOI."}

## Elastic Files Cited
{elastic_files or "- No Elastic files cited."}

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
        evidence_items = elastic.get("evidence") or [{}]
        primary_evidence = evidence_items[0]
        source = primary_evidence.get("source", "Elastic MCP")
        title = primary_evidence.get("title", "Elastic MCP evidence")
        lines.append(f"- Elastic MCP evidence: {title} via {source} ({mode} mode)")

    return lines or ["- No evidence available."]


def _format_elastic_file_lines(run: RunRecord) -> list[str]:
    elastic = run.evidence.get("elastic", {})
    evidence_items = elastic.get("evidence") if isinstance(elastic, dict) else []
    if not isinstance(evidence_items, list):
        return []
    lines: list[str] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("evidence_id") or item.get("doc_id") or item.get("id") or "unknown-file"
        title = item.get("title") or "Elastic MCP evidence"
        summary = str(item.get("summary") or "").strip()
        suffix = f" - {summary[:180]}" if summary else ""
        lines.append(f"- {evidence_id}: {title}{suffix}")
    return lines


def _format_assets_monitoring_lines(run: RunRecord) -> list[str]:
    spatial = run.evidence.get("spatial", {})
    data = spatial.get("data", {}) if isinstance(spatial, dict) else {}
    critical_assets = [str(item) for item in data.get("critical_assets", []) if item]
    protected_areas = [str(item) for item in data.get("protected_areas", []) if item]
    critical_count = int(data.get("critical_asset_count", len(critical_assets)) or 0)
    protected_count = int(data.get("protected_area_count", len(protected_areas)) or 0)
    radius = data.get("query_radius_km")
    lines: list[str] = []
    if radius:
        lines.append(f"- AOI exposure radius: {radius} km.")
    lines.append(f"- Critical assets identified: {critical_count}.")
    if critical_assets:
        lines.append(f"- Asset watchlist: {_join_names(critical_assets)}.")
    lines.append(f"- Parks or protected natural areas identified: {protected_count}.")
    if protected_areas:
        lines.append(f"- Protected-area watchlist: {_join_names(protected_areas)}.")
    if critical_count or protected_count:
        lines.append(
            "- AI monitoring recommendation: monitor hotspot movement toward listed assets and protected areas, "
            "wind direction and gust changes, humidity minima, new official warnings, and any access-route constraints."
        )
    else:
        lines.append(
            "- AI monitoring recommendation: continue hotspot, wind, humidity, rainfall, and official-warning "
            "monitoring; "
            "refresh spatial exposure if the AOI shifts."
        )
    return lines


def _join_names(values: list[str]) -> str:
    visible = values[:6]
    suffix = f", plus {len(values) - len(visible)} more" if len(values) > len(visible) else ""
    return "; ".join(visible) + suffix
