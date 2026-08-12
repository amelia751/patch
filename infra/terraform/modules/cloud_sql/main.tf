# Authoritative workflow state: run status, idempotency keys, audit events, and
# the API usage inventory (roadmap.md §10.1, CLAUDE.md constraint 7).
#
# The instance takes no public IP and accepts IAM database authentication, so a
# service reaches it through the Cloud SQL connector under its own identity
# rather than a shared password. No user password is managed here — putting one
# in a variable would put it in state.

# Private IP requires a VPC peering range handed to the Service Networking API
# before the instance is created. Terraform cannot infer this ordering, so the
# instance depends on the connection explicitly.
resource "google_compute_global_address" "private_service_access" {
  project       = var.project_id
  name          = "${var.instance_name}-psa"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = var.private_network
}

resource "google_service_networking_connection" "private_service_access" {
  network                 = var.private_network
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_access.name]
}

resource "google_sql_database_instance" "state" {
  depends_on = [google_service_networking_connection.private_service_access]

  project          = var.project_id
  name             = var.instance_name
  region           = var.region
  database_version = var.database_version

  deletion_protection = var.deletion_protection

  settings {
    tier              = var.tier
    availability_type = var.availability_type
    disk_type         = "PD_SSD"
    disk_size         = var.disk_size_gb
    disk_autoresize   = true

    user_labels = var.labels

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = var.private_network
      enable_private_path_for_google_cloud_services = true
      ssl_mode                                      = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = var.transaction_log_retention_days
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    insights_config {
      query_insights_enabled = true
      record_client_address  = false
    }
  }
}

resource "google_sql_database" "app" {
  project  = var.project_id
  instance = google_sql_database_instance.state.name
  name     = var.database_name
}

# IAM database users: no passwords exist to leak or rotate.
resource "google_sql_user" "iam" {
  for_each = toset(var.iam_user_emails)

  project  = var.project_id
  instance = google_sql_database_instance.state.name
  # Cloud SQL IAM service-account users are named without the domain suffix.
  name = trimsuffix(each.value, ".gserviceaccount.com")
  type = "CLOUD_IAM_SERVICE_ACCOUNT"
}
