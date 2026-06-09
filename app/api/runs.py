from fastapi import APIRouter, HTTPException

from app.agents.root_agent import run_daily, run_manual
from app.models.schemas import DailyRunRequest, ManualRunRequest
from app.services.firestore_store import store

router = APIRouter(tags=["runs"])


@router.post("/runs/daily")
def create_daily_run(request: DailyRunRequest | None = None) -> dict:
    return run_daily()


@router.post("/runs/manual")
def create_manual_run(request: ManualRunRequest) -> dict:
    return run_manual(request)


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = store.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run": run}


@router.get("/runs/{run_id}/events")
def get_run_events(run_id: str) -> dict:
    if run_id not in store.runs:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"events": store.events.get(run_id, [])}
