# `agents/` — the Google ADK fleet

Status: four reasoning agents (Change Intelligence, Impact, Patch, Verification)
plus two Python stages (Policy, PR). Policy is `packages.policy`; PR waits on
an independent Verification PASS. The Gemini 2.0 vertical slice runs through
Patch and stops at `TESTING`.

Google ADK is the only agent framework here, at runtime and in tests
(`CLAUDE.md` constraint 1). `tests/test_framework_compliance.py` parses every
runtime module in this tree and fails if another one appears. `google.adk` is
named only in `adk.py`, and only inside functions.

## Verify

```bash
./scripts/verify_agents_adk.sh
```

Compliance and offline checks always run. The live turn calls Gemini 3.5 Flash
on Vertex and prints `SKIP` with a reason when credentials are absent — set
`PATCHAPI_REQUIRE_LIVE=1` to make that a failure.

```bash
uv run --all-packages python scripts/smoke_adk_orchestrator.py
uv run --all-packages python scripts/smoke_patch_loop.py --deterministic
```

## Shape

```text
agents/
  adk.py                 # the only ADK import: LlmAgent + Runner + Vertex
  config.py              # pins, ToolName, grants
  context.py             # RunContext
  orchestrator.py        # state machine; Policy/PR are Python here
  command_allowlist.py   # argv shapes for run_command
  guardrails.py          # before_tool / after_tool
  trace.py
  specialists/           # instruction + AgentId; each calls adk.build_agent
    change_intelligence.py
    impact.py
    patch.py
    verification.py
  tools/
    shared.py            # record_human_required
    credentials.py       # list_runtime_credentials + request_runtime_credentials
    results.py
    change/              # feed + record
    impact/              # session-first scan + record
    patch/               # skill + workspace four
    verification/        # evidence readers + record
    policy.py            # orchestrator-only; not an LlmAgent grant
    pr.py                # orchestrator-only; opens a PR via github-tools after PASS
  tests/
```

## The three properties this tree exists to guarantee

**An agent can only do what its allowlist names.** `config.TOOL_ALLOWLISTS` is
the topology. `tools.build_tools` constructs exactly those functions, and
`guardrails.before_tool` refuses anything else before the function is entered —
so Patch cannot open a pull request and Change Intelligence cannot read a
repository, structurally rather than by instruction.

**An agent cannot commit a fact the deterministic layer does not support.** Each
stage pairs a deterministic reader with a `record_*` tool that cross-checks.
`record_change_manifest` refuses a confirmation that disagrees with the parsed
notice; `record_impact_report` commits the scanner's findings, not the model's;
`record_policy_decision` takes its permissions from `packages.policy`. An agent
can escalate. It cannot invent, and it cannot permit.

**Every tool call is on the record.** Both callbacks are attached by
`adk.build_agent`, so no tool runs untraced. Events carry the tool, bounded
arguments, duration, and a digest of the result — enough to prove what a run did
without copying provider text or repository source into a second store.

## Where the trust boundary sits

A provider notice reaches the model only through `load_provider_notice`, which
strips the fields PatchAPI itself wrote onto the document
(`INTERNAL_ENVELOPE_FIELDS`) and runs the remainder through the deterministic
injection gate. Tool policy is stated in the system instruction
(`adk.PREAMBLE`) and nowhere else.
