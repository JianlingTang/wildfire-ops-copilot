# Wildfire Ops Copilot

Emergency-operations dashboard and AI agent for wildfire monitoring, AOI analysis, reports, what-if scenarios, and approval-gated advisories.

Demo: https://wildfireops-tang-0606.web.app/
Backend health: https://wildfire-ops-backend-439532509169.australia-southeast1.run.app/health

## What It Does

- Focuses live Australian hotspot AOIs
- Routes chat through an ADK/Gemini coordinator
- Combines weather, warnings, spatial exposure, and Elastic MCP evidence
- Produces reports, traces, risk scoring, and approval records

## Stack

- Frontend: Firebase Hosting
- Backend: FastAPI on Cloud Run
- Agent runtime: Google ADK + Vertex AI Gemini
- Evidence: Elastic Agent Builder MCP
- Storage: Firestore

## Local Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
cp frontend/.env.example frontend/.env.local
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
cd frontend && npm install && npm run dev -- --hostname 127.0.0.1 --port 3001
```

## Elastic MCP

Seed the demo index:

```bash
export ELASTICSEARCH_URL="https://your-elasticsearch-endpoint"
export ELASTIC_API_KEY="your-seed-api-key"
.venv/bin/python scripts/seed_elastic_wildfire_docs.py
```

Use an MCP-visible index search tool:

- Index: `wildfire_ops_knowledge`
- Tool: `search_wildfire_ops_knowledge`

## Deploy

```bash
PROJECT_ID=your-gcp-project-id REGION=australia-southeast1 SERVICE_NAME=wildfire-ops-backend bash scripts/deploy_backend_cloud_run.sh
cd frontend && npm ci && npm run build && cd ..
firebase deploy --only hosting
```

## Tests

```bash
ruff check .
mypy app tests
pytest -q
cd frontend && npm run lint && npm run build
bash scripts/smoke_test.sh
```

## Demo Flow

1. Open the dashboard
2. Focus an AOI
3. Ask for today's report
4. Review trace, risk score, and report
5. Ask a what-if scenario
6. Draft a public advisory for approval
