# Agents rewrite plan

**Status:** layout landed — `specialists/` + `tools/{change,impact,patch,verification}`, four LlmAgents, Policy/PR are Python. Remaining: Verification `evidence_root` on the live slice, PR via github_tools after PASS.
**Contracts:** `roadmap.md` §8 (jobs) and §9 (state machine).
**ADK catalog:** `.local/research/adk-tooling-ecosystem.md`.
**Installed pin:** `google-adk==2.1.0`. Reasoning model: `gemini-3.5-flash`.

This plan is how the `agents/` tree gets out of “six nearly-identical specialist
files plus a 700-line orchestrator” and into the shape the roadmap already
specified: **four reasoning agents, two deterministic stages, one ADK wiring
module, one grant table.**

There is no `agents.py` today. The rewrite introduces `agents/adk.py` as that
single module — the thing a reader would expect `agents.py` to be.

---

## 1. What is messy today

The topology is correct. The packaging is not.

| Problem | Where |
|---|---|
| Six `LlmAgent`s even though §8.3 and §8.6 are **not agents** | `policy.py`, `pr.py` |
| ADK construction split across `specialist.py` + `runtime.py` + each `*.py` | three places to change a callback |
| Fresh `InMemoryRunner` + new session **per turn**, then `close()` | `runtime.run_turn` — no session, no resume |
| Two local exec stacks | `agents/environment.py` **and** `sandbox/session.py` |
| Tools registered by walking every builder, then filtering by name | `tools/__init__.py` — easy to grant a tool that “exists” for the wrong stage |
| Impact scans a host `Path`, with a late GKE walk bolted on | `tools/repo_inventory.py` |
| Policy agent wraps `packages.policy` instead of the orchestrator calling it | `tools/policy_gate.py` |
| PR agent’s `open_pull_request` always refuses | `tools/pull_request.py` |
| Orchestrator owns seed/scan/patch-check **and** the state machine | `orchestrator.py` (~700 lines) |
| `docs/agent-contracts.md` still says Policy and PR are agents | drift from §8 |

What we keep: allowlists in `config.py`, `before_tool` / `after_tool` in
`guardrails.py`, `record_*` that refuse invented facts, `test_framework_compliance.py`.

---

## 2. Roadmap jobs (source of truth)

§8 is explicit: **four reasoning agents** and **two deterministic components**.

```text
RECEIVED → SANITIZED → NORMALIZED
       → IMPACT_SCANNING → POLICY_EVALUATION
       → PATCHING → BUILDING → TESTING
       → VERIFYING → PR_CREATING → PR_CREATED
```

`PATCHING` is one state. The Patch agent’s edit/run loop lives *inside* it.
`BUILDING` / `TESTING` are the orchestrator’s clean evidence run, not the
agent’s own `run_command` output.

| Stage | Kind | In | Out | May not |
|---|---|---|---|---|
| **Change Intelligence** §8.1 | ADK agent | sanitized provider snapshot | `ChangeManifest` (per-id `replacements[]`, `source_conflicts[]`) | GitHub, repo, sandbox |
| **Impact** §8.2 | ADK agent | manifest + inventory/index rows + snippets | `ImpactReport` | write, fetch provider pages, GitHub |
| **Policy** §8.3 | **Python**, `packages.policy` | manifest + impact + rules | `PolicyDecision` | a model loosening a deny |
| **Patch** §8.4 | ADK agent | manifest + impact + skill + sandbox | `PatchPlan` + unified diff | GitHub, evidence sandbox, live API creds, self-grade |
| **Verification** §8.5 | ADK agent | manifest + snippets + **orchestrator** logs + diff | `VerificationReport` (veto) | Patch’s plan/transcript, sandbox write, GitHub |
| **PR publisher** §8.6 | **Python** → `github_tools` | `VerificationReport == PASS` + approved bytes | branch / commit / PR | merge, admin, secrets, branch protection |

Semantic Governance (preview) may sit **beside** Policy as a second opinion. It
can only tighten (`ALLOW`+deny → `HUMAN_REQUIRED`). It never replaces
`packages.policy`.

---

## 3. Target layout

```text
agents/
  adk.py                 # THE rewrite of “agents.py”: LlmAgent + Runner + session
  config.py              # pins, ToolName, grants — unchanged role
  context.py             # RunContext
  orchestrator.py        # state machine only; no tool implementations
  command_allowlist.py   # argv shapes for run_command
  guardrails.py          # before_tool / after_tool
  trace.py
  specialists/
    change_intelligence.py
    impact.py
    patch.py
    verification.py      # instruction + AgentId only
  tools/
    shared.py            # record_human_required
    results.py
    change/              # feed + optional ADK search wrapper
    impact/              # scan (session-first) + record
    patch/               # skill, workspace four
    verification/        # evidence readers + record
  tests/
```

Delete after the move (behavior preserved, not dropped):

