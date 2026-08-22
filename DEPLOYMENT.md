# Wildfire Ops Backend Deployment

## Backend

```bash
export AGENT_RUNTIME=adk
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=<your-project-id>
export GOOGLE_CLOUD_LOCATION=global
export ADK_GEMINI_MODEL=gemini-2.5-flash-lite
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

## Cloud Run

```bash
gcloud auth login
gcloud auth application-default login
PROJECT_ID=<your-project-id> REGION=australia-southeast1 SERVICE_NAME=wildfire-ops-backend bash scripts/deploy_backend_cloud_run.sh
```

The script enables APIs, builds the image, and deploys the backend with the runtime env vars already set for demos.

## Elastic MCP

Seed the demo index:

```bash
export ELASTICSEARCH_URL="https://<your-elasticsearch-endpoint>"
export ELASTIC_API_KEY="<seed-api-key>"
.venv/bin/python scripts/seed_elastic_wildfire_docs.py
```

MCP search tool:

- Index: `wildfire_ops_knowledge`
- Tool: `search_wildfire_ops_knowledge`

Store `elastic-kibana-url` and `elastic-api-key` in Secret Manager before deploy. If they already exist, add a new version.
Store `wildfire-api-auth-token` in Secret Manager to require `X-API-Key` or `Authorization: Bearer` on `/api/*` routes in production. Set the same value as `NEXT_PUBLIC_API_AUTH_TOKEN` when building the static frontend.

## Smoke Test

```bash
BACKEND_URL="$(gcloud run services describe wildfire-ops-backend --project <your-project-id> --region australia-southeast1 --format='value(status.url)')"
curl "$BACKEND_URL/health"
curl -X POST "$BACKEND_URL/api/chat" -H "Content-Type: application/json" -H "X-API-Key: $API_AUTH_TOKEN" -d '{"message":"Analyze this region and generate today's report.","region_id":"state_wa","region_name":"Western Australia hotspot cluster focus","aoi":{"center":[-16.12,126.35],"radius_km":50}}'
```

## Optional ADK Deploy

```bash
PROJECT_ID=<your-project-id> REGION=australia-southeast1 bash scripts/deploy_adk_agent_cloud_run.sh
```

## Terraform

```bash
cd infra/terraform
terraform init
terraform plan -var="project_id=<your-project-id>" -var="image_uri=australia-southeast1-docker.pkg.dev/<your-project-id>/wildfire-ops/wildfire-ops-backend:latest"
terraform apply -var="project_id=<your-project-id>" -var="image_uri=australia-southeast1-docker.pkg.dev/<your-project-id>/wildfire-ops/wildfire-ops-backend:latest"
```
