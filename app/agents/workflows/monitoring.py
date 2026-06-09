from app.services.change_detection import detect_material_change


def evaluate_monitoring_change(previous_snapshot: dict | None, latest_snapshot: dict) -> dict:
    return detect_material_change(previous_snapshot, latest_snapshot)
