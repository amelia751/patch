variable "project_id" {
  description = "GCP project that owns the service."
  type        = string
}

variable "region" {
  description = "Cloud Run region."
  type        = string
}

variable "name" {
  description = "Service name."
  type        = string
}

variable "image" {
  description = "Fully qualified container image. Pin by digest for anything a run depends on."
  type        = string
}

variable "service_account_email" {
  description = "Runtime identity for the service."
  type        = string
}

variable "ingress" {
  description = "Cloud Run ingress setting."
  type        = string
  default     = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  validation {
    condition = contains([
      "INGRESS_TRAFFIC_ALL",
      "INGRESS_TRAFFIC_INTERNAL_ONLY",
      "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER",
    ], var.ingress)
    error_message = "ingress must be a valid Cloud Run ingress value."
  }
}

variable "invoker_members" {
  description = "IAM members granted roles/run.invoker. Empty means no caller is authorized yet."
  type        = list(string)
  default     = []

  validation {
    condition     = !contains(var.invoker_members, "allUsers")
    error_message = "Public invocation is not permitted; front the service with an authenticated caller."
  }
}

variable "container_port" {
  description = "Port the container listens on."
  type        = number
  default     = 8080
}

variable "cpu" {
  description = "CPU limit."
  type        = string
  default     = "1"
}

variable "memory" {
  description = "Memory limit."
  type        = string
  default     = "512Mi"
}

variable "min_instances" {
  description = "Scale-to-zero floor."
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Instance ceiling."
  type        = number
  default     = 3
}

variable "vpc_connector" {
  description = "Serverless VPC Access connector for private Cloud SQL reach, or null."
  type        = string
  default     = null
}

variable "env" {
  description = "Plain environment variables. Never put a credential here."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for k in keys(var.env) :
      !can(regex("(?i)(secret|password|private_key|token|api_key)", k))
    ])
    error_message = "Credential-shaped names must go through secret_env, not env."
  }
}

variable "secret_env" {
  description = "Map of env var name => Secret Manager secret_id, resolved at start."
  type        = map(string)
  default     = {}
}

variable "labels" {
  description = "Labels applied to the service."
  type        = map(string)
  default     = {}
}
