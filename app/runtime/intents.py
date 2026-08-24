def classify_intent(message: str) -> str:
    lowered = message.lower()

    if _is_memory_lookup(lowered):
        return "MEMORY_LOOKUP"
    if _is_calculation_request(lowered):
        return "CALCULATION"
    if _is_risk_methodology_request(lowered):
        return "RISK_EXPLANATION"
    if _is_knowledge_required(lowered):
        return "KNOWLEDGE_REQUIRED"
    if _is_visualization_request(lowered):
        return "HOTSPOT_VISUALIZATION"
    if _is_monitor_task(lowered):
        return "MONITOR_TASK"
    if _is_analyze_and_report(lowered):
        return "ANALYZE_AND_REPORT"
    if _is_prediction_request(lowered):
        return "RISK_PREDICTION"
    if _is_risk_trend_request(lowered):
        return "RISK_TREND"
    if "what if" in lowered:
        return "WHAT_IF"
    if any(term in lowered for term in ["draft", "email", "advisory", "brief", "call script", "task"]):
        return "ACTION_COMMAND"
    if "report" in lowered:
        return "REPORT_REQUEST"
    if _is_wind_change_request(lowered):
        return "WIND_CHANGE"
    if _is_weather_change_request(lowered):
        return "WEATHER_CHANGE"
    if "changed" in lowered or "since yesterday" in lowered:
        return "CHANGE_EXPLANATION"
    if _is_exposure_lookup(lowered):
        return "EXPOSURE_LOOKUP"
    if "why" in lowered or "evidence" in lowered:
        return "RISK_EXPLANATION"
    if "inspect" in lowered or "first" in lowered or "priority" in lowered:
        return "OPERATIONAL_PRIORITIZATION"
    return "QUESTION"


def _is_memory_lookup(lowered: str) -> bool:
    question_phrases = ["my last question", "my previous question", "what did i ask", "what was i asking"]
    aoi_phrases = ["my selected aoi", "my current aoi", "selected area", "current area", "active aoi"]
    report_aoi = (
        "report" in lowered
        and any(term in lowered for term in ["aoi", "area", "region"])
        and any(term in lowered for term in ["my", "last", "previous", "what", "which"])
    )
    action_status = any(term in lowered for term in ["action", "advisory", "draft"]) and any(
        term in lowered for term in ["status", "state", "approved", "pending"]
    )
    return any(phrase in lowered for phrase in [*question_phrases, *aoi_phrases]) or report_aoi or action_status


def _is_calculation_request(lowered: str) -> bool:
    if not any(term in lowered for term in ["calculate", "compute", "what is"]):
        return False
    if "percent change" in lowered and any(term in lowered for term in ["risk", "wildfire", "fire"]):
        return True
    return any(term in lowered for term in ["aoi", "wildfire", "fire"]) and any(
        term in lowered for term in ["area", "square kilometre", "square kilometer", "km2"]
    )


def _is_risk_methodology_request(lowered: str) -> bool:
    methodology_terms = ["calculate", "calculated", "calculation", "formula", "equation", "basis", "methodology"]
    risk_terms = ["risk", "risk level", "risk score"]
    return any(term in lowered for term in methodology_terms) and any(term in lowered for term in risk_terms)


def _is_knowledge_required(lowered: str) -> bool:
    knowledge_terms = ["policy", "procedure", "sop", "guidance", "require", "mandatory", "approval form"]
    domain_terms = ["wildfire", "bushfire", "fire", "evacuation", "prescribed-burn", "prescribed burn"]
    return any(term in lowered for term in knowledge_terms) and any(term in lowered for term in domain_terms)


def _is_visualization_request(lowered: str) -> bool:
    terms = [
        "heatmap",
        "heat map",
        "contour",
        "visualization",
        "visualisation",
        "visualize",
        "visualise",
        "hotspot map",
        "density map",
    ]
    return any(term in lowered for term in terms)


def _is_monitor_task(lowered: str) -> bool:
    if "monitor task" in lowered or "monitoring task" in lowered:
        return True
    if "monitor" in lowered and any(term in lowered for term in ["every", "10 minute", "10-minute", "risk score"]):
        return True
    return "create" in lowered and "monitor" in lowered and "task" in lowered


def _is_risk_trend_request(lowered: str) -> bool:
    return "trend" in lowered and any(term in lowered for term in ["risk", "score", "pressure", "wildfire"])


def _is_prediction_request(lowered: str) -> bool:
    if "what if" in lowered:
        return False
    terms = [
        "predict",
        "prediction",
        "forecast",
        "next few days",
        "tomorrow",
        "future risk",
        "will risk",
        "预计",
        "预测",
        "未来",
    ]
    return any(term in lowered for term in terms)


def _is_wind_change_request(lowered: str) -> bool:
    return "wind" in lowered and any(term in lowered for term in ["changed", "change", "since yesterday", "yesterday"])


def _is_weather_change_request(lowered: str) -> bool:
    return "weather" in lowered and any(
        term in lowered for term in ["changed", "change", "since yesterday", "yesterday"]
    )


def _is_exposure_lookup(lowered: str) -> bool:
    exposure_terms = [
        "exposed",
        "exposure",
        "asset",
        "assets",
        "critical asset",
        "critical assets",
        "road",
        "roads",
        "town",
        "towns",
        "settlement",
        "settlements",
        "protected area",
        "protected areas",
        "park",
        "parks",
    ]
    lookup_terms = ["what", "which", "list", "show", "within", "inside", "near", "nearby", "aoi"]
    return any(term in lowered for term in exposure_terms) and any(term in lowered for term in lookup_terms)


def _is_analyze_and_report(lowered: str) -> bool:
    if "report" in lowered and any(term in lowered for term in ["analy", "run analysis"]):
        return True

    phrases = [
        "analyze this wildfire aoi",
        "analyse this wildfire aoi",
        "analyze this aoi",
        "analyse this aoi",
        "analyze this region",
        "analyse this region",
        "analyze blue mountains",
        "analyse blue mountains",
        "run analysis",
        "analyze and generate report",
        "analyse and generate report",
        "generate today's report",
        "generate todays report",
        "generate a report",
        "generate report",
    ]
    return any(phrase in lowered for phrase in phrases)