- `specialist.py` → `adk.build_agent`
- `runtime.py` → `adk.run_turn` + `adk.configure_vertex`
- `policy.py`, `tools/policy_gate.py` as **agent** surface → orchestrator calls
  `packages.policy` directly (keep the gate tests)
- `pr.py` as **agent** → orchestrator calls `github_tools` after PASS
- `environment.py` → `sandbox.session.LocalSession` only

`AgentId.POLICY` and `AgentId.PR` remain as **trace / stage names**, not as
`LlmAgent`s. The compliance test should assert those two IDs never construct
an `LlmAgent`.

---

## 4. `adk.py` — one place ADK is configured

Nothing else imports `google.adk` at module scope. `adk.py` imports it inside
functions, same rule as today.

```text
build_agent(agent_id, instruction, context, trace) -> LlmAgent
    model            = config.REASONING_MODEL          # gemini-3.5-flash
    generate_content = temperature 0, max_output_tokens from config
    tools            = tools.build_tools(context, agent_id)   # allowlist only
    before/after     = guardrails.build_tool_guardrails(...)
    disallow_transfer_to_parent = True
    disallow_transfer_to_peers  = True
    sub_agents       = ()  except Change Intelligence’s optional search child

run_turn(agent, prompt, *, session_service, session_id)
    Runner(agent, app_name=config.APP_NAME, session_service=...)
    # default: InMemorySessionService, one session per *run* (not per stage)
    # later: DatabaseSessionService when a Patch turn must resume

configure_vertex(config) -> env vars google-genai actually reads
```

**Session rule.** One ADK session per remediation `run_id`. Specialists do not
share a chat history with each other (Verification must stay blind). They may
resume *their own* turn if the Runner is still up. Run status, attempts, and
idempotency stay in Postgres — never in ADK Memory Bank.

**Do not use**

| ADK surface | Why |
|---|---|
| `EnvironmentToolset` / `BashTool` / `ComputerUseToolset` | wrong names, 30s shell, no allowlist |
| `BuiltInCodeExecutor` / `GkeCodeExecutor` as Patch | bypasses our claim TTL + argv allowlist |
| `transfer_to_agent` | §9: the state machine picks the next stage |
| `LangchainTool` / `CrewaiTool` / `LlamaIndexRetrieval` | constraint 1 |
| `SkillToolset` (experimental) | we load `skills/<id>/` ourselves |
| ADK Memory Bank as workflow state | constraint 7 |

---

## 5. Shared vs granted tools

**Shared (every reasoning agent):** `record_human_required` only.

Everything else is a **grant** in `config.TOOL_ALLOWLISTS`. A tool that is not
granted is not constructed. The prompt is not the control.

### 5.1 Change Intelligence — corroborate, do not invent

| Tool | Kind | Notes |
|---|---|---|
| `list_provider_notices` | ours | feed index |
| `load_provider_notice` | ours | strip envelope, injection gate, Model Armor later |
| `normalize_provider_notice` | ours | deterministic parse |
| `record_change_manifest` | ours | must match the parse; conflicts → `HUMAN_REQUIRED` |
| `google_search` *(add)* | ADK `GoogleSearchTool` via a **search-only** `AgentTool` child | CI only. Hits are untrusted. Never replaces the pinned feed. Prefer `enterprise_web_search` if the demo must stay on Vertex enterprise grounding. |
| `url_context` *(optional)* | ADK, same child agent | only URLs already on the snapshot |

No `read_file`, no GitHub, no MCP filesystem.

### 5.2 Impact — judge the scan, do not produce the hits

| Tool | Kind | Notes |
|---|---|---|
| `scan_repository` | ours | **session-first** (GKE or local). Host `Path` only when `LocalSession.working_dir` is a real directory. Identifiers come from the manifest, not the Imagen-only watchlist. |
| `lookup_index_usages` *(add)* | ours | `repo_indexer.store.usages_for_project` — fleet-scale hint; scan still authoritative for the sandbox copy |
| `classify_repository_path` | ours | path-derived kind |
| `record_impact_report` | ours | findings = last scan, never the model’s list |

### 5.3 Policy — not a toolbox

Orchestrator:

```text
decision = packages.policy.evaluate(manifest, impact, rules)
persist PolicyDecision
if blocked → BLOCKED
if not auto_patch → HUMAN_REQUIRED
else → PATCHING
```

No `LlmAgent`. Optional later: Semantic Governance dry-run alongside.

### 5.4 Patch — the debug loop (§8.4)

| Tool | Kind | Bound by |
|---|---|---|
| `load_migration_skill` | ours | `skills/<id>/` on disk (Skill Registry later) |
| `read_file` / `list_dir` | ours | workspace root |
| `apply_patch` | ours | forbidden-path table, then `git apply` in the session |
| `run_command` | ours | `command_allowlist.py` argv shapes |
| `record_patch_plan` | ours | `files_expected` is the unexpected-change baseline |

Transport is `context.sandbox` (`LocalSession` or `GkeSession`). Claim lifetime:
`shutdownPolicy: Delete` + `shutdownTime` + `close()` in `finally`. Two
sandboxes per attempt when evidence lands: Patch’s working claim, orchestrator’s
clean claim (§13 / §8.5).

