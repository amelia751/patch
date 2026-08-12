variable "project_id" {
  description = "GCP project that owns the instance."
  type        = string
}

variable "region" {
  description = "Instance region."
  type        = string
}

variable "instance_name" {
  description = "Cloud SQL instance name."
  type        = string
}

variable "database_name" {
  description = "Application database created on the instance."
  type        = string
  default     = "patchapi"
}

variable "database_version" {
  description = "Postgres major version, pinned so a provider upgrade cannot move it."
  type        = string
  default     = "POSTGRES_16"
}

variable "tier" {
  description = "Machine tier. The hackathon workload is small."
  type        = string
  default     = "db-custom-1-3840"
}

variable "availability_type" {
  description = "ZONAL or REGIONAL."
  type        = string
  default     = "ZONAL"

  validation {
    condition     = contains(["ZONAL", "REGIONAL"], var.availability_type)
    error_message = "availability_type must be ZONAL or REGIONAL."
  }
}

variable "disk_size_gb" {
  description = "Initial disk size; autoresize is enabled."
  type        = number
  default     = 10
}

variable "transaction_log_retention_days" {
  description = "Point-in-time recovery window."
  type        = number
  default     = 7
}

variable "private_network" {
  description = "Self link of the VPC the private IP is allocated from."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("/networks/[^/]+$", var.private_network))
    error_message = "private_network must be a VPC self link ending in /networks/<name>."
  }
}

variable "iam_user_emails" {
  description = "Service account emails granted IAM database authentication."
  type        = list(string)
  default     = []
}

variable "deletion_protection" {
  description = "Guard against terraform destroy removing authoritative workflow state."
  type        = bool
  default     = true
}

variable "labels" {
  description = "Labels applied to the instance."
  type        = map(string)
  default     = {}
}
