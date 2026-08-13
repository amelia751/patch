# Demo environment — deliberately a stub.
#
# It provisions only the identities and the free-at-rest scaffolding needed to
# stand a recorded run up next to dev without sharing dev's topics, buckets, or
# secret containers. GKE, Cloud SQL, and Cloud Run are intentionally absent
# rather than flag-disabled: the flagship demo runs against the dev cluster, and
# a second cluster nobody rehearses on is a liability during a recording.
#
# To promote this to a full environment, copy the gated module blocks from
# ../dev/main.tf. The modules are shared, so nothing needs rewriting.

locals {
  prefix = "patchapi-${var.environment}"

  labels = {
    application = "patchapi"
    environment = var.environment
    managed-by  = "terraform"
  }

  core_services = [
    "aiplatform.googleapis.com",
    "agentregistry.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudtrace.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
  ]

  optional_services = var.enable_model_armor ? ["modelarmor.googleapis.com"] : []

  # roadmap.md §10.4
  event_topics = [
    "provider-change-detected",
    "change-normalized",
    "repo-impact-requested",
    "repo-affected",
    "patch-requested",
    "sandbox-complete",
    "verification-requested",
    "pr-requested",
    "repo-push",
    "project-repo-added",
    "project-repo-removed",
    "index-updated",
  ]
}

module "project_services" {
  source = "../../modules/project_services"

  project_id = var.project_id
  services   = concat(local.core_services, local.optional_services)
}

module "service_accounts" {
  source = "../../modules/service_accounts"

  project_id  = var.project_id
  name_prefix = local.prefix

  service_accounts = {
    control-api = {
      display_name  = "PatchAPI control plane (demo)"
      description   = "Run state transitions and event publication for the recorded demo."
      project_roles = ["roles/logging.logWriter", "roles/cloudtrace.agent"]
    }
    agents = {
      display_name  = "PatchAPI ADK agent fleet (demo)"
      description   = "Agent Runtime identity for the orchestrator and six specialists."
      project_roles = ["roles/aiplatform.user", "roles/logging.logWriter", "roles/cloudtrace.agent"]
    }
    sandbox = {
      display_name  = "PatchAPI sandbox runner (demo)"
      description   = "Executes untrusted generated code. Deliberately holds no data-plane access."
      project_roles = ["roles/logging.logWriter"]
    }
  }

  depends_on = [module.project_services]
}

module "eventing" {
  source = "../../modules/eventing"

  project_id  = var.project_id
  name_prefix = local.prefix
  topics      = local.event_topics
  labels      = local.labels

  publisher_members = [
    module.service_accounts.members["control-api"],
    module.service_accounts.members["agents"],
  ]

  subscriber_members = [
    module.service_accounts.members["control-api"],
    module.service_accounts.members["agents"],
  ]

  depends_on = [module.project_services]
}

module "evidence_storage" {
  source = "../../modules/evidence_storage"

  project_id  = var.project_id
  bucket_name = "${local.prefix}-evidence-${var.project_id}"
  location    = var.region
  labels      = local.labels

  writer_members = [
    module.service_accounts.members["agents"],
    module.service_accounts.members["sandbox"],
  ]

  reader_members = [
    module.service_accounts.members["control-api"],
  ]

  depends_on = [module.project_services]
}
