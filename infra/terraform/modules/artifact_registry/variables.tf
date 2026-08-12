variable "project_id" {
  description = "GCP project that owns the repository."
  type        = string
}

variable "region" {
  description = "Artifact Registry location."
  type        = string
}

variable "repository_id" {
  description = "Repository id, e.g. patchapi-dev."
  type        = string
}

variable "description" {
  description = "Human-readable purpose of the repository."
  type        = string
  default     = "PatchAPI service and sandbox runner images"
}

variable "keep_versions" {
  description = "Number of recent versions the cleanup policy retains."
  type        = number
  default     = 10
}

variable "reader_members" {
  description = "IAM members granted pull-only access."
  type        = list(string)
  default     = []
}
