from app.services.risk_scoring import compute_wildfire_risk_score


def fixed_evidence() -> dict:
    return {
        "weather": {
            "data": {
                "humidity_min": 24,
                "wind_gust_max": 45,
                "rainfall_7d": 5,
            }
        },
        "hotspots": {"data": {"count_24h": 3}},
        "official_warnings": {"data": {"warning_level": "ADVICE"}},
        "spatial": {"data": {"critical_asset_count": 4}},
    }


def test_computes_expected_score_from_fixed_evidence() -> None:
    result = compute_wildfire_risk_score(fixed_evidence())

    assert result["risk_score"] == 83
    assert result["risk_level"] == "HIGH"


def test_returns_risk_drivers() -> None:
    result = compute_wildfire_risk_score(fixed_evidence())

    factors = {driver["factor"] for driver in result["drivers"]}
    assert {"wind_gust", "low_humidity", "recent_hotspots"}.issubset(factors)


def test_handles_missing_evidence_gracefully() -> None:
    result = compute_wildfire_risk_score({})

    assert result["status"] == "success"
    assert result["risk_score"] == 10
    assert result["risk_level"] == "LOW"
    assert result["drivers"] == []
