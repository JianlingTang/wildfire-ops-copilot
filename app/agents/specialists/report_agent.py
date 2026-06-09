from app.models.schemas import RunRecord
from app.services.firestore_store import store
from app.services.report_renderer import render_daily_report


def create_report_for_run(run: RunRecord | None) -> dict:
    if not run:
        return {"status": "needs_context", "message": "No completed run is available for report generation."}
    report = store.create_report(
        {
            "run_id": run.run_id,
            "type": "daily_brief",
            "title": "Daily Wildfire Operations Brief",
            "markdown": render_daily_report(run),
        }
    )
    store.add_event(run.run_id, "report_agent", "generate_requested_report", "completed", "Generated requested report.")
    return {
        "status": "success",
        "answer": "Generated a report from the latest completed run with Elastic MCP evidence preserved.",
        "report": report.model_dump(),
    }
