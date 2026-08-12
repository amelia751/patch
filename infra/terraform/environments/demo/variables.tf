variable "project_id" {
  description = "Target GCP project for the recorded demo."
  type        = string
}

variable "region" {
  description = "Default regional location."
  type        = string
  default     = "us-central1"
}

variable "vertex_location" {
  description = "Vertex AI location for Gemini model calls. See ../dev/variables.tf for why this is global."
  type        = string
  default     = "global"
}

variable "environment" {
  description = "Environment short name; prefixes every resource."
  type        = string
  default     = "demo"
}

variable "enable_model_armor" {
  description = "Enable the Model Armor API for untrusted provider-input screening."
  type        = bool
  default     = true
}
