# Evidence bundles for every run: source snapshots, unified diffs, build and
# test logs, generated image proof (roadmap.md §10.3).
#
# Versioning is on and object ACLs are off. A pull request cites this bucket as
# proof of what the sandbox actually did, so an object must not be silently
# replaced after a reviewer has read it, and access must be auditable through
# IAM alone.

resource "google_storage_bucket" "evidence" {
  project  = var.project_id
  name     = var.bucket_name
  location = var.location

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy
  labels                      = var.labels

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age                = var.noncurrent_retention_days
      with_state         = "ARCHIVED"
      num_newer_versions = 3
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age        = var.nearline_after_days
      with_state = "LIVE"
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
}

resource "google_storage_bucket_iam_member" "writers" {
  for_each = toset(var.writer_members)

  bucket = google_storage_bucket.evidence.name
  role   = "roles/storage.objectUser"
  member = each.value
}

resource "google_storage_bucket_iam_member" "readers" {
  for_each = toset(var.reader_members)

  bucket = google_storage_bucket.evidence.name
  role   = "roles/storage.objectViewer"
  member = each.value
}
