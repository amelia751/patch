output "service_name" {
  description = "Cloud Run service name."
  value       = google_cloud_run_v2_service.this.name
}

output "uri" {
  description = "Service URI. Reachable only by an authorized invoker unless ingress is INGRESS_TRAFFIC_ALL."
  value       = google_cloud_run_v2_service.this.uri
}
