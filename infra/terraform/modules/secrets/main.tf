# Secret *containers* only. Terraform never manages a google_secret_manager_secret_version,
# because doing so would put the plaintext into state and into any plan output a
# reviewer pastes into a terminal.
#
# Populate a value out of band, once, per docs/operations.md:
#   gcloud secrets versions add <name> --data-file=.secrets/<file> --project <project>
#
# Accessor grants are per-secret, never project-wide: the GitHub App private key
# is readable by the github_tools identity alone, which is what keeps
# CLAUDE.md §8 ("agents receive capabilities, never raw tokens") true at the
# infrastructure layer rather than only in application code.

resource "google_secret_manager_secret" "this" {
  for_each = var.secrets

  project   = var.project_id
  secret_id = "${var.name_prefix}-${each.key}"
  labels    = merge(var.labels, { purpose = each.value.purpose })

  replication {
    user_managed {
      replicas {
        location = var.replica_location
      }
    }
  }
}

locals {
  accessor_bindings = merge([
    for secret_key, secret in var.secrets : {
      for member in secret.accessor_members :
      "${secret_key}:${member}" => { secret_key = secret_key, member = member }
    }
  ]...)
}

resource "google_secret_manager_secret_iam_member" "accessors" {
  for_each = local.accessor_bindings

  project   = var.project_id
  secret_id = google_secret_manager_secret.this[each.value.secret_key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}
