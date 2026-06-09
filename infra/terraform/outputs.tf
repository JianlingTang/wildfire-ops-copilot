output "artifact_repository" {
  value = google_artifact_registry_repository.backend.name
}

output "backend_service_account_email" {
  value = google_service_account.backend.email
}

output "cloud_run_service_name" {
  value = google_cloud_run_v2_service.backend.name
}

output "cloud_run_url" {
  value = google_cloud_run_v2_service.backend.uri
}
