from app.models.schemas import ManualRunRequest
from app.services.analysis_pipeline import compute_analysis
from app.services.firestore_store import store
from app.services.report_renderer import render_daily_report
from app.tools.fire_hotspot_tools import resolve_operational_region


def run_daily_intelligence(request: ManualRunRequest, trigger_type: str) -> dict:
    region = resolve_operational_region(request.region_id, request.region_name, request.aoi)
    run = store.create_run(region["region_id"], region["region_name"])
    store.add_event(
        run.run_id,
        "wildfire_ops_orchestrator",
        "route_request",
        "completed",
        f"Started {trigger_type} analysis.",
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
        "Prioritize inspection near recent hotspot cluster and exposed road corridor.",
        "Prepare a public advisory draft for review if conditions deteriorate.",
        "Continue monitoring wind gust and humidity changes through the next forecast cycle.",
    ]
    analysis = compute_analysis(
        region,
        recommendations=recommendations,
        elastic_query="wildfire operational risk pattern",
        elastic_evidence_type="historical_incident",
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
            "data_collection_team",
            "gather_operational_inputs",
            "completed",
            "Gathered hotspot, weather, warning, spatial, and Elastic evidence in parallel.",
        )
        if analysis.spatial_soft_timeout:
            store.add_event(
                run.run_id,
                "data_collection_team",
                "soft_timeout_spatial_exposure",
                "completed",
                "Spatial exposure exceeded the soft timeout and used fallback data.",
            )
    store.add_event(
        run.run_id,
        "risk_scoring_service",
        "compute_risk_score",
        "completed",
        f"Computed {analysis.risk['risk_level']} risk.",
    )

    completed = store.complete_run(run.run_id, analysis.evidence, analysis.risk, recommendations)
    store.add_event(run.run_id, "daily_intelligence_workflow", "store_run_result", "completed", "Stored run result.")

    report_markdown = render_daily_report(completed)
    report = store.create_report(
        {
            "run_id": completed.run_id,
            "type": "daily_brief",
            "title": "Daily Wildfire Operations Brief",
            "markdown": report_markdown,
        }
    )
    store.add_event(run.run_id, "report_agent", "generate_daily_report", "completed", "Generated markdown report.")

    alert = None
    if completed.risk_level in {"HIGH", "EXTREME"}:
        alert = store.create_alert(
            {
                "run_id": completed.run_id,
                "region_id": completed.region_id,
                "region_name": completed.region_name,
                "severity": completed.risk_level,
                "reason": (
                    f"Risk score is {completed.risk_score} with elevated wind, "
                    "low humidity, and hotspot activity."
                ),
                "evidence_ids": ["elastic_demo_001"],
                "recommended_next_action": (
                    "Review public advisory and field team brief drafts before any external action."
                ),
            }
        )
        store.add_event(
            run.run_id,
            "daily_intelligence_workflow",
            "create_alert",
            "completed",
            "Created high-risk alert.",
        )

    return {"run": completed, "report": report, "alert": alert}
