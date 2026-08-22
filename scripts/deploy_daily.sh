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
ELASTIC_KIBANA_URL_SECRET="${ELASTIC_KIBANA_URL_SECRET:-elastic-kibana-url}"
ELASTIC_API_KEY_SECRET="${ELASTIC_API_KEY_SECRET:-elastic-api-key}"
ELASTIC_MCP_URL_SECRET="${ELASTIC_MCP_URL_SECRET:-}"
FIREBASE_PROJECT_ID="${FIREBASE_PROJECT_ID:-${PROJECT_ID}}"

cd "${ROOT_DIR}"

gcloud builds submit \
  --project "${PROJECT_ID}" \
  --config cloudbuild.yaml \
  --substitutions "_IMAGE_URI=${IMAGE_URI}"

SECRET_ARGS=()
if gcloud secrets describe "${ELASTIC_KIBANA_URL_SECRET}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  SECRET_ARGS+=(--set-secrets "KIBANA_URL=${ELASTIC_KIBANA_URL_SECRET}:latest")
elif [ "${ELASTIC_EVIDENCE_PROVIDER}" = "real" ]; then
  echo "Error: Secret ${ELASTIC_KIBANA_URL_SECRET} is required when ELASTIC_EVIDENCE_PROVIDER=real." >&2
  exit 1
fi
if gcloud secrets describe "${ELASTIC_API_KEY_SECRET}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  SECRET_ARGS+=(--set-secrets "ELASTIC_API_KEY=${ELASTIC_API_KEY_SECRET}:latest")
elif [ "${ELASTIC_EVIDENCE_PROVIDER}" = "real" ]; then
  echo "Error: Secret ${ELASTIC_API_KEY_SECRET} is required when ELASTIC_EVIDENCE_PROVIDER=real." >&2
  exit 1
fi
if [ -n "${ELASTIC_MCP_URL_SECRET}" ] && gcloud secrets describe "${ELASTIC_MCP_URL_SECRET}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  SECRET_ARGS+=(--set-secrets "ELASTIC_MCP_URL=${ELASTIC_MCP_URL_SECRET}:latest")
fi
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
  --set-env-vars "^@^AGENT_RUNTIME=adk@GOOGLE_GENAI_USE_VERTEXAI=True@GOOGLE_CLOUD_PROJECT=${PROJECT_ID}@GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION}@ADK_GEMINI_MODEL=${ADK_GEMINI_MODEL}@ELASTIC_EVIDENCE_PROVIDER=${ELASTIC_EVIDENCE_PROVIDER}@ELASTIC_MCP_TOOL_NAME=${ELASTIC_MCP_TOOL_NAME}@CORS_ORIGINS=${CORS_ORIGINS}@FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID}" \
  "${SECRET_ARGS[@]}"

cd "${ROOT_DIR}/frontend"
: "${NEXT_PUBLIC_API_BASE_URL:?NEXT_PUBLIC_API_BASE_URL is required for production frontend builds}"
: "${NEXT_PUBLIC_FIREBASE_API_KEY:?NEXT_PUBLIC_FIREBASE_API_KEY is required for production frontend builds}"
: "${NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN:?NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN is required for production frontend builds}"
: "${NEXT_PUBLIC_FIREBASE_PROJECT_ID:?NEXT_PUBLIC_FIREBASE_PROJECT_ID is required for production frontend builds}"
: "${NEXT_PUBLIC_FIREBASE_APP_ID:?NEXT_PUBLIC_FIREBASE_APP_ID is required for production frontend builds}"
npm run build

cd "${ROOT_DIR}"
npx firebase-tools deploy --only hosting --project "${PROJECT_ID}"
