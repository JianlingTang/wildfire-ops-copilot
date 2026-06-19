from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

DEFAULT_ELASTIC_MCP_TOOL_NAME = "platform_core_search"


class ElasticEvidenceProvider(ABC):
    @abstractmethod
    def query(
        self,
        query: str,
        region_name: str | None = None,
        time_window: str | None = None,
        evidence_type: str | None = None,
    ) -> dict:
        raise NotImplementedError


class MockElasticEvidenceProvider(ElasticEvidenceProvider):
    def query(
        self,
        query: str,
        region_name: str | None = None,
        time_window: str | None = None,
        evidence_type: str | None = None,
    ) -> dict:
        return {
            "status": "success",
            "mode": "demo",
            "query": query,
            "filters": {
                "region_name": region_name,
                "time_window": time_window,
                "evidence_type": evidence_type,
            },
            "evidence": [
                {
                    "evidence_id": "elastic_demo_001",
                    "source": "Elastic MCP demo fallback",
                    "type": evidence_type or "historical_incident",
                    "title": "Similar elevated wind and low humidity pattern",
                    "summary": "Prior local incidents escalated when gusts exceeded 55 km/h with humidity below 20%.",
                    "timestamp": "demo",
                    "region_name": region_name,
                    "mode": "demo",
                }
            ],
        }


