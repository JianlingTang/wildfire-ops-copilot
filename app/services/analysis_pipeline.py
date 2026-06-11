from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.tools.elastic_mcp_tools import query_elastic_evidence
from app.tools.fire_hotspot_tools import get_fire_hotspots
from app.tools.official_warning_tools import get_official_fire_warnings
from app.tools.provider_utils import coerce_center, coerce_radius_km, external_data_mode
from app.tools.risk_tools import compute_wildfire_risk_score
from app.tools.spatial_tools import get_spatial_exposure_summary
from app.tools.weather_tools import get_weather_forecast

_ANALYSIS_CACHE: dict[str, dict[str, Any]] = {}


@dataclass
class AnalysisComputation:
    evidence: dict[str, Any]
    risk: dict[str, Any]
    recommendations: list[str]
    cache_hit: bool = False
    hotspot_reused: bool = False
    spatial_soft_timeout: bool = False


def reset_analysis_cache() -> None:
    _ANALYSIS_CACHE.clear()


def compute_analysis(
    region: dict[str, Any],
    *,
    recommendations: list[str],
    elastic_query: str,
    elastic_time_window: str = "30d",
    elastic_evidence_type: str = "operational_evidence",
) -> AnalysisComputation:
    cache_key = _analysis_cache_key(
        region,
        elastic_query=elastic_query,
        elastic_time_window=elastic_time_window,
        elastic_evidence_type=elastic_evidence_type,
    )
    cached = _get_cached_analysis(cache_key)
    if cached:
        return AnalysisComputation(
            evidence=deepcopy(cached["evidence"]),
            risk=deepcopy(cached["risk"]),
            recommendations=list(cached["recommendations"]),
            cache_hit=True,
            hotspot_reused=bool(cached["hotspot_reused"]),
            spatial_soft_timeout=bool(cached["spatial_soft_timeout"]),
        )

    evidence, hotspot_reused, spatial_soft_timeout = _collect_evidence(
        region,
        elastic_query=elastic_query,
        elastic_time_window=elastic_time_window,
        elastic_evidence_type=elastic_evidence_type,
    )
    risk = compute_wildfire_risk_score(evidence)
    result = AnalysisComputation(
        evidence=evidence,
        risk=risk,
        recommendations=list(recommendations),
        cache_hit=False,
        hotspot_reused=hotspot_reused,
        spatial_soft_timeout=spatial_soft_timeout,
    )
    _store_cached_analysis(cache_key, result)
    return result


def _collect_evidence(
    region: dict[str, Any],
    *,
    elastic_query: str,
    elastic_time_window: str,
    elastic_evidence_type: str,
) -> tuple[dict[str, Any], bool, bool]:
    hotspot_payload = deepcopy(region.get("hotspots"))
    hotspot_reused = hotspot_payload is not None

    spatial_executor = ThreadPoolExecutor(max_workers=1)
    spatial_started = time.monotonic()
    spatial_future = spatial_executor.submit(get_spatial_exposure_summary, region["aoi"])
    spatial_soft_timeout = False

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                "weather": executor.submit(get_weather_forecast, region["aoi"]),
                "official_warnings": executor.submit(
                    get_official_fire_warnings, region["region_id"], region["aoi"]
                ),
                "elastic": executor.submit(
                    query_elastic_evidence,
                    elastic_query,
                    region["region_name"],
                    elastic_time_window,
                    elastic_evidence_type,
                ),
            }
            if hotspot_payload is None:
                futures["hotspots"] = executor.submit(get_fire_hotspots, region["aoi"])

            results = {name: future.result() for name, future in futures.items()}

        if hotspot_payload is None:
            hotspot_payload = results["hotspots"]

        remaining = max(0.0, _spatial_soft_timeout_seconds() - (time.monotonic() - spatial_started))
        try:
            spatial = spatial_future.result(timeout=remaining)
        except FutureTimeout:
            spatial_soft_timeout = True
            spatial = {"status": "error", "message": "Spatial exposure request exceeded the soft timeout."}
        except Exception as exc:  # pragma: no cover - defensive path
            spatial = {"status": "error", "message": f"Spatial exposure request failed: {exc}"}
    finally:
        spatial_executor.shutdown(wait=False, cancel_futures=True)

    evidence = {
        "region_context": deepcopy(region["region_context"]),
        "hotspots": hotspot_payload,
        "weather": results["weather"],
        "official_warnings": results["official_warnings"],
        "spatial": spatial,
        "elastic": results["elastic"],
    }
    evidence["risk_timeseries"] = _build_risk_timeseries(evidence)
    return evidence, hotspot_reused, spatial_soft_timeout


