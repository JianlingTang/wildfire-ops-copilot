"""DEA hotspot feed fetch and the process-wide overview/rows cache.

_get_or_load_australia_hotspot_rows is monkeypatched directly by tests via
app.tools.fire_hotspot_tools._get_or_load_australia_hotspot_rows, so its
callers in query.py/region.py resolve it through the package's own namespace
(see the comment there) rather than importing it directly from this module.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.tools.fire_hotspot_tools.constants import DEA_HOTSPOTS_URL, DEA_REFRESH_INTERVAL_SECONDS
from app.tools.fire_hotspot_tools.demo_data import _demo_australia_hotspot_rows
from app.tools.fire_hotspot_tools.format import _build_australia_hotspot_overview
from app.tools.provider_utils import external_data_mode, http_user_agent, request_timeout_seconds

_AUSTRALIA_OVERVIEW_CACHE: dict[str, Any] = {
    "etag": None,
    "last_modified": None,
    "last_checked_at": None,
    "last_refreshed_at": None,
    "next_refresh_at": None,
    "payload": None,
    "refresh_error": None,
    "refreshing": False,
    "rows": None,
}
_AUSTRALIA_OVERVIEW_CACHE_LOCK = threading.Lock()


def refresh_dea_hotspot_cache(force: bool = False) -> dict[str, Any]:
    now = datetime.now(UTC)
    skip_response, etag, last_modified = _begin_refresh_or_skip(now, force)
    if skip_response is not None:
        return skip_response

    headers = {"User-Agent": http_user_agent()}
    if etag:
        headers["If-None-Match"] = str(etag)
    if last_modified:
        headers["If-Modified-Since"] = str(last_modified)

    try:
        return _apply_refresh_response(headers)
    except Exception as exc:
        _record_refresh_failure(exc)
        raise


def _begin_refresh_or_skip(now: datetime, force: bool) -> tuple[dict[str, Any] | None, Any, Any]:
    with _AUSTRALIA_OVERVIEW_CACHE_LOCK:
        next_refresh_at = _AUSTRALIA_OVERVIEW_CACHE.get("next_refresh_at")
        if (
            not force
            and isinstance(next_refresh_at, datetime)
            and next_refresh_at > now
            and _AUSTRALIA_OVERVIEW_CACHE.get("payload") is not None
        ):
            return {"status": "skipped", "reason": "fresh"}, None, None
        if _AUSTRALIA_OVERVIEW_CACHE.get("refreshing"):
            return {"status": "skipped", "reason": "refresh_in_progress"}, None, None
        _AUSTRALIA_OVERVIEW_CACHE["refreshing"] = True
        return None, _AUSTRALIA_OVERVIEW_CACHE.get("etag"), _AUSTRALIA_OVERVIEW_CACHE.get("last_modified")


def _apply_refresh_response(headers: dict[str, str]) -> dict[str, Any]:
    features, response_headers, status_code = _fetch_dea_features(headers=headers)
    now = datetime.now(UTC)
    if status_code == 304:
        with _AUSTRALIA_OVERVIEW_CACHE_LOCK:
            _AUSTRALIA_OVERVIEW_CACHE["last_checked_at"] = now
            _AUSTRALIA_OVERVIEW_CACHE["next_refresh_at"] = now + timedelta(seconds=DEA_REFRESH_INTERVAL_SECONDS)
            _AUSTRALIA_OVERVIEW_CACHE["refresh_error"] = None
            _AUSTRALIA_OVERVIEW_CACHE["refreshing"] = False
        return {"status": "not_modified"}

    rows = [row for row in (_dea_feature_to_row(feature) for feature in features) if row]
    if not rows:
        raise ValueError("DEA Hotspots feed returned no usable hotspot rows.")
    payload = _build_australia_hotspot_overview(rows, mode="live", source="DEA Hotspots recent feed")
    _store_cached_australia_overview(
        payload,
        rows,
        etag=response_headers.get("etag"),
        last_modified=response_headers.get("last-modified"),
    )
    return {"status": "refreshed", "row_count": len(rows)}


def _record_refresh_failure(exc: Exception) -> None:
    failed_at = datetime.now(UTC)
    with _AUSTRALIA_OVERVIEW_CACHE_LOCK:
        _AUSTRALIA_OVERVIEW_CACHE["last_checked_at"] = failed_at
        _AUSTRALIA_OVERVIEW_CACHE["next_refresh_at"] = failed_at + timedelta(seconds=DEA_REFRESH_INTERVAL_SECONDS)
        _AUSTRALIA_OVERVIEW_CACHE["refresh_error"] = str(exc)
        _AUSTRALIA_OVERVIEW_CACHE["refreshing"] = False


def seconds_until_dea_refresh() -> float:
    with _AUSTRALIA_OVERVIEW_CACHE_LOCK:
        next_refresh_at = _AUSTRALIA_OVERVIEW_CACHE.get("next_refresh_at")
    if not isinstance(next_refresh_at, datetime):
        return 0.0
    return max(0.0, (next_refresh_at - datetime.now(UTC)).total_seconds())


def _fetch_dea_features(*, headers: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], httpx.Headers, int]:
    response = httpx.get(
        DEA_HOTSPOTS_URL,
        headers=headers or {"User-Agent": http_user_agent()},
        timeout=request_timeout_seconds(default=15.0),
    )
    if response.status_code == 304:
        return [], response.headers, response.status_code
    response.raise_for_status()
    payload = response.json()
    return payload.get("features", []), response.headers, response.status_code


def _dea_feature_to_row(feature: dict[str, Any]) -> dict[str, Any] | None:
    geometry = feature.get("geometry", {})
    coordinates = geometry.get("coordinates", [])
    if len(coordinates) != 2:
        return None
    properties = feature.get("properties", {})
    return {
        "lat": float(coordinates[1]),
        "lon": float(coordinates[0]),
        "confidence": str(properties.get("confidence", "unknown")),
        "detected_at": _coerce_datetime(properties.get("datetime")),
        "power": properties.get("power"),
        "satellite": properties.get("satellite"),
        "sensor": properties.get("sensor"),
        "state": str(properties.get("australian_state", "")).strip() or None,
    }


def _coerce_datetime(raw_value: Any) -> datetime | None:
    if not raw_value:
        return None
    value = str(raw_value).strip()
    if len(value) == 15 and "T" in value and value.count(":") == 0:
        value = f"{value[:11]}{value[11:13]}:{value[13:15]}:00"
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _get_cached_australia_overview(include_stale: bool = False) -> dict | None:
    with _AUSTRALIA_OVERVIEW_CACHE_LOCK:
        payload = _AUSTRALIA_OVERVIEW_CACHE.get("payload")
        refresh_error = _AUSTRALIA_OVERVIEW_CACHE.get("refresh_error")
    if not payload:
        return None
    cached = deepcopy(payload)
    if include_stale and refresh_error:
        cached["message"] = f"Serving cached Australia hotspot overview after refresh failure: {refresh_error}"
    return cached


def _get_cached_australia_rows(include_stale: bool = False) -> list[dict[str, Any]] | None:
    with _AUSTRALIA_OVERVIEW_CACHE_LOCK:
        rows = _AUSTRALIA_OVERVIEW_CACHE.get("rows")
    if not rows:
        return None
    return deepcopy(rows)


def _store_cached_australia_overview(
    payload: dict,
    rows: list[dict[str, Any]],
    *,
    etag: str | None = None,
    last_modified: str | None = None,
) -> None:
    now = datetime.now(UTC)
    with _AUSTRALIA_OVERVIEW_CACHE_LOCK:
        _AUSTRALIA_OVERVIEW_CACHE["payload"] = deepcopy(payload)
        _AUSTRALIA_OVERVIEW_CACHE["rows"] = deepcopy(rows)
        if etag:
            _AUSTRALIA_OVERVIEW_CACHE["etag"] = etag
        if last_modified:
            _AUSTRALIA_OVERVIEW_CACHE["last_modified"] = last_modified
        _AUSTRALIA_OVERVIEW_CACHE["last_checked_at"] = now
        _AUSTRALIA_OVERVIEW_CACHE["last_refreshed_at"] = now
        _AUSTRALIA_OVERVIEW_CACHE["next_refresh_at"] = now + timedelta(seconds=DEA_REFRESH_INTERVAL_SECONDS)
        _AUSTRALIA_OVERVIEW_CACHE["refresh_error"] = None
        _AUSTRALIA_OVERVIEW_CACHE["refreshing"] = False


def _get_or_load_australia_hotspot_rows() -> tuple[list[dict[str, Any]], str, str, bool]:
    if external_data_mode() == "demo":
        rows = _demo_australia_hotspot_rows()
        payload = _build_australia_hotspot_overview(rows, mode="demo", source="DEA Hotspots demo overview")
        _store_cached_australia_overview(payload, rows)
        return rows, "demo", "DEA Hotspots demo overview", False

    cached_rows = _get_cached_australia_rows(include_stale=True)
    cached_payload = _get_cached_australia_overview(include_stale=True)
    if cached_rows and cached_payload:
        return (
            cached_rows,
            str(cached_payload.get("mode", "live")),
            str(cached_payload.get("source", "DEA Hotspots recent feed")),
            True,
        )

    raise RuntimeError("Live DEA hotspot cache is not ready yet. Background ingestion has not completed.")
