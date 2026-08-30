variable "project_id" {
  description = "Target GCP project."
  type        = string
}

variable "region" {
  description = "Default regional location for Cloud Run, GKE, Cloud SQL, and Artifact Registry."
  type        = string
  default     = "us-central1"
}

# Gemini 3.5 Flash and gemini-3.1-flash-image resolve under locations/global on
# this project; us-central1 returns 404 for those model IDs (setup.md §8). This
# is not a regional-compute setting — it is the Vertex endpoint the agents call.
variable "vertex_location" {
  description = "Vertex AI location for Gemini model calls."
  type        = string
  default     = "global"
}

variable "environment" {
  description = "Environment short name; prefixes every resource."
  type        = string
  default     = "dev"
}

# Empty on a project where scripts/bootstrap_cloud_run.sh has not run: an IAM
# binding naming a service account that does not exist is rejected, and a clean
# project must stay applyable.
variable "deploy_service_account" {
  description = "Email of the GitHub Actions deploy identity, or empty to manage no grants for it."
  type        = string
  default     = ""
}

variable "enable_model_armor" {
  description = "Enable the Model Armor API for untrusted provider-input screening."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------
# Cost- and blast-radius-gated resources.
#
# These default to false so `terraform apply` on a clean project provisions only
# free-at-rest scaffolding. Turning one on is a deliberate act recorded in
# terraform.tfvars, not a side effect of running the verifier.
# ---------------------------------------------------------------------------

variable "enable_gke_sandbox" {
  description = "Provision the GKE Agent Sandbox cluster, its VPC, and NAT."
  type        = bool
  default     = false
}

variable "enable_cloud_sql" {
  description = "Provision Cloud SQL for PostgreSQL. Requires enable_gke_sandbox for the private network."
  type        = bool
  default     = false
}

variable "enable_cloud_run" {
  description = "Provision Cloud Run services. Requires images to exist in Artifact Registry."
  type        = bool
  default     = false
}

variable "cloud_run_images" {
  description = "Map of service short name => container image. Only read when enable_cloud_run is true."
  type        = map(string)
  default     = {}
}

variable "master_authorized_cidrs" {
  description = "Networks allowed to reach the GKE control plane."
  type = list(object({
    cidr_block   = string
    display_name = string
  }))
  default = []
}

variable "evidence_bucket_force_destroy" {
  description = "Allow terraform destroy to delete a non-empty evidence bucket."
  type        = bool
  default     = false
}
