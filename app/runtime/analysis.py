from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import AlertRecord, ChatRequest, ReportRecord, RunRecord
from app.services.analysis_pipeline import compute_analysis
from app.services.firestore_store import store
from app.services.report_renderer import render_daily_report
from app.tools.fire_hotspot_tools import resolve_operational_region


@dataclass
class AnalysisArtifacts:
    run: RunRecord
    report: ReportRecord
    alert: AlertRecord | None


def execute_analysis_request(request: ChatRequest, *, route_label: str) -> AnalysisArtifacts:
    region = resolve_operational_region(
        request.region_id,
        request.region_name or _region_name_for(request.region_id),
        request.aoi,
        respect_explicit_aoi=bool(request.aoi and request.aoi.center),
    )
    run = store.create_run(region["region_id"], region["region_name"])
    store.add_event(
        run.run_id,
        route_label,
        "route_chat_analysis_request",
        "completed",
        "Accepted a chat-driven analysis request.",
    )
    if region["region_context"]["selection_mode"] in {"auto_live_hotspot", "demo_auto_live_hotspot"}:
        store.add_event(
            run.run_id,
            "wildfire_ops_orchestrator",
            "select_live_hotspot_region",
            "completed",
            f"Auto-selected {region['region_name']} from live Australian hotspot activity.",
        )
    recommendations = [
        "Inspect the hotspot cluster near exposed road and town assets first.",
        "Keep a public advisory draft ready for human approval if winds deteriorate.",
        "Continue monitoring Elastic MCP evidence and official warnings for similar escalation patterns.",
    ]
    analysis = compute_analysis(
        region,
        recommendations=recommendations,
        elastic_query="wildfire operational evidence",
    )
    if analysis.cache_hit:
        store.add_event(
            run.run_id,
            "analysis_cache",
            "reuse_cached_analysis_inputs",
            "completed",
            "Reused cached AOI analysis inputs and risk assessment.",
        )
    else:
        store.add_event(
            run.run_id,
            "elastic_evidence_provider",
            "query_elastic_mcp_evidence",
            "completed",
            f"Queried Elastic MCP evidence ({analysis.evidence['elastic'].get('mode', 'unknown')} mode).",
        )
        store.add_event(
            run.run_id,
            "data_collection_team",
            "gather_weather_hotspots_and_exposure",
            "completed",
            "Gathered hotspot, weather, warning, and exposure inputs in parallel.",
        )
        if analysis.spatial_soft_timeout:
            store.add_event(
                run.run_id,
                "data_collection_team",
                "soft_timeout_spatial_exposure",
                "completed",
                "Spatial exposure exceeded the soft timeout and used fallback data.",
            )
    completed = store.complete_run(run.run_id, analysis.evidence, analysis.risk, recommendations)
    store.add_event(
        run.run_id,
        "risk_scoring_service",
        "compute_risk_assessment",
        "completed",
        f"Computed {completed.risk_level} risk at {completed.risk_score}/100.",
    )

    report = store.create_report(
        {
            "run_id": completed.run_id,
            "type": "daily_brief",
            "title": "Daily Wildfire Operations Brief",
            "markdown": render_daily_report(completed),
        }
    )
    store.add_event(
        run.run_id,
        "report_agent",
        "generate_daily_report",
        "completed",
        "Generated the daily report with Elastic MCP evidence noted as "
        f"{analysis.evidence['elastic'].get('mode', 'unknown')} mode.",
    )

    alert = None
    if completed.risk_level in {"HIGH", "EXTREME"}:
        evidence_id = _primary_elastic_evidence_id(analysis.evidence["elastic"])
        alert = store.create_alert(
            {
                "run_id": completed.run_id,
                "region_id": completed.region_id,
                "region_name": completed.region_name,
                "severity": completed.risk_level,
                "reason": (
                    f"Risk score is {completed.risk_score} with elevated wind, "
                    "low humidity, hotspot activity, and corroborating Elastic MCP evidence."
                ),
                "evidence_ids": [evidence_id] if evidence_id else [],
                "recommended_next_action": (
                    "Review the public advisory draft before any external communication."
                ),
            }
        )
        store.add_event(
            run.run_id,
            "alerting_workflow",
            "create_high_risk_alert",
            "completed",
            "Created an alert from the high-risk analysis result.",
        )
    else:
        store.add_event(
            run.run_id,
            "alerting_workflow",
            "complete_without_alert",
            "completed",
            "Completed the analysis without creating an alert.",
        )

    return AnalysisArtifacts(run=completed, report=report, alert=alert)


def _primary_elastic_evidence_id(elastic_payload: dict) -> str | None:
    evidence = elastic_payload.get("evidence") or []
    if not evidence:
        return None
    evidence_id = evidence[0].get("evidence_id")
    return str(evidence_id) if evidence_id else None


def _region_name_for(region_id: str) -> str:
    return region_id.replace("_", " ").title()
