output "project_id" {
  description = "Target project."
  value       = var.project_id
}

output "region" {
  description = "Compute region."
  value       = var.region
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

output "image_prefix" {
  description = "Artifact Registry path prefix for PatchAPI images."
  value       = module.artifact_registry.image_prefix
}

output "evidence_bucket_uri" {
  description = "Evidence and artifact bucket."
  value       = module.evidence_storage.bucket_uri
}

output "event_topics" {
  description = "Pub/Sub topics keyed by their roadmap §10.4 name."
  value       = module.eventing.topic_names
}

output "event_subscriptions" {
  description = "Pull subscriptions keyed by their roadmap §10.4 topic name."
  value       = module.eventing.subscription_names
}

output "secret_ids" {
  description = "Secret Manager containers. Values are added out of band; see populate_secrets_commands."
  value       = module.secrets.secret_ids
}

output "populate_secrets_commands" {
  description = "One-time commands an operator runs to add a version to each empty secret."
  value       = module.secrets.pending_versions_command
}

output "gke_cluster_name" {
  description = "Sandbox cluster name, or null when enable_gke_sandbox is false."
  value       = one(module.gke_sandbox[*].cluster_name)
}

output "gke_get_credentials_command" {
  description = "kubeconfig command for sandbox/gke/ manifests, or null when the cluster is off."
  value       = one(module.gke_sandbox[*].get_credentials_command)
}

output "cloud_sql_connection_name" {
  description = "project:region:instance for the Cloud SQL connector, or null when off."
  value       = one(module.cloud_sql[*].connection_name)
}

output "cloud_run_uris" {
  description = "Deployed Cloud Run service URIs, empty when enable_cloud_run is false."
  value       = { for k, m in module.cloud_run : k => m.uri }
}