def _build_risk_timeseries(evidence: dict[str, Any]) -> dict[str, Any]:
    baseline = compute_wildfire_risk_score(evidence)
    current_score = int(baseline["risk_score"])
    today = datetime.now(UTC).date()
    points = []
    for offset in range(-5, 6):
        adjustment = _timeseries_adjustment(offset, current_score)
        score = min(100, max(0, current_score + adjustment))
        point_type = "historical" if offset < 0 else "forecast" if offset > 0 else "current"
        points.append(
            {
                "date": (today + timedelta(days=offset)).isoformat(),
                "risk_score": score,
                "risk_level": _risk_level_for_score(score),
                "type": point_type,
            }
        )
    return {
        "source": "deterministic_risk_timeseries",
        "window_days": 5,
        "points": points,
        "caveat": (
            "Historical and forecast points are estimates from current AOI evidence for operational planning."
        ),
    }


def _timeseries_adjustment(offset: int, current_score: int) -> int:
    if offset == 0:
        return 0
    direction = 1 if current_score >= 70 else -1 if current_score <= 40 else 0
    if offset < 0:
        return -direction * min(10, abs(offset) * 2) - max(0, 5 - abs(offset))
    return direction * max(0, 6 - offset) - max(0, offset - 2)


def _risk_level_for_score(score: int) -> str:
    if score >= 85:
        return "EXTREME"
    if score >= 65:
        return "HIGH"
    if score >= 35:
        return "MODERATE"
    return "LOW"


def _analysis_cache_key(
    region: dict[str, Any],
    *,
    elastic_query: str,
    elastic_time_window: str,
    elastic_evidence_type: str,
) -> str:
    center = region.get("region_context", {}).get("center")
    if not center:
        lat, lon = coerce_center(region["aoi"])
    else:
        lat, lon = float(center[0]), float(center[1])
    radius_km = float(region.get("region_context", {}).get("radius_km") or coerce_radius_km(region["aoi"]))
    return "|".join(
        [
            external_data_mode(),
            region["region_id"],
            f"{lat:.4f}",
            f"{lon:.4f}",
            f"{radius_km:.1f}",
            elastic_query,
            elastic_time_window,
            elastic_evidence_type,
        ]
    )


def _analysis_cache_ttl_seconds() -> float:
    raw = os.getenv("ANALYSIS_CACHE_TTL_SECONDS", "180").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 180.0


def _spatial_soft_timeout_seconds() -> float:
    raw = os.getenv("ANALYSIS_SPATIAL_SOFT_TIMEOUT_SECONDS", "10").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 10.0


def _get_cached_analysis(cache_key: str) -> dict[str, Any] | None:
    entry = _ANALYSIS_CACHE.get(cache_key)
    if not entry:
        return None
    expires_at = entry.get("expires_at")
    if not isinstance(expires_at, datetime) or expires_at <= datetime.now(UTC):
        _ANALYSIS_CACHE.pop(cache_key, None)
        return None
    return deepcopy(entry)


def _store_cached_analysis(cache_key: str, result: AnalysisComputation) -> None:
    _ANALYSIS_CACHE[cache_key] = {
        "expires_at": datetime.now(UTC) + timedelta(seconds=_analysis_cache_ttl_seconds()),
        "evidence": deepcopy(result.evidence),
        "risk": deepcopy(result.risk),
        "recommendations": list(result.recommendations),
        "hotspot_reused": result.hotspot_reused,
        "spatial_soft_timeout": result.spatial_soft_timeout,
    }
