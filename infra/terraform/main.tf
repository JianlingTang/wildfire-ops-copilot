locals {
  required_services = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
  ])
}

resource "google_project_service" "required" {
  for_each           = local.required_services
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "backend" {
  location      = var.region
  repository_id = var.artifact_repository_id
  description   = "Wildfire Ops backend images"
  format        = "DOCKER"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "backend" {
  account_id   = "${var.service_name}-sa"
  display_name = "Wildfire Ops backend runtime"
}

resource "google_project_iam_member" "backend_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_secret_manager_secret" "elastic_kibana_url" {
  count     = var.create_elastic_secret_placeholders ? 1 : 0
  secret_id = "elastic-kibana-url"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "elastic_api_key" {
  count     = var.create_elastic_secret_placeholders ? 1 : 0
  secret_id = "elastic-api-key"

  replication {
    auto {}
  }
}

resource "google_cloud_run_v2_service" "backend" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.backend.email
    timeout         = "300s"

    scaling {
      max_instance_count = 1
    }

    containers {
      image = var.image_uri

      env {
        name  = "AGENT_RUNTIME"
        value = "adk"
      }

      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "True"
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }

      env {
        name  = "ADK_GEMINI_MODEL"
        value = var.adk_gemini_model
      }

      env {
        name  = "ELASTIC_EVIDENCE_PROVIDER"
        value = var.elastic_evidence_provider
      }

      env {
        name  = "ELASTIC_MCP_TOOL_NAME"
        value = var.elastic_mcp_tool_name
      }

      env {
        name = "KIBANA_URL"
        value_source {
          secret_key_ref {
            secret  = var.elastic_kibana_url_secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "ELASTIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = var.elastic_api_key_secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "CORS_ORIGINS"
        value = join(",", var.cors_origins)
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_project_iam_member.backend_vertex_user,
    google_project_iam_member.backend_logs,
    google_project_iam_member.backend_secret_accessor,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  name     = google_cloud_run_v2_service.backend.name
  location = google_cloud_run_v2_service.backend.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
