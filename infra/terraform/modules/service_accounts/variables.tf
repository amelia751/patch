variable "project_id" {
  description = "GCP project that owns the service accounts."
  type        = string
}

variable "name_prefix" {
  description = "Prefix applied to every account_id, e.g. patchapi-dev."
  type        = string

  validation {
    # account_id is capped at 30 characters; the longest key below is 14.
    condition     = length(var.name_prefix) <= 15
    error_message = "name_prefix must be 15 characters or fewer to keep account_id within the 30-character limit."
  }
}

variable "service_accounts" {
  description = "Map of short name => identity definition."
  type = map(object({
    display_name  = string
    description   = string
    project_roles = list(string)
  }))

  validation {
    condition = alltrue([
      for sa in var.service_accounts :
      !contains(sa.project_roles, "roles/owner") && !contains(sa.project_roles, "roles/editor")
    ])
    error_message = "Least privilege: workload identities may not hold roles/owner or roles/editor."
  }
}
