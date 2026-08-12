output "enabled_services" {
  description = "Service API names managed by this module."
  value       = sort([for s in google_project_service.enabled : s.service])
}
