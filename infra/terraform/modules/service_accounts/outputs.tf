output "emails" {
  description = "Map of short name => service account email."
  value       = { for k, sa in google_service_account.workload : k => sa.email }
}

output "members" {
  description = "Map of short name => IAM member string, ready for resource-scoped bindings."
  value       = { for k, sa in google_service_account.workload : k => "serviceAccount:${sa.email}" }
}
