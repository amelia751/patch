# PatchAPI infrastructure

**Status:** `dev` plans clean against `patch-505223`; nothing has been applied.
Gated modules (GKE, Cloud SQL, Cloud Run) are switched off. `demo` is a stub
that has never been applied.

Terraform for the GCP services in [`roadmap.md`](../../roadmap.md) §20–§21.

```
infra/terraform/
├── modules/
│   ├── project_services/    API enablement (§21)
│   ├── service_accounts/    one workload identity per service
│   ├── artifact_registry/   container images, immutable tags
│   ├── eventing/            Pub/Sub topics + subscriptions (§10.4)
│   ├── evidence_storage/    run evidence bucket (§10.3)
│   ├── secrets/             Secret Manager containers, no values
│   ├── gke_sandbox/         Agent Sandbox cluster, gVisor pool (§13)
│   ├── cloud_sql/           authoritative workflow state (§10.1)
│   └── cloud_run_service/   one service, own identity, closed ingress
└── environments/
    ├── dev/                 full composition, gated resources off
    └── demo/                identities + eventing + evidence only
```

## Run it

```bash
./scripts/verify_infra_terraform.sh              # fmt, init, validate, plan
APPLY_INFRA=1 ./scripts/verify_infra_terraform.sh  # ... then apply
INFRA_ENV_DIR=infra/terraform/environments/demo ./scripts/verify_infra_terraform.sh
```

Every environment is initialized and validated on each run; only the selected
one is planned. Credentials resolve from `GOOGLE_APPLICATION_CREDENTIALS`,
falling back to `.secrets/gcp-service-account.json`, then to gcloud ADC. With
none of those the script exits `SKIP`, never a validate-only pass dressed up as
success.

## What applies by default

`terraform apply` on a clean project provisions API enablement, five workload
identities, an Artifact Registry repository, the eight event topics with their
subscriptions and a shared dead-letter topic, the evidence bucket, and four
empty secret containers. All of it is free at rest.

Three things are behind flags in `environments/dev/terraform.tfvars` because
they cost money and widen blast radius:

| Flag | Provisions | Turn on when |
|---|---|---|
| `enable_gke_sandbox` | VPC, NAT, GKE Standard cluster, gVisor node pool | `T-sandbox-gke` needs a real cluster |
| `enable_cloud_sql` | Postgres 16, private IP, IAM database auth | local Postgres is no longer enough |
| `enable_cloud_run` | one service per entry in `cloud_run_images` | images exist in Artifact Registry |

`enable_cloud_sql` requires `enable_gke_sandbox`; the instance takes its private
IP from that module's VPC. The `cloud_sql_needs_a_network` check block catches
the combination during plan.

## Ordering that Terraform does not express

1. **Secret values.** Terraform creates empty containers only — a managed
   `secret_version` would put plaintext into state and into any plan a reviewer
   pastes into a terminal. Run `terraform output populate_secrets_commands` and
   execute each one once against a file under `.secrets/`.
2. **Agent Sandbox operator.** The cluster is Terraform's; installing the Agent
   Sandbox operator and applying `SandboxTemplate` / `NetworkPolicy` manifests
   is kubectl-and-Helm work owned by `sandbox/gke/`. Terraform holds no
   Kubernetes provider, so a broken manifest cannot corrupt infrastructure
   state. Start from `terraform output gke_get_credentials_command`.
3. **Container images.** `enable_cloud_run` reads `cloud_run_images`; build and
   push before flipping the flag. Pin by digest, not tag — the registry sets
   `immutable_tags`, but a digest is what a verification result cites.

## Decisions worth knowing

**Region is `us-central1`.** Gemini model calls are the exception: on this
project `gemini-3.5-flash` and `gemini-3.1-flash-image` resolve under
`locations/global` and return 404 in `us-central1`
([`setup.md`](../../setup.md) §8). That is the `vertex_location` variable, and
it is not a compute-region setting.

**GKE is Standard, not Autopilot.** The sandbox node pool needs an explicit
gVisor runtime, and node-level sandboxing is a Standard-only control.
`node_config.sandbox_config` exists only in the `google-beta` provider as of
google 6.x, so that one resource is declared against beta while everything else
stays GA.

**API enablement never reverses.** `disable_on_destroy = false` throughout.
Tearing down a demo environment must not silently break Vertex AI or GKE for
anything else in the project.

**State is local.** Fine for a hackathon with one operator. Moving to a GCS
backend means creating the bucket out of band first, then adding a `backend
"gcs"` block and running `terraform init -migrate-state` — a backend block that
points at a bucket this configuration has not created breaks `init` on a clean
checkout, so it is not committed pre-emptively.

**No compliance claims.** Regional resources and a private cluster are not a
certification. Nothing here asserts one.

## Deliberate non-goals

- No `google_project_iam_policy` anywhere — it is authoritative and would strip
  bindings this configuration does not know about.
- No `allUsers` invoker on any Cloud Run service; the module rejects it.
- No `roles/owner` or `roles/editor` on a workload identity; the module rejects
  those too.
- No branch-protection, merge, or repository-admin surface of any kind. PatchAPI
  stops at the pull request ([`README.md`](../../README.md)).
