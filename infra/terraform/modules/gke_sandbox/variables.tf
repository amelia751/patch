variable "project_id" {
  description = "GCP project that owns the cluster."
  type        = string
}

variable "region" {
  description = "Regional cluster location."
  type        = string
}

variable "name" {
  description = "Cluster name; also prefixes the network, subnet, and node pool."
  type        = string
}

variable "labels" {
  description = "Labels applied to the cluster and its nodes."
  type        = map(string)
  default     = {}
}

variable "release_channel" {
  description = "GKE release channel. REGULAR carries Agent Sandbox support without preview churn."
  type        = string
  default     = "REGULAR"

  validation {
    condition     = contains(["RAPID", "REGULAR", "STABLE"], var.release_channel)
    error_message = "release_channel must be RAPID, REGULAR, or STABLE."
  }
}

variable "subnet_cidr" {
  description = "Primary node CIDR."
  type        = string
  default     = "10.20.0.0/20"
}

variable "pods_cidr" {
  description = "Secondary CIDR for pods."
  type        = string
  default     = "10.21.0.0/16"
}

variable "services_cidr" {
  description = "Secondary CIDR for services."
  type        = string
  default     = "10.22.0.0/20"
}

variable "master_cidr" {
  description = "Control plane CIDR for the private cluster."
  type        = string
  default     = "172.16.0.0/28"
}

variable "master_authorized_cidrs" {
  description = "Networks allowed to reach the control plane endpoint."
  type = list(object({
    cidr_block   = string
    display_name = string
  }))
  default = []
}

variable "machine_type" {
  description = "Node machine type for the gVisor pool."
  type        = string
  default     = "e2-standard-4"
}

variable "disk_size_gb" {
  description = "Node boot disk size. Verification builds need room for node_modules."
  type        = number
  default     = 100
}

variable "min_nodes" {
  description = "Autoscaler floor. Keep at least one warm node so a demo run is not waiting on provisioning."
  type        = number
  default     = 1
}

variable "max_nodes" {
  description = "Autoscaler ceiling."
  type        = number
  default     = 3
}

variable "deletion_protection" {
  description = "Guard against terraform destroy removing the cluster."
  type        = bool
  default     = true
}
