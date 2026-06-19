from app.models.schemas import Aoi, ChatRequest
from app.services.monitoring_tasks import create_monitor_task_from_chat


def test_monitor_task_parses_hour_interval_from_user_request() -> None:
    payload = create_monitor_task_from_chat(
        ChatRequest(
            message="Create a monitor task for this state every 2 hours.",
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
            aoi=Aoi(center=(-12.4513, 132.9192), radius_km=50),
        )
    )

    assert payload["monitor_task"].interval_minutes == 120
    assert "every 120 minutes" in payload["answer"]
