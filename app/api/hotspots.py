from fastapi import APIRouter, Query

from app.tools.fire_hotspot_tools import get_australia_hotspots_overview, get_state_hotspot_focus

router = APIRouter(tags=["hotspots"])


@router.get("/hotspots/overview")
def get_hotspots_overview() -> dict:
    return get_australia_hotspots_overview()


@router.get("/hotspots/focus")
def get_hotspots_focus(
    state: str = Query(..., min_length=2, max_length=3),
    radius_km: int = Query(..., gt=0),
) -> dict:
    return get_state_hotspot_focus(state, radius_km)
