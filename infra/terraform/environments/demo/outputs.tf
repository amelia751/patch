output "project_id" {
  description = "Target project."
  value       = var.project_id
}

output "vertex_location" {
  description = "Vertex AI location the agents call for Gemini models."
  value       = var.vertex_location
}

output "enabled_services" {
  description = "Service APIs this environment manages."
  value       = module.project_services.enabled_services
}

output "service_account_emails" {
  description = "Workload identity per service."
  value       = module.service_accounts.emails
}

output "evidence_bucket_uri" {
  description = "Evidence and artifact bucket for recorded runs."
  value       = module.evidence_storage.bucket_uri
}

output "event_topics" {
  description = "Pub/Sub topics keyed by their roadmap §10.4 name."
  value       = module.eventing.topic_names
}
