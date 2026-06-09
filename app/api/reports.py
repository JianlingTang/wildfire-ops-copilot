from fastapi import APIRouter, HTTPException

from app.agents.specialists.report_agent import create_report_for_run
from app.services.firestore_store import store

router = APIRouter(tags=["reports"])


@router.post("/reports/{run_id}")
def create_report(run_id: str) -> dict:
    run = store.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return create_report_for_run(run)


@router.get("/reports/{report_id}")
def get_report(report_id: str) -> dict:
    report = store.reports.get(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"report": report}
