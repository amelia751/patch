terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.8"
    }
    # node_config.sandbox_config — the gVisor runtime selector — exists only in
    # the beta provider as of google 6.x, so the node pool is declared against
    # google-beta while everything else stays on GA.
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.8"
    }
  }
}
