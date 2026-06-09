def classify_intent(message: str) -> str:
    lowered = message.lower()

    if _is_visualization_request(lowered):
        return "HOTSPOT_VISUALIZATION"
    if _is_monitor_task(lowered):
        return "MONITOR_TASK"
    if _is_analyze_and_report(lowered):
        return "ANALYZE_AND_REPORT"
    if "what if" in lowered:
        return "WHAT_IF"
    if any(term in lowered for term in ["draft", "email", "advisory", "brief", "call script", "task"]):
        return "ACTION_COMMAND"
    if "report" in lowered:
        return "REPORT_REQUEST"
    if "changed" in lowered or "since yesterday" in lowered:
        return "CHANGE_EXPLANATION"
    if "why" in lowered or "evidence" in lowered:
        return "RISK_EXPLANATION"
    if "inspect" in lowered or "first" in lowered or "priority" in lowered:
        return "OPERATIONAL_PRIORITIZATION"
    return "QUESTION"


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


def _is_analyze_and_report(lowered: str) -> bool:
    if "report" in lowered and any(term in lowered for term in ["analy", "run analysis"]):
        return True

    phrases = [
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
