# Container images for the Cloud Run services and the sandbox runner image.
#
# Immutable tags are on: a sandbox that verifies a patch must be reproducible
# from the digest recorded in the run's evidence, so a tag may never be moved
# after a verification result has been written.

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  format        = "DOCKER"
  description   = var.description

  docker_config {
    immutable_tags = true
  }

  cleanup_policy_dry_run = true

  cleanup_policies {
    id     = "keep-recent-versions"
    action = "KEEP"
    most_recent_versions {
      keep_count = var.keep_versions
    }
  }
}

resource "google_artifact_registry_repository_iam_member" "readers" {
  for_each = toset(var.reader_members)

  project    = google_artifact_registry_repository.images.project
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.reader"
  member     = each.value
}
