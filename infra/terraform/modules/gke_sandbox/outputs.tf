output "cluster_name" {
  description = "Cluster name."
  value       = google_container_cluster.sandbox.name
}

output "network_self_link" {
  description = "Self link of the sandbox VPC; Cloud SQL allocates its private IP from here."
  value       = google_compute_network.sandbox.self_link
}

output "cluster_endpoint" {
  description = "Control plane endpoint."
  value       = google_container_cluster.sandbox.endpoint
  sensitive   = true
}

output "workload_pool" {
  description = "Workload Identity pool for binding Kubernetes SAs to GCP SAs."
  value       = "${var.project_id}.svc.id.goog"
}

output "node_service_account" {
  description = "Node service account email."
  value       = google_service_account.nodes.email
}

output "get_credentials_command" {
  description = "Command that populates a kubeconfig context for sandbox/gke/ manifests."
  value       = "gcloud container clusters get-credentials ${google_container_cluster.sandbox.name} --region ${var.region} --project ${var.project_id}"
}

output "sandbox_node_taint" {
  description = "Toleration a sandbox pod must carry to schedule on the gVisor pool."
  value       = "sandbox.gke.io/runtime=gvisor:NoSchedule"
}
