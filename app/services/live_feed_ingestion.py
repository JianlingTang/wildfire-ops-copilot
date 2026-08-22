from __future__ import annotations

import threading
import time
from collections.abc import Callable

from app.tools.fire_hotspot_tools import refresh_dea_hotspot_cache, seconds_until_dea_refresh
from app.tools.official_warning_tools import refresh_nsw_rfs_warning_cache, seconds_until_nsw_rfs_refresh
from app.tools.provider_utils import external_data_mode

_LIVE_FEED_LOOP_STARTED = False
_MIN_SLEEP_SECONDS = 5.0
_MAX_SLEEP_SECONDS = 60.0


def start_live_feed_ingestion_loop() -> None:
    global _LIVE_FEED_LOOP_STARTED
    if _LIVE_FEED_LOOP_STARTED or external_data_mode() == "demo":
        return
    _LIVE_FEED_LOOP_STARTED = True
    thread = threading.Thread(target=_live_feed_loop, name="live-feed-ingestion", daemon=True)
    thread.start()


def refresh_live_feed_caches_once() -> dict[str, object]:
    return {
        "dea": _refresh_without_raising(refresh_dea_hotspot_cache),
        "nsw_rfs": _refresh_without_raising(refresh_nsw_rfs_warning_cache),
    }


def _live_feed_loop() -> None:
    while True:
        refresh_live_feed_caches_once()
        time.sleep(_next_sleep_seconds())


def _refresh_without_raising(refresh: Callable[[], dict[str, object]]) -> dict[str, object]:
    try:
        return refresh()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _next_sleep_seconds() -> float:
    due_in = min(seconds_until_dea_refresh(), seconds_until_nsw_rfs_refresh())
    return min(_MAX_SLEEP_SECONDS, max(_MIN_SLEEP_SECONDS, due_in))
