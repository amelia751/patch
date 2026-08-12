variable "project_id" {
  description = "GCP project that owns the secrets."
  type        = string
}

variable "name_prefix" {
  description = "Prefix applied to every secret_id."
  type        = string
}

variable "replica_location" {
  description = "Single user-managed replica location, so residency is explicit."
  type        = string
}

variable "labels" {
  description = "Labels applied to every secret."
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Map of short name => container definition. Values are added out of band."
  type = map(object({
    purpose          = string
    accessor_members = list(string)
  }))
}
