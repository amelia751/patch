locals {
  prefix = "patchapi-${var.environment}"

  labels = {
    application = "patchapi"
    environment = var.environment
    managed-by  = "terraform"
  }

  # Service families from roadmap.md §20–§21. Names are the current GA API IDs;
  # aiplatform.googleapis.com is the Gemini Enterprise Agent Platform API in the
  # 2026 docs, and agentregistry.googleapis.com is separate (setup.md §8).
  # Agent Gateway and agent connectivity templates live under
  # networkservices.googleapis.com (projects.locations.agentGateways, v1beta1),
  # which is already listed below — there is no separate agentgateway API to
  # enable. agentidentity.googleapis.com owns projects.locations.authProviders,
  # which an Agent Registry binding attaches a published Service to. Enabling it
  # pulls in agentidentitycredentials.googleapis.com, which is why that shows up
  # in `gcloud services list` without being declared here.
  core_services = [
    "aiplatform.googleapis.com",
    "agentidentity.googleapis.com",
    "agentregistry.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudtrace.googleapis.com",
    "compute.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "networksecurity.googleapis.com",
    "networkservices.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "serviceusage.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "vpcaccess.googleapis.com",
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
    "policy-denied",
    "repo-push",
    "project-repo-added",
    "project-repo-removed",
    "index-updated",
  ]
}

# Agent Registry Service resources — the fleet's published A2A cards — are not
# Terraform-managed. Verified against the pinned providers with
# `terraform providers schema -json`: hashicorp/google and google-beta 6.x expose
# no agentregistry resource type (only the unrelated Dialogflow agents). The
# resources are created idempotently by scripts/register_agent_registry.sh, which
# derives each card from agents/config.py. Terraform owns the API enablement and
# the IAM below.
module "project_services" {
  source = "../../modules/project_services"

  project_id = var.project_id
  services   = concat(local.core_services, local.optional_services)
}

# ---------------------------------------------------------------------------
# Workload identities
# ---------------------------------------------------------------------------

module "service_accounts" {
  source = "../../modules/service_accounts"

  project_id  = var.project_id
  name_prefix = local.prefix

  service_accounts = {
    control-api = {
      display_name = "PatchAPI control plane"
      description  = "Run state transitions, event publication, dashboard backend."
      project_roles = [
        "roles/cloudsql.client",
        "roles/logging.logWriter",
        "roles/cloudtrace.agent",
        # The fleet page renders the published catalog. Read-only: publishing is
        # an operator action, not something the console can trigger.
        "roles/agentregistry.viewer",
      ]
    }
    repo-indexer = {
      display_name  = "PatchAPI repo indexer"
      description   = "Builds the API usage inventory from customer checkouts."
      project_roles = ["roles/cloudsql.client", "roles/logging.logWriter", "roles/cloudtrace.agent"]
    }
    github-tools = {
      display_name  = "PatchAPI GitHub tool adapter"
      description   = "Sole holder of the GitHub App key. No merge, admin, or branch-protection scope."
      project_roles = ["roles/logging.logWriter", "roles/cloudtrace.agent"]
    }
    agents = {
      display_name = "PatchAPI ADK agent fleet"
      description  = "Agent Runtime identity for the orchestrator and six specialists."
      project_roles = [
        "roles/aiplatform.user",
        "roles/logging.logWriter",
        "roles/cloudtrace.agent",
        # Look peers up in the catalog. An agent must not be able to rewrite what
        # the fleet claims about itself, so viewer and not editor.
        "roles/agentregistry.viewer",
      ]
    }
    # Publishes the fleet's A2A cards (scripts/register_agent_registry.sh). Split
    # from every runtime identity on purpose: registration is the one action that
    # changes what PatchAPI claims to be, and no service needs it at request time.
    # `roles/agentregistry.editor` carries services.create / .update and no IAM,
    # no project, and no Vertex permission.
    registrar = {
      display_name  = "PatchAPI agent catalog publisher"
      description   = "Registers the fleet's A2A agent cards. No runtime or data-plane access."
      project_roles = ["roles/agentregistry.editor", "roles/logging.logWriter"]
    }
    sandbox = {
      display_name  = "PatchAPI sandbox runner"
      description   = "Executes untrusted generated code. Deliberately holds no data-plane access."
      project_roles = ["roles/logging.logWriter"]
    }
  }

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# Always-on scaffolding: free at rest, safe to apply on a clean project
# ---------------------------------------------------------------------------

module "artifact_registry" {
  source = "../../modules/artifact_registry"

