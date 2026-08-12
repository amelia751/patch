# Development environment for the hackathon build.
#
# Gated resources are off. Turning one on costs money and widens blast radius,
# so flip it here deliberately and apply with APPLY_INFRA=1 — never as a side
# effect of running scripts/verify_infra_terraform.sh.

project_id  = "patch-505223"
region      = "us-central1"
environment = "dev"

# Gemini 3.5 Flash and gemini-3.1-flash-image resolve under locations/global on
# this project; us-central1 returns 404 for those model IDs.
vertex_location = "global"

enable_model_armor = true

enable_gke_sandbox = false
enable_cloud_sql   = false
enable_cloud_run   = false

# Populate once images exist, e.g.
#   control-api = "us-central1-docker.pkg.dev/patch-505223/patchapi-dev/control-api@sha256:..."
cloud_run_images = {}
