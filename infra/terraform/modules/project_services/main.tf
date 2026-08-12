# Enables the GCP service families PatchAPI depends on (roadmap.md §20–§21).
#
# Enablement is additive and idempotent: a service already enabled by hand is
# adopted on the next apply without disruption. Destroy never disables an API —
# tearing down a demo environment must not silently break Vertex AI or GKE for
# anything else living in the same project.

resource "google_project_service" "enabled" {
  for_each = toset(var.services)

  project = var.project_id
  service = each.value

  disable_on_destroy         = false
  disable_dependent_services = false
}
