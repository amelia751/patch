# Provider and CLI versions are pinned here, never at a resource call site.
# Upper bounds are deliberate: the google provider makes breaking changes across
# major versions, and an unpinned upgrade would rewrite a plan under a demo.

terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.8"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.8"
    }
  }

  # State is local for the hackathon build. Migrating to a GCS backend is a
  # documented follow-up in ../../README.md; do not add a backend block that
  # points at a bucket this configuration has not created yet, because it
  # breaks `terraform init` on a clean checkout.
}
