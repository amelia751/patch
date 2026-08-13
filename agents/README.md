# `agents/` — the Google ADK fleet

Status: Change Intelligence runs end to end against the pinned Google
deprecation fixture. The other five specialists construct, hold their tool
allowlists, and are wired into the trace; their stages wait on the sandbox
workspace and sandbox evidence that later phases produce.

Google ADK is the only agent framework here, at runtime and in tests
(`CLAUDE.md` constraint 1). `tests/test_framework_compliance.py` parses every
runtime module in this tree and fails if another one appears.

## Verify

```bash
./scripts/verify_agents_adk.sh
```

Compliance and offline checks always run. The live turn calls Gemini 3.5 Flash
on Vertex and prints `SKIP` with a reason when credentials are absent — set
`PATCHAPI_REQUIRE_LIVE=1` to make that a failure.

```bash
uv run --all-packages python scripts/smoke_adk_orchestrator.py
```

## Shape

| File | Holds |
|---|---|
| `config.py` | model pin, prompt versions, every tool allowlist |
| `command_allowlist.py` | argv shapes `run_command` will execute |
| `environment.py` | local workspace exec; same result shape as a GKE swap |
| `context.py` | the roots a run's tools may read, and what they recorded |
| `trace.py` | the tool-trace stream the dashboard renders |
| `guardrails.py` | allowlist enforcement and trace capture at the tool boundary |
| `runtime.py` | Vertex wiring and one-turn execution |
| `specialist.py` | the single `LlmAgent` constructor every agent goes through |
| `orchestrator.py` | the deterministic state machine that calls the agents |
| `tools/` | the typed tool contracts, one module per stage |
| `change_intelligence.py` … `pr.py` | one file per specialist: identity, description, instruction |

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
`build_specialist`, so no tool runs untraced. Events carry the tool, bounded
arguments, duration, and a digest of the result — enough to prove what a run did
without copying provider text or repository source into a second store.

## Where the trust boundary sits

A provider notice reaches the model only through `load_provider_notice`, which
strips the fields PatchAPI itself wrote onto the document
(`INTERNAL_ENVELOPE_FIELDS`) and runs the remainder through the deterministic
injection gate. Tool policy is stated in the system instruction
(`specialist.PREAMBLE`) and nowhere else.
