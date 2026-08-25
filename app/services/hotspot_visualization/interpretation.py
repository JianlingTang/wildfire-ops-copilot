"""Plain-text AI interpretation summary for the hotspot visualization."""

from __future__ import annotations

from typing import Any


def _interpretation(
    region_name: str,
    hotspots: list[dict[str, Any]],
    cluster: dict[str, Any],
    radius_km: float,
) -> dict[str, Any]:
    count = len(hotspots)
    summary, recommendation = _summary_and_recommendation(region_name, count, radius_km)
    return {
        "summary": summary,
        "cluster_center": [round(cluster["center"][0], 5), round(cluster["center"][1], 5)],
        "priority": "Priority 1 contour" if count else "Monitor",
        "recommendation": recommendation,
        "caveat": "Satellite hotspots indicate thermal anomalies, not confirmed fire perimeter or fire size.",
    }


def _summary_and_recommendation(region_name: str, count: int, radius_km: float) -> tuple[str, str]:
    if count == 0:
        summary = f"{region_name} has no rendered hotspot detections inside the selected AOI."
        recommendation = "Keep the AOI watch active and rerun visualization when new detections arrive."
        return summary, recommendation
    summary = (
        f"{region_name} contains a dominant hotspot concentration with {count} rendered detections "
        f"inside the {radius_km:g} km AOI."
    )
    recommendation = (
        "Inspect the Priority 1 contour first, then check downwind access routes and exposed settlement edges."
    )
    return summary, recommendation


def _interpretation_text(interpretation: dict[str, Any]) -> str:
    lines = [
        f"Summary: {interpretation['summary']}",
        f"Priority: {interpretation['priority']}",
        f"Cluster center: {interpretation['cluster_center'][0]}, {interpretation['cluster_center'][1]}",
        f"Recommendation: {interpretation['recommendation']}",
        f"Caveat: {interpretation['caveat']}",
    ]
    return "\n".join(lines) + "\n"
