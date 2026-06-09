from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

INDEX_NAME = os.getenv("ELASTIC_INDEX_NAME", "wildfire_ops_knowledge")
ROOT = Path(__file__).resolve().parents[1]
SEED_DOCS_PATH = ROOT / "app" / "data" / "elastic_seed_docs.json"


def main() -> None:
    elasticsearch_url = os.environ["ELASTICSEARCH_URL"].rstrip("/")
    api_key = os.environ["ELASTIC_API_KEY"]
    docs = _load_seed_docs()
    headers = {
        "Authorization": f"ApiKey {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(base_url=elasticsearch_url, headers=headers, timeout=30.0) as client:
        _ensure_index(client)
        response = client.post("/_bulk", content=_bulk_payload(docs))
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(json.dumps(payload, indent=2))
    print(f"Seeded {len(docs)} docs into {INDEX_NAME}.")


def _load_seed_docs() -> list[dict[str, Any]]:
    docs = json.loads(SEED_DOCS_PATH.read_text(encoding="utf-8"))
    if not isinstance(docs, list):
        raise ValueError("Elastic seed docs must be a JSON list.")
    return docs


def _ensure_index(client: httpx.Client) -> None:
    response = client.head(f"/{INDEX_NAME}")
    if response.status_code == 200:
        return
    if response.status_code != 404:
        response.raise_for_status()
    create_response = client.put(
        f"/{INDEX_NAME}",
        json={
            "mappings": {
                "properties": {
                    "doc_id": {"type": "keyword"},
                    "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "doc_type": {"type": "keyword"},
                    "jurisdiction": {"type": "keyword"},
                    "state": {"type": "keyword"},
                    "severity_applicability": {"type": "keyword"},
                    "summary": {"type": "text"},
                    "content": {"type": "text"},
                    "tags": {"type": "keyword"},
                    "effective_date": {"type": "date"},
                    "mode": {"type": "keyword"},
                }
            }
        },
    )
    create_response.raise_for_status()


def _bulk_payload(docs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for doc in docs:
        doc_id = doc["doc_id"]
        lines.append(json.dumps({"index": {"_index": INDEX_NAME, "_id": doc_id}}))
        lines.append(json.dumps(doc))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
