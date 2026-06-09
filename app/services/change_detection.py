from typing import Any


def detect_material_change(previous_snapshot: dict[str, Any] | None, latest_snapshot: dict[str, Any]) -> dict:
    if not previous_snapshot:
        return {
            "status": "success",
            "material_change": True,
            "changes": ["Initial baseline established for monitored region."],
        }

    changes: list[str] = []
    previous_score = previous_snapshot.get("risk_score", 0)
    latest_score = latest_snapshot.get("risk_score", 0)
    if latest_score - previous_score >= 10:
        changes.append(f"Risk score increased by {latest_score - previous_score} points.")

    previous_hotspots = previous_snapshot.get("hotspot_count", 0)
    latest_hotspots = latest_snapshot.get("hotspot_count", 0)
    if latest_hotspots > previous_hotspots:
        changes.append(f"Hotspot count increased from {previous_hotspots} to {latest_hotspots}.")

    previous_warning = previous_snapshot.get("warning_level")
    latest_warning = latest_snapshot.get("warning_level")
    if latest_warning and latest_warning != previous_warning:
        changes.append(f"Official warning changed from {previous_warning or 'none'} to {latest_warning}.")

    return {"status": "success", "material_change": bool(changes), "changes": changes}
