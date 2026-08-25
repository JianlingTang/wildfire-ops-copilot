"""Provider selection and the public query_elastic_evidence entry point."""

from __future__ import annotations

import os

from app.tools.elastic_mcp_tools.base import ElasticEvidenceProvider
from app.tools.elastic_mcp_tools.mcp_client import RealElasticMcpProvider
from app.tools.elastic_mcp_tools.normalize import _error_payload, _filters


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