  project_id    = var.project_id
  region        = var.region
  repository_id = local.prefix
  description   = "PatchAPI service and sandbox runner images (${var.environment})"

  reader_members = [
    module.service_accounts.members["control-api"],
    module.service_accounts.members["github-tools"],
    module.service_accounts.members["repo-indexer"],
  ]

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
    module.service_accounts.members["repo-indexer"],
  ]

  subscriber_members = [
    module.service_accounts.members["control-api"],
    module.service_accounts.members["agents"],
    module.service_accounts.members["repo-indexer"],
  ]

  depends_on = [module.project_services]
}

module "evidence_storage" {
  source = "../../modules/evidence_storage"

  project_id    = var.project_id
  bucket_name   = "${local.prefix}-evidence-${var.project_id}"
  location      = var.region
  labels        = local.labels
  force_destroy = var.evidence_bucket_force_destroy

  # The sandbox writes build and test logs; it can read back only its own run
  # through the application layer, so object read is not granted here.
  writer_members = [
    module.service_accounts.members["agents"],
    module.service_accounts.members["sandbox"],
  ]

  reader_members = [
    module.service_accounts.members["control-api"],
  ]

  depends_on = [module.project_services]
}

module "secrets" {
  source = "../../modules/secrets"

  project_id       = var.project_id
  name_prefix      = local.prefix
  replica_location = var.region
  labels           = local.labels

  secrets = {
    github-app-private-key = {
      purpose          = "github-app"
      accessor_members = [module.service_accounts.members["github-tools"]]
    }
    github-app-id = {
      purpose          = "github-app"
      accessor_members = [module.service_accounts.members["github-tools"]]
    }
    github-webhook-secret = {
      purpose          = "github-app"
      accessor_members = [module.service_accounts.members["control-api"]]
    }
    database-url = {
      purpose = "database"
      accessor_members = [
        module.service_accounts.members["control-api"],
        module.service_accounts.members["repo-indexer"],
      ]
    }
  }

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# Gated resources
# ---------------------------------------------------------------------------

module "gke_sandbox" {
  source = "../../modules/gke_sandbox"
  count  = var.enable_gke_sandbox ? 1 : 0

  project_id              = var.project_id
  region                  = var.region
  name                    = "${local.prefix}-sandbox"
  labels                  = local.labels
  master_authorized_cidrs = var.master_authorized_cidrs

  depends_on = [module.project_services]
}

module "cloud_sql" {
  source = "../../modules/cloud_sql"
  count  = var.enable_cloud_sql ? 1 : 0

  project_id      = var.project_id
  region          = var.region
  instance_name   = "${local.prefix}-state"
  labels          = local.labels
  private_network = one(module.gke_sandbox[*].network_self_link)

  iam_user_emails = [
    module.service_accounts.emails["control-api"],
    module.service_accounts.emails["repo-indexer"],
  ]

  depends_on = [module.project_services]
}

# enable_cloud_sql without enable_gke_sandbox leaves the instance with no VPC to
# take a private IP from. Terraform module blocks accept no precondition, so the
# guard is a check assertion plus a non-nullable variable in the module.
check "cloud_sql_needs_a_network" {
  assert {
    condition     = !var.enable_cloud_sql || var.enable_gke_sandbox
    error_message = "enable_cloud_sql requires enable_gke_sandbox: the instance takes its private IP from that module's VPC."
  }
}

module "cloud_run" {
  source = "../../modules/cloud_run_service"

  for_each = var.enable_cloud_run ? var.cloud_run_images : {}

  project_id            = var.project_id
  region                = var.region
  name                  = "${local.prefix}-${each.key}"
  image                 = each.value
  service_account_email = module.service_accounts.emails[each.key]
  labels                = local.labels

  # Only the control plane faces anything outside the project; the tool adapter
  # and the indexer are reachable from inside the VPC alone.
  ingress = each.key == "control-api" ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" : "INGRESS_TRAFFIC_INTERNAL_ONLY"

  invoker_members = each.key == "control-api" ? [] : [module.service_accounts.members["control-api"]]

  env = {
    PATCHAPI_ENVIRONMENT  = var.environment
    GOOGLE_CLOUD_PROJECT  = var.project_id
    GOOGLE_CLOUD_LOCATION = var.vertex_location
    PATCHAPI_EVIDENCE_URI = module.evidence_storage.bucket_uri
    PATCHAPI_TOPIC_PREFIX = local.prefix
  }

  depends_on = [module.project_services]
}
