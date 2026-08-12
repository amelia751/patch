# One workload identity per PatchAPI service, plus the project-level roles that
# have no resource-scoped equivalent. Resource-scoped grants (bucket, secret,
# topic) are wired in the environment root so the grant sits next to the
# resource it protects.
#
# Trust-boundary note (CLAUDE.md §8, roadmap §7.3): the sandbox runner identity
# is intentionally the weakest here. It gets log writing and nothing else, so a
# patch that escapes the generated-code boundary still holds no capability to
# read customer source, reach Secret Manager, or call GitHub.

resource "google_service_account" "workload" {
  for_each = var.service_accounts

  project      = var.project_id
  account_id   = "${var.name_prefix}-${each.key}"
  display_name = each.value.display_name
  description  = each.value.description
}

locals {
  # Flatten {sa_key => [role, ...]} into one binding per (sa, role) pair.
  project_role_bindings = merge([
    for sa_key, sa in var.service_accounts : {
      for role in sa.project_roles :
      "${sa_key}:${role}" => { sa_key = sa_key, role = role }
    }
  ]...)
}

resource "google_project_iam_member" "workload" {
  for_each = local.project_role_bindings

  project = var.project_id
  role    = each.value.role
  member  = "serviceAccount:${google_service_account.workload[each.value.sa_key].email}"
}
