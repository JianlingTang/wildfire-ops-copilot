"""Response-shape helpers: filters/error payloads and MCP evidence normalization."""

from __future__ import annotations

import json
from typing import Any


def _filters(region_name: str | None, time_window: str | None, evidence_type: str | None) -> dict:
    return {
        "region_name": region_name,
        "time_window": time_window,
        "evidence_type": evidence_type,
    }


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


def _normalize_mcp_evidence(payload: Any, region_name: str | None, evidence_type: str | None) -> list[dict]:
    docs = _extract_candidate_documents(payload)
    evidence: list[dict] = []
    for index, doc in enumerate(docs[:5], start=1):
        if isinstance(doc, str):
            if _is_mcp_error_text(doc):
                raise RuntimeError(doc)
            evidence.append(_evidence_from_text(index, doc, region_name, evidence_type))
            continue
        item = _evidence_from_doc(index, doc, region_name, evidence_type)
        if item is not None:
            evidence.append(item)
    return evidence


def _evidence_from_doc(
    index: int, doc: Any, region_name: str | None, evidence_type: str | None
) -> dict[str, Any] | None:
    if not isinstance(doc, dict):
        return None
    raw_source = doc.get("_source") if isinstance(doc.get("_source"), dict) else doc
    if not isinstance(raw_source, dict):
        return None
    source: dict[str, Any] = raw_source
    raw_reference = source.get("reference")
    reference: dict[str, Any] = raw_reference if isinstance(raw_reference, dict) else {}
    raw_content = source.get("content")
    content: dict[str, Any] = raw_content if isinstance(raw_content, dict) else {}
    raw_snippets = content.get("snippets")
    snippets: list[Any] = raw_snippets if isinstance(raw_snippets, list) else []
    return {
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
        "title": str(source.get("title") or source.get("name") or reference.get("id") or "Elastic MCP evidence"),
        "summary": str(
            source.get("summary") or source.get("text") or "\n".join(str(snippet) for snippet in snippets) or ""
        ),
        "timestamp": str(source.get("timestamp") or source.get("effective_date") or source.get("date") or "live"),
        "region_name": str(source.get("region_name") or source.get("region") or region_name or ""),
        "mode": "live",
        "tags": source.get("tags", []),
    }


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
        return _candidate_documents_from_result(result)
    return [result]


def _candidate_documents_from_result(result: dict[str, Any]) -> list[Any]:
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
