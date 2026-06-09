# Wildfire Ops Copilot

Wildfire Ops Copilot is an emergency-operations dashboard and AI agent for wildfire monitoring, AOI analysis, operational recommendations, report generation, and human-approved public-advisory drafting.

Hosted demo: https://wildfireops-tang-0606.web.app/

Backend health check: https://wildfire-ops-backend-439532509169.australia-southeast1.run.app/health

## What It Does

- Shows Australia-wide live hotspot activity and lets an operator focus a state AOI by radius.
- Routes chat requests through an ADK/Gemini wildfire operations coordinator.
- Calls workflow tools for analysis, what-if scenarios, operational prioritization, reports, and approval-gated action drafting.
- Retrieves operational evidence from Elastic Agent Builder MCP using a curated wildfire knowledge index.
- Combines live weather, hotspot, warning, spatial exposure, Elastic evidence, and deterministic risk scoring.
- Generates operator summaries, trace events, reports, alerts, and pending approval records.

Example prompts:

- `Analyze this region and generate today's report.`
- `Which area should we inspect first?`
- `What if wind increases by 30% and humidity decreases by 10%?`
- `Draft a public advisory for this alert.`

## Required Hackathon Tech

This project uses the required stack at runtime:

- Gemini on Google Cloud Vertex AI, configured with `GOOGLE_GENAI_USE_VERTEXAI=True`.
- Google ADK / Gemini Enterprise Agent Platform code-first runtime through `google-adk`.
- Elastic Agent Builder MCP through `{KIBANA_URL}/api/agent_builder/mcp`.
- Google Cloud Run for the FastAPI backend.
- Firebase Hosting for the frontend.

Key files:

- ADK/Gemini runtime: `app/runtime/adk.py`
- Agent coordinator and tools: `wildfire_ops_agent/agent.py`, `wildfire_ops_agent/tools.py`
- Elastic MCP provider: `app/tools/elastic_mcp_tools.py`
- Elastic seed docs: `app/data/elastic_seed_docs.json`
- Cloud Run deploy script: `scripts/deploy_backend_cloud_run.sh`
- Firebase frontend: `frontend/`

## Architecture

```text
Firebase Hosting frontend
  -> FastAPI backend on Cloud Run
    -> ADK/Gemini root coordinator
      -> analysis / what-if / action / report / analyst workflow tools
        -> live hotspot, weather, warning, exposure tools
        -> Elastic Agent Builder MCP evidence provider
        -> deterministic risk scoring, reports, alerts, approvals
```

## Local Setup

Prerequisites:

- Python 3.11+
- Node.js 20+
- Google Cloud project with Vertex AI enabled
- Elastic Cloud deployment with an Agent Builder MCP search tool

Install backend dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Create local environment files:

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

Set these values in `.env`:

```bash
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=global
ADK_GEMINI_MODEL=gemini-2.5-flash-lite
ELASTIC_EVIDENCE_PROVIDER=real
KIBANA_URL=https://your-kibana-endpoint
ELASTIC_API_KEY=your-elastic-api-key
```

Run the backend:

```bash
set -a
. .env
set +a
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Run the frontend:

```bash
cd frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3001
```

Open http://127.0.0.1:3001.

## Elastic MCP Setup

Seed the demo knowledge index:

```bash
export ELASTICSEARCH_URL="https://your-elasticsearch-endpoint"
export ELASTIC_API_KEY="your-seed-api-key"
.venv/bin/python scripts/seed_elastic_wildfire_docs.py
```

In Kibana Agent Builder, create an MCP-visible index search tool:

- Index: `wildfire_ops_knowledge`
- Tool name: `search_wildfire_ops_knowledge`
- Description: retrieves wildfire policies, SOPs, advisory templates, historical incidents, warning guidance, and data reliability notes.

The backend reads:

- `KIBANA_URL`
- `ELASTIC_API_KEY`
- `ELASTIC_MCP_TOOL_NAME=search_wildfire_ops_knowledge`

If Elastic MCP is unavailable, the provider returns a deterministic fallback payload with `mode=fallback`.

## Deploy

Deploy the backend to Cloud Run:

```bash
PROJECT_ID=your-gcp-project-id \
REGION=australia-southeast1 \
SERVICE_NAME=wildfire-ops-backend \
bash scripts/deploy_backend_cloud_run.sh
```

Deploy the frontend to Firebase Hosting:

```bash
cd frontend
npm ci
npm run build
cd ..
firebase deploy --only hosting
```

More deployment details are in `DEPLOYMENT.md`.

## Tests

Backend:

```bash
ruff check .
mypy app tests
pytest -q
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

Smoke test:

```bash
bash scripts/smoke_test.sh
```

## Demo Flow

1. Open the hosted dashboard.
2. Focus an AOI from live Australian hotspot data.
3. Ask: `Analyze this region and generate today's report.`
4. Confirm the agent trace shows data gathering, Elastic MCP evidence, risk scoring, and report generation.
5. Ask: `What if wind increases by 30% and humidity decreases by 10%?`
6. Ask: `Draft a public advisory for this alert.`
7. Confirm the draft appears as a pending approval instead of being externally executed.

## Safety Boundary

The system can generate reports, evidence briefs, what-if outputs, and draft action records. It does not directly publish public advisories, send emails, or dispatch resources. External actions are routed to human approval.

## License

MIT License. See `LICENSE`.
