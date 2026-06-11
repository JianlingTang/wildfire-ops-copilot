import json
from pathlib import Path

from app.tools.elastic_mcp_tools import RealElasticMcpProvider, query_elastic_evidence


def test_returns_stable_schema() -> None:
    result = query_elastic_evidence("similar cases", region_name="Blue Mountains", time_window="30d")

    assert result["status"] == "error"
    assert result["mode"] == "error"
    assert result["query"] == "similar cases"
    assert isinstance(result["filters"], dict)
    assert isinstance(result["evidence"], list)
    assert result["evidence"] == []


def test_returns_error_without_credentials() -> None:
    result = query_elastic_evidence("guidance", evidence_type="official_guidance")

    assert result["status"] == "error"
    assert result["evidence"] == []


def test_real_provider_errors_when_credentials_are_missing(monkeypatch) -> None:
    monkeypatch.setenv("ELASTIC_EVIDENCE_PROVIDER", "real")
    monkeypatch.delenv("KIBANA_URL", raising=False)
    monkeypatch.delenv("ELASTIC_MCP_URL", raising=False)
    monkeypatch.delenv("ELASTIC_API_KEY", raising=False)

    result = query_elastic_evidence("public advisory approval", evidence_type="policy")

    assert result["status"] == "error"
    assert result["mode"] == "error"
    assert "credentials are not configured" in result["message"]
    assert result["evidence"] == []


def test_real_provider_maps_mcp_tool_documents(monkeypatch) -> None:
    def mcp_response(*args, **kwargs):
        return {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "documents": [
                                    {
                                        "doc_id": "policy_public_advisory_001",
                                        "title": "Public Advisory Approval Policy",
                                        "doc_type": "policy",
                                        "summary": "Drafts require human approval before release.",
                                        "effective_date": "2026-01-01",
                                        "tags": ["approval", "public_advisory"],
                                    }
                                ]
                            }
                        ),
                    }
                ]
            }
        }

    monkeypatch.setattr(RealElasticMcpProvider, "_call_mcp_tool", mcp_response)
    provider = RealElasticMcpProvider(
        mcp_url="https://example.elastic.dev/api/agent_builder/mcp",
        api_key="test-api-key",
    )

    result = provider.query("public advisory approval", region_name="Northern Territory", evidence_type="policy")

    assert result["status"] == "success"
    assert result["mode"] == "live"
    assert result["source"] == "Elastic Agent Builder MCP"
    assert result["evidence"][0]["evidence_id"] == "policy_public_advisory_001"
    assert result["evidence"][0]["title"] == "Public Advisory Approval Policy"
    assert result["evidence"][0]["type"] == "policy"
    assert result["evidence"][0]["mode"] == "live"


def test_real_provider_maps_platform_core_search_resources(monkeypatch) -> None:
    def mcp_response(*args, **kwargs):
        return {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "results": [
                                    {
                                        "type": "resource_list",
                                        "data": {
                                            "resources": [
                                                {
                                                    "reference": {
                                                        "id": "playbook_wildfire_operations_risk_001",
                                                        "index": "wildfire_ops_knowledge",
                                                    },
                                                    "content": {
                                                        "snippets": [
                                                            "High risk workflows prioritize dense hotspot clusters.",
                                                            "Prepare a public advisory draft if needed.",
                                                        ]
                                                    },
                                                }
                                            ]
                                        },
                                    }
                                ]
                            }
                        ),
                    }
                ]
            }
        }

    monkeypatch.setattr(RealElasticMcpProvider, "_call_mcp_tool", mcp_response)
    provider = RealElasticMcpProvider(
        mcp_url="https://example.elastic.dev/api/agent_builder/mcp",
        api_key="test-api-key",
    )

    result = provider.query("wildfire operational evidence", region_name="Queensland", time_window="30d")

    assert result["status"] == "success"
    assert result["tool_name"] == "platform_core_search"
    assert result["evidence"][0]["evidence_id"] == "playbook_wildfire_operations_risk_001"
    assert "dense hotspot clusters" in result["evidence"][0]["summary"]


def test_real_provider_errors_on_mcp_failure(monkeypatch) -> None:
    def failed_response(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(RealElasticMcpProvider, "_call_mcp_tool", failed_response)
    provider = RealElasticMcpProvider(
        mcp_url="https://example.elastic.dev/api/agent_builder/mcp",
        api_key="test-api-key",
    )

    result = provider.query("inspection prioritization", evidence_type="sop")

    assert result["status"] == "error"
    assert result["mode"] == "error"
    assert "boom" in result["message"]
    assert result["evidence"] == []


def test_real_provider_does_not_treat_mcp_tool_error_as_live_evidence(monkeypatch) -> None:
    def mcp_response(*args, **kwargs):
        return {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "MCP error -32602: Tool search_wildfire_ops_knowledge not found",
                    }
                ]
            }
        }

    monkeypatch.setattr(RealElasticMcpProvider, "_call_mcp_tool", mcp_response)
    provider = RealElasticMcpProvider(
        mcp_url="https://example.elastic.dev/api/agent_builder/mcp",
        api_key="test-api-key",
    )

    result = provider.query("public advisory approval", evidence_type="policy")

    assert result["status"] == "error"
    assert result["mode"] == "error"
    assert result["evidence"] == []
    assert "Tool search_wildfire_ops_knowledge not found" in result["message"]


def test_seed_docs_are_valid_for_demo_ingest() -> None:
    docs_path = Path(__file__).resolve().parents[2] / "app" / "data" / "elastic_seed_docs.json"
    docs = json.loads(docs_path.read_text(encoding="utf-8"))
    required = {
        "doc_id",
        "title",
        "doc_type",
        "jurisdiction",
        "state",
        "severity_applicability",
        "summary",
        "content",
        "tags",
        "effective_date",
        "mode",
    }
    doc_ids = [doc["doc_id"] for doc in docs]

    assert len(docs) >= 8
    assert len(doc_ids) == len(set(doc_ids))
    for doc in docs:
        assert required.issubset(doc)
        assert doc["mode"] == "demo"
        assert doc["tags"]
        assert doc.get("source_title")
        assert doc.get("source_url")
    all_tags = {tag for doc in docs for tag in doc["tags"]}
    assert {"approval", "public_advisory", "elastic_mcp", "inspection", "official_warning"}.issubset(all_tags)
