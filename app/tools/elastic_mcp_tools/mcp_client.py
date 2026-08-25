"""The live Elastic Agent Builder MCP client provider."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from app.tools.elastic_mcp_tools.base import ElasticEvidenceProvider
from app.tools.elastic_mcp_tools.normalize import _error_payload, _filters, _normalize_mcp_evidence

DEFAULT_ELASTIC_MCP_TOOL_NAME = "platform_core_search"


class RealElasticMcpProvider(ElasticEvidenceProvider):
    def __init__(
        self,
        *,
        kibana_url: str | None = None,
        api_key: str | None = None,
        mcp_url: str | None = None,
        tool_name: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        configured_kibana_url = kibana_url if kibana_url is not None else os.getenv("KIBANA_URL", "")
        self.kibana_url = configured_kibana_url.rstrip("/")
        self.api_key = api_key or os.getenv("ELASTIC_API_KEY", "")
        self.mcp_url = mcp_url or os.getenv("ELASTIC_MCP_URL") or _mcp_url_from_kibana(self.kibana_url)
        self.tool_name = tool_name or os.getenv("ELASTIC_MCP_TOOL_NAME") or DEFAULT_ELASTIC_MCP_TOOL_NAME
        self.timeout_seconds = timeout_seconds or _elastic_timeout_seconds()

    def query(
        self,
        query: str,
        region_name: str | None = None,
        time_window: str | None = None,
        evidence_type: str | None = None,
    ) -> dict:
        filters = _filters(region_name, time_window, evidence_type)
        if not self.mcp_url or not self.api_key:
            return _error_payload(query, filters, "Elastic MCP credentials are not configured.")

        try:
            payload = self._call_mcp_tool(query, region_name, time_window, evidence_type)
            evidence = _normalize_mcp_evidence(payload, region_name, evidence_type)
            if not evidence:
                return _error_payload(query, filters, "Elastic MCP returned no usable evidence.")
            return {
                "status": "success",
                "mode": "live",
                "source": "Elastic Agent Builder MCP",
                "tool_name": self.tool_name,
                "query": query,
                "filters": filters,
                "evidence": evidence,
            }
        except Exception as exc:
            return _error_payload(query, filters, f"Elastic MCP request failed: {exc}.")

    def _call_mcp_tool(
        self,
        query: str,
        region_name: str | None,
        time_window: str | None,
        evidence_type: str | None,
    ) -> Any:
        headers = {
            "Authorization": f"ApiKey {self.api_key}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        arguments = _mcp_tool_arguments(self.tool_name, query, region_name, time_window, evidence_type)
        with httpx.Client(timeout=self.timeout_seconds) as client:
            self._initialize_mcp_session(client, headers)
            return self._call_tool(client, headers, arguments)

    def _initialize_mcp_session(self, client: httpx.Client, headers: dict[str, str]) -> None:
        initialize = _mcp_request(
            1,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "wildfire-ops-copilot", "version": "0.1.0"},
            },
        )
        init_response = client.post(self.mcp_url, headers=headers, json=initialize)
        init_response.raise_for_status()

        session_id = init_response.headers.get("mcp-session-id")
        if session_id:
            headers["mcp-session-id"] = session_id
        client.post(self.mcp_url, headers=headers, json=_mcp_notification("notifications/initialized"))

    def _call_tool(self, client: httpx.Client, headers: dict[str, str], arguments: dict[str, Any]) -> Any:
        call_response = client.post(
            self.mcp_url,
            headers=headers,
            json=_mcp_request(2, "tools/call", {"name": self.tool_name, "arguments": arguments}),
        )
        call_response.raise_for_status()
        return _decode_mcp_http_response(call_response.text)


def _mcp_url_from_kibana(kibana_url: str) -> str:
    if not kibana_url:
        return ""
    return f"{kibana_url}/api/agent_builder/mcp"


def _mcp_tool_arguments(
    tool_name: str,
    query: str,
    region_name: str | None,
    time_window: str | None,
    evidence_type: str | None,
) -> dict:
    if tool_name == "platform_core_search":
        return _platform_core_search_arguments(query, region_name, time_window, evidence_type)

    arguments = {
        os.getenv("ELASTIC_MCP_QUERY_ARGUMENT", "query"): query,
        "region_name": region_name,
        "time_window": time_window,
        "evidence_type": evidence_type,
    }
    return {key: value for key, value in arguments.items() if value is not None}


def _platform_core_search_arguments(
    query: str, region_name: str | None, time_window: str | None, evidence_type: str | None
) -> dict:
    context = []
    if region_name:
        context.append(f"region: {region_name}")
    if evidence_type:
        context.append(f"evidence type: {evidence_type}")
    enriched_query = f"{query} ({'; '.join(context)})" if context else query
    arguments: dict[str, Any] = {"query": enriched_query}
    time_range = _time_range_from_window(time_window)
    if time_range:
        arguments["time_range"] = time_range
    index = os.getenv("ELASTIC_MCP_INDEX", "").strip()
    if index:
        arguments["index"] = index
    return arguments


def _time_range_from_window(time_window: str | None) -> dict | None:
    if not time_window:
        return None
    window = time_window.strip()
    if not window:
        return None
    start = window if window.startswith("now-") else f"now-{window}"
    return {"from": start, "to": "now"}


def _elastic_timeout_seconds() -> float:
    raw = os.getenv("ELASTIC_MCP_TIMEOUT_SECONDS", "8").strip()
    try:
        return max(0.1, float(raw))
    except ValueError:
        return 8.0


def _mcp_request(request_id: int, method: str, params: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def _mcp_notification(method: str) -> dict:
    return {"jsonrpc": "2.0", "method": method}


def _decode_mcp_http_response(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("event:") or "\ndata:" in stripped:
        data_lines = [line.removeprefix("data:").strip() for line in stripped.splitlines() if line.startswith("data:")]
        stripped = "\n".join(data_lines).strip()
    return json.loads(stripped)
