from __future__ import annotations

import re
from typing import Any

from app.models.schemas import ChatRequest

_EXPLICIT_SCOPE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bwildfires?\b",
        r"\bbushfires?\b",
        r"\bwildland fires?\b",
        r"\bforest fires?\b",
        r"\bfire (?:danger|risk|incident|operations?|weather|spread|perimeter|front)\b",
        r"\bhotspots?\b",
        r"\bthermal anomal(?:y|ies)\b",
        r"\bsmoke plumes?\b",
        r"\bburn scars?\b",
        r"\bfuel (?:load|moisture)s?\b",
        r"\bfirebreaks?\b",
        r"\baoi\b",
        r"\broi\b",
        r"山火|野火|森林火灾|林火|草原火灾|火点|热点|热异常|烟羽|过火区|燃料负荷|火险",
    )
)

_OPERATIONAL_SCOPE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bcurrent operating picture\b",
        r"\blatest (?:analysis )?run\b",
        r"\brisk (?:score|level|trend|prediction|forecast|high|low|changed?)\b",
        r"\b(?:selected|focused) (?:area|region|state)\b",
        r"\bthis (?:area|region|state|alert|incident)\b",
        r"\binspect(?:ion)? (?:first|priority|priorities)\b",
        r"\b(?:public safety )?(?:advisory|evacuation|warning)\b",
        r"\bemergency services?\b",
        r"\bmonitor(?:ing)? task\b",
        r"\bhotspot (?:heat ?map|contours?|visuali[sz]ation)\b",
        r"\bexposed (?:assets?|roads?|towns?|settlements?)\b",
        r"\bprotected areas?\b",
        r"运行态势|最新分析|最新运行|风险(?:分数|等级|趋势|预测)|当前(?:区域|地区|警报|事件)|"
        r"优先巡查|检查优先级|疏散|公众预警|应急服务|监控任务|暴露资产|保护区",
    )
)

_CONTEXTUAL_DOMAIN_TERMS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bwind(?: speed| gusts?)?\b",
        r"\bweather\b",
        r"\bhumidity\b",
        r"\brainfall\b",
        r"\btemperature\b",
        r"\bforecast\b",
        r"\bscenario\b",
        r"\bwhat if\b",
        r"\brisk\b",
        r"\balert\b",
        r"\bassets?\b",
        r"\broads?\b",
        r"\btowns?\b",
        r"\bsettlements?\b",
        r"风速|阵风|天气|湿度|降雨|温度|预测|情景|风险|警报|资产|道路|城镇|居民点",
    )
)

_CONTEXTUAL_FOLLOW_UP_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:this|that|it|them|those|these)\b",
        r"\b(?:today|tomorrow|yesterday|next|current|latest|again)\b",
        r"那|这个|这些|它|今天|明天|昨天|当前|最新|再来",
    )
)

_MEMORY_LOOKUP_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bmy (?:last|previous) question\b",
        r"\bwhat did i ask\b",
        r"\bwhat was i asking\b",
        r"\bmy (?:selected|current|active) aoi\b",
        r"\bmy (?:selected|current) area\b",
        r"\bmy report (?:aoi|area|region)\b",
        r"\b(?:last|previous) report\b.*\b(?:aoi|area|region|analy[sz]e)\b",
        r"\bwhich region did (?:the )?(?:last|previous) report\b",
        r"\b(?:my )?(?:last )?(?:action|advisory|draft) (?:status|state)\b",
        r"\bstatus of my (?:last )?(?:action|advisory|draft)\b",
    )
)


def is_wildfire_operations_request(request: ChatRequest) -> bool:
    """Return True only when a request is recognizably inside wildfire operations scope.

    This gate is intentionally deterministic so an unrelated prompt cannot reach the
    model. It is an allow-list, not a semantic classifier: uncertain requests are
    blocked and can be rephrased with explicit wildfire/AOI context.
    """
    message = _normalized_message(request.message)
    if not message:
        return False
    if _matches_any(message, _EXPLICIT_SCOPE_PATTERNS):
        return True
    if _matches_any(message, _OPERATIONAL_SCOPE_PATTERNS):
        return True
    if (request.conversation_id or request.run_id) and _matches_any(message, _MEMORY_LOOKUP_PATTERNS):
        return True
    if _has_explicit_context(request) and _matches_any(message, _CONTEXTUAL_DOMAIN_TERMS):
        return True
    if _has_explicit_context(request) and _matches_any(message, _CONTEXTUAL_FOLLOW_UP_PATTERNS):
        return True
    return False


def out_of_scope_response(*, mode: str) -> dict[str, Any]:
    answer = (
        "This assistant only handles wildfire operations, AOI analysis, risk evidence, "
        "monitoring, reports, visualizations, and approval-gated response actions. "
        "Your request was blocked before any LLM call. Rephrase it with explicit wildfire or AOI context."
    )
    return {
        "intent": "OUT_OF_SCOPE",
        "mode": mode,
        "response": {
            "status": "blocked",
            "mode": mode,
            "answer": answer,
            "blocked_reason": "out_of_scope",
            "llm_called": False,
            "requires_rag": False,
            "tool_trace": [
                {
                    "called": "Domain Scope Gate",
                    "did": "Blocked an out-of-domain request before conversation or model processing.",
                    "output": "No LLM or workflow tool was called.",
                    "mode": mode,
                    "status": "blocked",
                }
            ],
        },
        "requires_analysis": False,
    }


def _normalized_message(message: str) -> str:
    return " ".join(message.strip().split())


def _matches_any(message: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(message) for pattern in patterns)


def _has_explicit_context(request: ChatRequest) -> bool:
    return bool(request.run_id or request.conversation_id or request.region_name or request.aoi)
