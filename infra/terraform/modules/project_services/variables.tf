variable "project_id" {
  description = "GCP project that owns the enabled services."
  type        = string
}

variable "services" {
  description = "Fully qualified service API names, e.g. run.googleapis.com."
  type        = list(string)

  validation {
    condition     = alltrue([for s in var.services : endswith(s, ".googleapis.com")])
    error_message = "Each service must be a fully qualified *.googleapis.com API name."
  }
}
