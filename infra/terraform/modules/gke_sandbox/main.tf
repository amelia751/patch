# GKE Standard cluster that hosts GKE Agent Sandbox (roadmap.md §13).
#
# Autopilot is deliberately not used: the sandbox node pool needs an explicit
# gVisor runtime, and node-level sandboxing is a Standard-only control.
#
# This module provisions the cluster and its isolation posture only. Installing
# the Agent Sandbox operator and applying SandboxTemplate / NetworkPolicy
# manifests is kubectl-and-Helm work owned by sandbox/gke/ — Terraform does not
# reach into the cluster, so a broken manifest cannot corrupt infrastructure
# state. See ../../README.md for the ordering.

resource "google_compute_network" "sandbox" {
  project                 = var.project_id
  name                    = "${var.name}-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "sandbox" {
  project       = var.project_id
  name          = "${var.name}-subnet"
  region        = var.region
  network       = google_compute_network.sandbox.id
  ip_cidr_range = var.subnet_cidr

  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }
}

# Untrusted generated code gets no route to the internet by default. Egress for
# package installs during a verification build goes through this NAT, which is
# the single chokepoint an operator can log or revoke.
resource "google_compute_router" "sandbox" {
  project = var.project_id
  name    = "${var.name}-router"
  region  = var.region
  network = google_compute_network.sandbox.id
}

resource "google_compute_router_nat" "sandbox" {
  project = var.project_id
  name    = "${var.name}-nat"
  region  = var.region
  router  = google_compute_router.sandbox.name

  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

resource "google_container_cluster" "sandbox" {
  project  = var.project_id
  name     = var.name
  location = var.region

  network    = google_compute_network.sandbox.id
  subnetwork = google_compute_subnetwork.sandbox.id

  # The default pool is removed immediately; every workload lands on the
  # explicitly configured sandbox pool below.
  remove_default_node_pool = true
  initial_node_count       = 1

  deletion_protection = var.deletion_protection

  release_channel {
    channel = var.release_channel
  }

  # Per-agent least privilege depends on Workload Identity rather than node
  # service account keys.
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_cidr
  }

  master_authorized_networks_config {
    dynamic "cidr_blocks" {
      for_each = var.master_authorized_cidrs
      content {
        cidr_block   = cidr_blocks.value.cidr_block
        display_name = cidr_blocks.value.display_name
      }
    }
  }

  # Default-deny pod-to-pod traffic; sandbox/gke/ layers the explicit allows.
  network_policy {
    enabled  = true
    provider = "CALICO"
  }

  addons_config {
    network_policy_config {
      disabled = false
    }
  }

  logging_service    = "logging.googleapis.com/kubernetes"
  monitoring_service = "monitoring.googleapis.com/kubernetes"

  resource_labels = var.labels
}

resource "google_service_account" "nodes" {
  project      = var.project_id
  account_id   = "${var.name}-nodes"
  display_name = "GKE node identity for ${var.name}"
  description  = "Minimum node-level permissions; sandbox workloads use Workload Identity instead."
}

resource "google_project_iam_member" "nodes" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/artifactregistry.reader",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

resource "google_container_node_pool" "sandbox" {
  provider = google-beta

  project  = var.project_id
  name     = "${var.name}-gvisor"
  cluster  = google_container_cluster.sandbox.id
  location = var.region

  initial_node_count = var.min_nodes

  autoscaling {
    min_node_count = var.min_nodes
    max_node_count = var.max_nodes
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = var.machine_type
    disk_size_gb = var.disk_size_gb
    disk_type    = "pd-balanced"
    image_type   = "COS_CONTAINERD"

    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    # Kernel-level isolation for LLM-generated code.
    sandbox_config {
      sandbox_type = "gvisor"
    }

    workload_metadata_config {
      # Blocks the legacy metadata endpoint, so a sandboxed process cannot read
      # the node service account token.
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    labels = merge(var.labels, { workload = "agent-sandbox" })

    # Only pods that explicitly tolerate the gVisor taint schedule here.
    taint {
      key    = "sandbox.gke.io/runtime"
      value  = "gvisor"
      effect = "NO_SCHEDULE"
    }
  }
}
