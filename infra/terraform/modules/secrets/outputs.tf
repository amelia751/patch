output "secret_ids" {
  description = "Map of short name => Secret Manager secret_id."
  value       = { for k, s in google_secret_manager_secret.this : k => s.secret_id }
}

output "pending_versions_command" {
  description = "Commands an operator runs once to populate each empty secret container."
  value = [
    for k, s in google_secret_manager_secret.this :
    "gcloud secrets versions add ${s.secret_id} --project ${var.project_id} --data-file=.secrets/${k}"
  ]
}
