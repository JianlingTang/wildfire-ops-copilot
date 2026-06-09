from fastapi import APIRouter

from app.services.monitoring_tasks import list_monitor_tasks

router = APIRouter()


@router.get("/monitor-tasks")
def get_monitor_tasks() -> dict:
    return {"monitor_tasks": list_monitor_tasks()}
