from datetime import UTC, datetime

from app.agents.specialists.what_if_agent import run_what_if
from app.models.schemas import RunRecord


def test_rainfall_increase_uses_positive_multiplier_and_reports_driver_change() -> None:
    run = RunRecord(
        run_id="run_rain",
        region_id="state_wa",
        region_name="Western Australia hotspot focus",
        status="completed",
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        evidence={
            "weather": {"data": {"wind_gust_max": 45, "humidity_min": 24, "rainfall_7d": 5}},
            "hotspots": {"data": {"count_24h": 3}},
            "official_warnings": {"data": {"warning_level": "ADVICE"}},
            "spatial": {"data": {"critical_asset_count": 4}},
        },
        risk_assessment={},
        recommendations=[],
    )

    result = run_what_if("What if rain increases by 300%?", run)

    assert result["scenario_delta"]["rainfall_multiplier"] == 4
    assert result["weather_delta"]["rainfall_7d"] == {"baseline": 5, "scenario": 20}
    assert result["driver_changes"]["low_rainfall"] == {"baseline": 8, "scenario": 0}
    assert "rainfall_7d 5 -> 20" in result["answer"]
    assert "low_rainfall 8 -> 0" in result["answer"]
