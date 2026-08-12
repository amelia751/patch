output "instance_name" {
  description = "Cloud SQL instance name."
  value       = google_sql_database_instance.state.name
}

output "connection_name" {
  description = "project:region:instance string used by the Cloud SQL connector."
  value       = google_sql_database_instance.state.connection_name
}

output "private_ip_address" {
  description = "Private IP of the instance."
  value       = google_sql_database_instance.state.private_ip_address
}

output "database_name" {
  description = "Application database name."
  value       = google_sql_database.app.name
}
