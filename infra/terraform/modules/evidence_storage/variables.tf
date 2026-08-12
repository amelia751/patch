variable "project_id" {
  description = "GCP project that owns the bucket."
  type        = string
}

variable "bucket_name" {
  description = "Globally unique bucket name."
  type        = string
}

variable "location" {
  description = "Bucket location; keep it aligned with the compute region."
  type        = string
}

variable "labels" {
  description = "Labels applied to the bucket."
  type        = map(string)
  default     = {}
}

variable "force_destroy" {
  description = "Allow terraform destroy to delete a non-empty evidence bucket."
  type        = bool
  default     = false
}

variable "nearline_after_days" {
  description = "Age at which live evidence objects move to NEARLINE."
  type        = number
  default     = 30
}

variable "noncurrent_retention_days" {
  description = "Age at which superseded object versions are deleted."
  type        = number
  default     = 90
}

variable "writer_members" {
  description = "IAM members granted read/write on objects (no bucket admin)."
  type        = list(string)
  default     = []
}

variable "reader_members" {
  description = "IAM members granted object read only."
  type        = list(string)
  default     = []
}
