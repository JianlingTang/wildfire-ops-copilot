# Wildfire Ops Backend Deployment

## Local ADK runtime

Set the backend to the real ADK runtime:

```bash
export AGENT_RUNTIME=adk
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=<your-project-id>
export GOOGLE_CLOUD_LOCATION=global
export ADK_GEMINI_MODEL=gemini-2.5-flash-lite
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

If Vertex credentials are not available, `/api/chat` will return a structured ADK runtime error instead of crashing the service.

## FastAPI backend to Cloud Run

Prerequisites on your machine:

```bash
gcloud auth login
gcloud auth application-default login
```

Build and deploy the backend service:

```bash
PROJECT_ID=<your-project-id> \
REGION=australia-southeast1 \
SERVICE_NAME=wildfire-ops-backend \
bash scripts/deploy_backend_cloud_run.sh
```

The script is idempotent. It enables required APIs, creates the Artifact Registry repository,
creates the backend service account, binds runtime IAM, builds the image with Cloud Build, and
deploys the FastAPI backend publicly with:

- `AGENT_RUNTIME=adk`
- `GOOGLE_GENAI_USE_VERTEXAI=True`
- `GOOGLE_CLOUD_LOCATION=global`
- `ADK_GEMINI_MODEL=gemini-2.5-flash-lite`
- `ELASTIC_EVIDENCE_PROVIDER=real`
- `ELASTIC_MCP_TOOL_NAME=search_wildfire_ops_knowledge`
- `max-instances=1`
- `memory=1Gi`
- `concurrency=4`

The ADK runtime can exceed 512 MiB during Gemini tool orchestration, so keep the
backend at 1 GiB or higher for Cloud Run demos.

## Elastic MCP demo evidence

Seed the demo knowledge index after setting Elastic Cloud credentials:

```bash
export ELASTICSEARCH_URL="https://<your-elasticsearch-endpoint>"
export ELASTIC_API_KEY="<seed-api-key-with-index-write-access>"
.venv/bin/python scripts/seed_elastic_wildfire_docs.py
```

Create or configure an Elastic Agent Builder MCP-visible index search tool over:

- Index: `wildfire_ops_knowledge`
- Tool name: `search_wildfire_ops_knowledge`
- Purpose: retrieve wildfire policies, SOPs, advisory templates, historical incidents,
  warning guidance, and data reliability notes.

Store runtime secrets in GCP Secret Manager before deploying Cloud Run:

```bash
printf "%s" "https://<your-kibana-url>" | gcloud secrets create elastic-kibana-url \
  --project <your-project-id> \
  --data-file=-

printf "%s" "<runtime-api-key-with-agent-builder-read-access>" | gcloud secrets create elastic-api-key \
  --project <your-project-id> \
  --data-file=-
```

If the secrets already exist, add a new version instead of creating them:

```bash
printf "%s" "https://<your-kibana-url>" | gcloud secrets versions add elastic-kibana-url \
  --project <your-project-id> \
  --data-file=-

printf "%s" "<runtime-api-key-with-agent-builder-read-access>" | gcloud secrets versions add elastic-api-key \
  --project <your-project-id> \
  --data-file=-
```

The backend falls back to deterministic evidence with `mode=fallback` if Elastic MCP
credentials are missing or the MCP call fails.

Smoke test the deployed backend:

```bash
BACKEND_URL="$(gcloud run services describe wildfire-ops-backend \
  --project <your-project-id> \
  --region australia-southeast1 \
  --format='value(status.url)')"

curl "$BACKEND_URL/health"
curl -X POST "$BACKEND_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"Analyze this region and generate today'\''s report.","region_id":"state_wa","region_name":"Western Australia hotspot cluster focus","aoi":{"center":[-16.12,126.35],"radius_km":50}}'
```

To test the local dashboard against Cloud Run:

```bash
NEXT_PUBLIC_API_BASE_URL="$BACKEND_URL" npm run dev -- --hostname 127.0.0.1 --port 3001
```

## Optional pure ADK smoke deploy

If you want to validate the ADK agent package directly with the official ADK Cloud Run path:

```bash
PROJECT_ID=<your-project-id> \
REGION=australia-southeast1 \
bash scripts/deploy_adk_agent_cloud_run.sh
```

This deploys the `wildfire_ops_agent/` package directly with `adk deploy cloud_run`.

## Terraform

Initialize and plan:

```bash
cd infra/terraform
terraform init
terraform plan \
  -var="project_id=<your-project-id>" \
  -var="image_uri=australia-southeast1-docker.pkg.dev/<your-project-id>/wildfire-ops/wildfire-ops-backend:latest"
```

Apply:

```bash
terraform apply \
  -var="project_id=<your-project-id>" \
  -var="image_uri=australia-southeast1-docker.pkg.dev/<your-project-id>/wildfire-ops/wildfire-ops-backend:latest"
```

The repo also includes a dedicated ADK agent package at `wildfire_ops_agent/` for direct ADK-oriented deployment or experimentation.
