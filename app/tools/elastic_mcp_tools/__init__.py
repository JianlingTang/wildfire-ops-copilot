"""Elastic Agent Builder MCP evidence lookup: the provider boundary used by the
analysis pipeline to fetch operational evidence.

Package layout:
- base.py: the ElasticEvidenceProvider interface.
- mcp_client.py: RealElasticMcpProvider, the live MCP HTTP client.
- provider.py: provider selection (get_elastic_evidence_provider) and the
  public query_elastic_evidence entry point.
- normalize.py: response/evidence normalization shared by both providers.
"""

from __future__ import annotations

from app.tools.elastic_mcp_tools.base import ElasticEvidenceProvider
from app.tools.elastic_mcp_tools.mcp_client import DEFAULT_ELASTIC_MCP_TOOL_NAME, RealElasticMcpProvider
from app.tools.elastic_mcp_tools.provider import (
    ErrorElasticEvidenceProvider,
    get_elastic_evidence_provider,
    query_elastic_evidence,
)

__all__ = [
    "ElasticEvidenceProvider",
    "ErrorElasticEvidenceProvider",
    "RealElasticMcpProvider",
    "DEFAULT_ELASTIC_MCP_TOOL_NAME",
    "get_elastic_evidence_provider",
    "query_elastic_evidence",
]
