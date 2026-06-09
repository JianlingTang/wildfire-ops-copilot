from app.services.change_detection import detect_material_change


def test_detects_new_hotspots() -> None:
    result = detect_material_change({"hotspot_count": 1, "risk_score": 50}, {"hotspot_count": 3, "risk_score": 50})

    assert result["material_change"] is True
    assert "Hotspot count increased from 1 to 3." in result["changes"]


def test_detects_risk_score_delta() -> None:
    result = detect_material_change({"risk_score": 50, "hotspot_count": 1}, {"risk_score": 65, "hotspot_count": 1})

    assert result["material_change"] is True
    assert "Risk score increased by 15 points." in result["changes"]


def test_detects_official_warning_changes() -> None:
    result = detect_material_change(
        {"risk_score": 50, "hotspot_count": 1, "warning_level": "ADVICE"},
        {"risk_score": 50, "hotspot_count": 1, "warning_level": "WATCH_AND_ACT"},
    )

    assert result["material_change"] is True
    assert "Official warning changed from ADVICE to WATCH_AND_ACT." in result["changes"]


def test_returns_no_alert_when_changes_below_threshold() -> None:
    result = detect_material_change({"risk_score": 50, "hotspot_count": 1}, {"risk_score": 55, "hotspot_count": 1})

    assert result["material_change"] is False
    assert result["changes"] == []
