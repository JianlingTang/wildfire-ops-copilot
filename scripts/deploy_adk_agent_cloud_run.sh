#!/usr/bin/env bash

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID is required}"
REGION="${REGION:-australia-southeast1}"
SERVICE_NAME="${SERVICE_NAME:-wildfire-ops-adk-agent}"
APP_NAME="${APP_NAME:-wildfire_ops_agent}"
ADK_GEMINI_MODEL="${ADK_GEMINI_MODEL:-gemini-2.5-flash}"

export GOOGLE_CLOUD_PROJECT="${PROJECT_ID}"
export GOOGLE_CLOUD_LOCATION="${REGION}"
export GOOGLE_GENAI_USE_VERTEXAI=True
export ADK_GEMINI_MODEL

.venv/bin/adk deploy cloud_run \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --service_name "${SERVICE_NAME}" \
  --app_name "${APP_NAME}" \
  wildfire_ops_agent \
  -- \
  --allow-unauthenticated \
  --max-instances=1
