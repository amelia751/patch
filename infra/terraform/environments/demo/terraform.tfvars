# Demo environment. Shares the hackathon project with dev; every resource is
# prefixed patchapi-demo so the two never collide.
#
# This environment has never been applied. `terraform plan` here is expected to
# show creates for everything.

project_id  = "patch-505223"
region      = "us-central1"
environment = "demo"

vertex_location = "global"

enable_model_armor = true
