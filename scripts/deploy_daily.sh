#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROJECT_ID="${PROJECT_ID:-wildfireops-tang-0606}"
REGION="${REGION:-australia-southeast1}"
SERVICE_NAME="${SERVICE_NAME:-wildfire-ops-backend}"
REPOSITORY="${REPOSITORY:-wildfire-ops}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${SERVICE_NAME}:latest"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_EMAIL:-${SERVICE_NAME}-sa@${PROJECT_ID}.iam.gserviceaccount.com}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
ADK_GEMINI_MODEL="${ADK_GEMINI_MODEL:-gemini-2.5-flash-lite}"
CLOUD_RUN_MEMORY="${CLOUD_RUN_MEMORY:-1Gi}"
CLOUD_RUN_CONCURRENCY="${CLOUD_RUN_CONCURRENCY:-4}"
CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,https://${PROJECT_ID}.web.app,https://${PROJECT_ID}.firebaseapp.com}"
ELASTIC_EVIDENCE_PROVIDER="${ELASTIC_EVIDENCE_PROVIDER:-real}"
ELASTIC_MCP_TOOL_NAME="${ELASTIC_MCP_TOOL_NAME:-platform_core_search}"

cd "${ROOT_DIR}"

gcloud builds submit \
  --project "${PROJECT_ID}" \
  --config cloudbuild.yaml \
  --substitutions "_IMAGE_URI=${IMAGE_URI}"

gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_URI}" \
  --service-account "${SERVICE_ACCOUNT_EMAIL}" \
  --allow-unauthenticated \
  --ingress all \
  --max-instances 1 \
  --memory "${CLOUD_RUN_MEMORY}" \
  --concurrency "${CLOUD_RUN_CONCURRENCY}" \
  --set-env-vars "^@^AGENT_RUNTIME=adk@GOOGLE_GENAI_USE_VERTEXAI=True@GOOGLE_CLOUD_PROJECT=${PROJECT_ID}@GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION}@ADK_GEMINI_MODEL=${ADK_GEMINI_MODEL}@ELASTIC_EVIDENCE_PROVIDER=${ELASTIC_EVIDENCE_PROVIDER}@ELASTIC_MCP_TOOL_NAME=${ELASTIC_MCP_TOOL_NAME}@CORS_ORIGINS=${CORS_ORIGINS}"

cd "${ROOT_DIR}/frontend"
npm run build

cd "${ROOT_DIR}"
npx firebase-tools deploy --only hosting --project "${PROJECT_ID}"
