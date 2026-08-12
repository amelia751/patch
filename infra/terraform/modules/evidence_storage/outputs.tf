output "bucket_name" {
  description = "Evidence bucket name."
  value       = google_storage_bucket.evidence.name
}

output "bucket_uri" {
  description = "gs:// URI of the evidence bucket."
  value       = "gs://${google_storage_bucket.evidence.name}"
}
