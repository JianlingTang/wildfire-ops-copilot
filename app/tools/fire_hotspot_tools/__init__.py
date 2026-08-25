"""Fire hotspot data: live DEA feed ingestion/cache, region resolution, and
the read API used by chat tools and the /hotspots API routes.

Package layout:
- constants.py: shared region/state/cache-tuning constants.
- geo_math.py: pure clustering/centroid/sampling math over hotspot rows.
- format.py: AOI validation and payload/overview formatting.
- demo_data.py: static hotspot rows used when WILDFIRE_DATA_MODE=demo.
- cache.py: the DEA feed fetch and the process-wide overview/rows cache.
- query.py: the public read API (get_fire_hotspots, get_state_hotspot_focus,
  get_australia_hotspots_overview).
- region.py: resolve_operational_region and its region-selection strategies.

_get_or_load_australia_hotspot_rows is re-exported here because tests
monkeypatch it at this dotted path (app.tools.fire_hotspot_tools.
_get_or_load_australia_hotspot_rows) — see the comment in query.py.
"""

from __future__ import annotations

from app.tools.fire_hotspot_tools.cache import (
    _AUSTRALIA_OVERVIEW_CACHE,
    _AUSTRALIA_OVERVIEW_CACHE_LOCK,
    _get_or_load_australia_hotspot_rows,
    refresh_dea_hotspot_cache,
    seconds_until_dea_refresh,
)
from app.tools.fire_hotspot_tools.query import (
    get_australia_hotspots_overview,
    get_fire_hotspots,
    get_state_hotspot_focus,
)
from app.tools.fire_hotspot_tools.region import resolve_operational_region

__all__ = [
    "get_fire_hotspots",
    "get_australia_hotspots_overview",
    "get_state_hotspot_focus",
    "resolve_operational_region",
    "refresh_dea_hotspot_cache",
    "seconds_until_dea_refresh",
    "_AUSTRALIA_OVERVIEW_CACHE",
    "_AUSTRALIA_OVERVIEW_CACHE_LOCK",
    "_get_or_load_australia_hotspot_rows",
]