### 5.5 Verification — blind, read-only

| Tool | Kind | Notes |
|---|---|---|
| `list_verification_evidence` | ours | orchestrator-populated `evidence_root` |
| `read_verification_evidence` | ours | logs / diff / hashes only |
| `record_verification_report` | ours | unavailable live API → `INCONCLUSIVE`, never `PASS` |

Withheld: `PatchPlan`, inner-loop transcript, sandbox write, GitHub.

### 5.6 PR publisher — not a toolbox

After `verdict == PASS`, orchestrator calls `github_tools`
(`create_patch_branch`, `commit_verified_patch`, `open_pull_request`) with the
**approved bytes**. Render the body in Python (`pr_body.py`). No merge APIs.

---

## 6. How a specialist file looks after the rewrite

`specialists/patch.py` is identity + instruction. No ADK imports.

```python
AGENT = AgentId.PATCH
INSTRUCTION = """... debug loop ..."""

def build(context, trace):
    return adk.build_agent(AGENT, INSTRUCTION, context, trace)
```

`tools/patch/workspace.py` stays the four functions. ADK wraps them as
`FunctionTool` automatically when they appear on `LlmAgent.tools`.

---

## 7. Orchestrator after the rewrite

`Orchestrator` only:

1. `assert_transition` on `RunState`
2. open / close sandboxes (working vs evidence)
3. call `adk.run_turn` for the four agents
4. call `packages.policy` and `github_tools` itself
5. re-run build/test in the **evidence** session and write `evidence_root`
6. persist transitions to Postgres (once `0010` exists)

Deterministic slice (`PATCHAPI_PATCH_LOOP_DETERMINISTIC=1`) stays: no model,
same transitions, so isolation tests do not need Vertex.

Wire the missing stages in this order: `VERIFYING` (needs `evidence_root`) →
`PR_CREATING` (needs github_tools client) → control-plane trigger.

---

## 8. Phases (do not do this as one diff)

1. **Extract `adk.py`.** Move `build_specialist` + `run_turn` + Vertex env.
   Specialists become one-line wrappers. No behavior change. Smoke still PASS.
2. **Demote Policy and PR.** Orchestrator calls the Python gates. Delete the
   two `LlmAgent`s. Update `docs/agent-contracts.md`.
3. **Session-first Impact scan** as the only path (local Path is the session’s
   `working_dir`). Drop the host-only branch.
4. **Delete `environment.py`.** All exec goes through `sandbox.session`.
5. **CI search child** — `AgentTool` + `google_search`, grant on Change
   Intelligence only, still fail closed if it disagrees with the feed.
6. **`evidence_root` + `run_verification`.** Blind inputs only.
7. **`run_pr`** via github_tools HTTP, after PASS.
8. **One `session_service` per run**; optional `DatabaseSessionService` later.

Each phase keeps `scripts/smoke_patch_loop.py` green (deterministic + live).
GKE: `--sandbox gke --deterministic`, then assert `patchapi-sandbox-dev` is empty.

---

## 9. Inventory — what we are actually using

**ADK (runtime path)**

- `google.adk.agents.LlmAgent`
- `google.adk.runners.InMemoryRunner` (today) → `Runner` + explicit
  `InMemorySessionService` / later `DatabaseSessionService`
- `before_tool_callback` / `after_tool_callback`
- Function tools (plain Python callables on `LlmAgent.tools`)
- Planned: `GoogleSearchTool` / `GoogleSearchAgentTool` on CI only

**Our services (not ADK)**

| Service | Used by |
|---|---|
| `sandbox.session` (local / GKE claim) | Patch + orchestrator evidence |
| `packages.repo_scan` / `repo_indexer` | Impact |
| `packages.policy` | Policy stage |
| `packages.providers.google` | feed normalize, Vertex pins |
| `packages.schemas.*` | every `record_*` |
| `packages.memory` | institutional recall later; not run state |
| `services/github_tools` | PR publisher only |
| Model Armor (planned) | before CI sees provider text |
| Agent Gateway / SPIFFE (planned) | deny GitHub MCP to CI and Patch |

**Gemini**

- Agent reasoning: `gemini-3.5-flash` on Vertex `global`
- Live image check (Egaki evidence): `gemini-3.1-flash-image`, credential
  injected only for the orchestrator’s verify step

---

## 10. Definition of done

- Four `LlmAgent`s, zero Policy/PR agents.
- `grep -n 'import google.adk' agents` → `adk.py` only (inside functions).
- Grant table in `config.py` matches §5 of this file.
- `smoke_patch_loop.py` PASS local and GKE; namespace empty after GKE.
- Verification can fail a green build that deleted a test or collapsed the
  three Imagen IDs onto one model.
- A PR exists only after `VerificationReport.verdict == PASS`.
- No OpenCode, no LangChain, no `EnvironmentToolset`.