class ErrorElasticEvidenceProvider(ElasticEvidenceProvider):
    def __init__(self, message: str) -> None:
        self.message = message

    def query(
        self,
        query: str,
        region_name: str | None = None,
        time_window: str | None = None,
        evidence_type: str | None = None,
    ) -> dict:
        return _error_payload(query, _filters(region_name, time_window, evidence_type), self.message)


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

            call_response = client.post(
                self.mcp_url,
                headers=headers,
                json=_mcp_request(
                    2,
                    "tools/call",
                    {
                        "name": self.tool_name,
                        "arguments": arguments,
                    },
                ),
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

    arguments = {
        os.getenv("ELASTIC_MCP_QUERY_ARGUMENT", "query"): query,
        "region_name": region_name,
        "time_window": time_window,
        "evidence_type": evidence_type,
    }
    return {key: value for key, value in arguments.items() if value is not None}


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


def _filters(region_name: str | None, time_window: str | None, evidence_type: str | None) -> dict:
    return {
        "region_name": region_name,
        "time_window": time_window,
        "evidence_type": evidence_type,
    }


def _mcp_request(request_id: int, method: str, params: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def _mcp_notification(method: str) -> dict:
    return {"jsonrpc": "2.0", "method": method}


def _decode_mcp_http_response(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("event:") or "\ndata:" in stripped:
        data_lines = [
            line.removeprefix("data:").strip()
            for line in stripped.splitlines()
            if line.startswith("data:")
        ]
        stripped = "\n".join(data_lines).strip()
    return json.loads(stripped)


def _normalize_mcp_evidence(payload: Any, region_name: str | None, evidence_type: str | None) -> list[dict]:
    docs = _extract_candidate_documents(payload)
    evidence: list[dict] = []
    for index, doc in enumerate(docs[:5], start=1):
        if isinstance(doc, str):
            if _is_mcp_error_text(doc):
                raise RuntimeError(doc)
            evidence.append(_evidence_from_text(index, doc, region_name, evidence_type))
            continue
        if not isinstance(doc, dict):
            continue
        raw_source = doc.get("_source") if isinstance(doc.get("_source"), dict) else doc
        if not isinstance(raw_source, dict):
            continue
        source: dict[str, Any] = raw_source
        raw_reference = source.get("reference")
        reference: dict[str, Any] = raw_reference if isinstance(raw_reference, dict) else {}
        raw_content = source.get("content")
        content: dict[str, Any] = raw_content if isinstance(raw_content, dict) else {}
        raw_snippets = content.get("snippets")
        snippets: list[Any] = raw_snippets if isinstance(raw_snippets, list) else []
        evidence.append(
            {
                "evidence_id": str(
                    source.get("evidence_id")
                    or source.get("doc_id")
                    or source.get("_id")
                    or source.get("id")
                    or reference.get("id")
                    or f"elastic_mcp_{index:03d}"
                ),
                "source": "Elastic Agent Builder MCP",
                "type": str(source.get("type") or source.get("doc_type") or evidence_type or "operational_evidence"),
                "title": str(
                    source.get("title") or source.get("name") or reference.get("id") or "Elastic MCP evidence"
                ),
                "summary": str(
                    source.get("summary")
                    or source.get("text")
                    or "\n".join(str(snippet) for snippet in snippets)
                    or ""
                ),
                "timestamp": str(
                    source.get("timestamp") or source.get("effective_date") or source.get("date") or "live"
                ),
                "region_name": str(source.get("region_name") or source.get("region") or region_name or ""),
                "mode": "live",
                "tags": source.get("tags", []),
            }
        )
    return evidence


def _extract_candidate_documents(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return [payload] if payload else []
    if payload.get("type") == "resource_list":
        resources = payload.get("data", {}).get("resources")
        if isinstance(resources, list):
            return resources
    if "error" in payload:
        raise RuntimeError(payload["error"])
    result = payload.get("result", payload)
    if isinstance(result, dict):
        if isinstance(result.get("structuredContent"), dict):
            nested = _extract_candidate_documents(result["structuredContent"])
            if nested:
                return nested
        if isinstance(result.get("content"), list):
            docs: list[Any] = []
            for item in result["content"]:
                docs.extend(_extract_candidate_documents(_content_item_payload(item)))
            if docs:
                return docs
        for key in ("evidence", "documents", "docs", "results", "items", "data"):
            if isinstance(result.get(key), list):
                nested_docs: list[Any] = []
                for item in result[key]:
                    nested = _extract_candidate_documents(item)
                    nested_docs.extend(nested if nested != [item] else [item])
                return nested_docs
            if isinstance(result.get(key), dict):
                nested = _extract_candidate_documents(result[key])
                if nested:
                    return nested
        hits = result.get("hits")
        if isinstance(hits, dict) and isinstance(hits.get("hits"), list):
            return hits["hits"]
    return [result]


def _content_item_payload(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    if "json" in item:
        return item["json"]
    if "data" in item:
        return item["data"]
    text = item.get("text")
    if isinstance(text, str):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return item


def _is_mcp_error_text(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized.startswith("mcp error") or "tool search_wildfire_ops_knowledge not found" in normalized


def _evidence_from_text(index: int, text: str, region_name: str | None, evidence_type: str | None) -> dict:
    return {
        "evidence_id": f"elastic_mcp_text_{index:03d}",
        "source": "Elastic Agent Builder MCP",
        "type": evidence_type or "operational_evidence",
        "title": "Elastic MCP evidence",
        "summary": text,
        "timestamp": "live",
        "region_name": region_name,
        "mode": "live",
    }


def _fallback_payload(query: str, filters: dict, message: str) -> dict:
    fallback = MockElasticEvidenceProvider().query(
        query,
        region_name=filters.get("region_name"),
        time_window=filters.get("time_window"),
        evidence_type=filters.get("evidence_type"),
    )
    fallback["mode"] = "fallback"
    fallback["source"] = "Elastic MCP fallback"
    fallback["message"] = message
    for item in fallback.get("evidence", []):
        item["mode"] = "fallback"
        item["source"] = "Elastic MCP fallback"
    return fallback


def _error_payload(query: str, filters: dict, message: str) -> dict:
    return {
        "status": "error",
        "mode": "error",
        "source": "Elastic Agent Builder MCP",
        "query": query,
        "filters": filters,
        "evidence": [],
        "message": message,
    }


def get_elastic_evidence_provider() -> ElasticEvidenceProvider:
    provider_name = os.getenv("ELASTIC_EVIDENCE_PROVIDER", "real").lower()
    if provider_name == "real":
        return RealElasticMcpProvider()
    return ErrorElasticEvidenceProvider(f"Elastic provider '{provider_name}' is disabled; live MCP is required.")


def query_elastic_evidence(
    query: str,
    region_name: str | None = None,
    time_window: str | None = None,
    evidence_type: str | None = None,
) -> dict:
    """Query Elastic MCP for wildfire operational evidence through a swappable provider boundary."""
    return get_elastic_evidence_provider().query(query, region_name, time_window, evidence_type)
