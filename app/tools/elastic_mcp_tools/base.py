"""The Elastic evidence provider interface, kept in its own module so both
mcp_client.py (RealElasticMcpProvider) and provider.py (ErrorElasticEvidenceProvider,
get_elastic_evidence_provider) can depend on it without a cycle."""

from __future__ import annotations

from abc import ABC, abstractmethod


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
