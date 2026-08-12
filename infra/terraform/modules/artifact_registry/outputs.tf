output "repository_id" {
  description = "Short repository id."
  value       = google_artifact_registry_repository.images.repository_id
}

output "docker_host" {
  description = "Registry host to tag images against."
  value       = "${var.region}-docker.pkg.dev"
}

output "image_prefix" {
  description = "Fully qualified image path prefix; append <name>:<tag>."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}
