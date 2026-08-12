# Sandbox runner

Status: Phase 1 — local temp-workspace implementation, verified.

Executes a pinned source tree plus a candidate patch somewhere disposable, then
reports what happened with the logs to back it up. Nothing here decides whether
a pull request may be opened; the Verification Agent does that, and it can only
do it honestly if this component never overstates a result.

The GKE Agent Sandbox implementation (`sandbox/gke/`) consumes the same plan
document and emits the same result record, so swapping the execution
environment does not change a single agent.

## Command contract

    python -m sandbox.runner.entrypoint --plan <plan.json> [options]

| Option | Meaning |
|---|---|
| `--plan` | path to a `sandbox.plan.v1` document (required) |
| `--base-dir` | root for relative source and patch locations (default: repository root) |
| `--sandbox-root` | parent of the run directory (default: `$PATCHAPI_SANDBOX_ROOT`, else the system temp dir) |
| `--run-id` | stable id for the run; must not already exist |
| `--retain` | keep the workspace after the run; logs are kept either way |
| `--json` | print the run record to stdout |

Exit codes: `0` every step passed, `1` the run reached a conclusion that was not
a pass, `2` the run could not be set up (bad plan, unwritable or unsafe sandbox
root).

## Run layout

    <sandbox_root>/patchapi-sandbox/<run_id>/
        workspace/     the only thing generated code may touch; destroyed unless --retain
        logs/<step>.txt one file per step, always written
        patch.diff     the exact edit that was applied
        result.json    the sandbox.result.v1 record

Evidence lives beside the workspace, never inside it, so a timeout can destroy
the environment without destroying the reason it timed out.

## Plan document (`sandbox.plan.v1`)

```json
{
  "schema_version": "sandbox.plan.v1",
  "plan_id": "egaki-baseline",
  "source": {"kind": "git", "location": "https://…/egaki", "sha": "c09e1a44…"},
  "patch": {"kind": "file", "location": "…/candidate.patch", "strip": 1},
  "steps": [
    {"name": "install", "argv": ["pnpm", "install", "--frozen-lockfile"],
     "phase": "dependencies", "timeout_seconds": 900}
  ]
}
```

- `source.kind: "git"` **must** pin a sha; a clone whose HEAD does not match is
  an error. `"path"` copies a directory and exists for fixtures and vendored
  checkouts.
- `patch.kind: "none"` (or an empty diff file) is the baseline run that proves
  the pinned source is green before any generated edit is credited with
  anything.
- `phase` is `none`, `dependencies`, or `live_verification`. It selects the
  network posture the environment applies and is the only way a step can request
  a credential.

Shipped plans live in `plans/`. `egaki-baseline.v1.json` mirrors the commands
recorded in `demo/egaki/baseline.json`; the live image smoke is a separate
`live_verification` plan issued only when a narrow Google credential is brokered
for that one step.

## Result record (`sandbox.result.v1`)

`status` is one of:

| Status | Meaning |
|---|---|
| `PASS` | every step exited 0 |
| `FAIL` | a step exited non-zero |
| `TIMEOUT` | a step exceeded its budget; its process group was destroyed |
| `PATCH_FAILED` | the candidate did not apply to the pinned source; no step ran |
| `ERROR` | the run could not be set up or a declared credential was absent |

Only `PASS` means the plan succeeded. Everything else is a stop, never a
"probably fine".

## What isolation means here, precisely

Enforced by this runner, locally and in the container alike:

- The workspace is allocated outside the repository under test, and a sandbox
  root inside it (or containing it) is refused before anything is created.
- Steps run with an environment **built from an allowlist**, not filtered by a
  denylist: no GitHub key, no admin token, no `GOOGLE_APPLICATION_CREDENTIALS`,
  no `KUBECONFIG`. `HOME` and `TMPDIR` point inside the disposable workspace.
- A credential can only be requested by a `live_verification` step and only from
  a fixed allowlist; a request for anything else is rejected when the plan
  loads. A declared credential that is unset stops the run rather than letting a
  live check degrade into a no-op that "passes".
- `argv` is a list, never a shell string. Steps run in their own process group
  so a timeout reaps the whole tree.
- `.git`, `node_modules`, `.venv`, and `.secrets` are never copied into a
  workspace.

**Not** enforced by the local runner: gVisor, default-deny networking, dropped
capabilities, CPU and memory limits, and the absence of a service-account token.
Those are properties of the SandboxTemplate and NetworkPolicy under
`sandbox/gke/`. The `phase` field is recorded and passed through as
`PATCHAPI_NETWORK_PHASE`, but locally it is a declaration, not a firewall — do
not read a local `PASS` as evidence that a step stayed offline.

## Container image

    docker build -f sandbox/runner/Dockerfile -t patchapi-sandbox-runner sandbox/runner

The build context is this directory, so nothing outside `sandbox/runner` can be
baked into an image that untrusted code runs inside. Verified invocation:

    docker run --rm --network=none --read-only \
      --tmpfs /sandbox:rw,exec,uid=1000,gid=1000 \
      --cap-drop=ALL --security-opt=no-new-privileges \
      patchapi-sandbox-runner --plan sandbox/runner/plans/testdata-good.v1.json

The image ships Node 22 and pnpm for the pinned demo target, git for pinned
checkouts, and a Python interpreter for the runner, which is standard-library
only.

## Test data

`testdata/image_service/` is a small tree whose provider knows which model
identifiers exist, so an invented one is caught by execution rather than by a
reviewer's memory:

| Patch | Outcome |
|---|---|
| `patches/noop.patch` | `PASS` — baseline, nothing applied |
| `patches/good.patch` | `PASS` — migrates to a model the provider serves |
| `patches/bad.patch` | `FAIL` — plausible, invented model id; caught at the test step |
| `patches/unappliable.patch` | `PATCH_FAILED` — generated against another revision |

## Verify

    ./scripts/verify_sandbox_local.sh

Runs the unit suite, the four fixture outcomes above, and the container path
when Docker is available; asserts the checkout is byte-identical afterwards and
appends its result to `demo/setup-ledger.ndjson`.
