# ADK human-in-the-loop for missing secrets — 2026-08-23

Scope: the Google-practice way for a PatchAPI ADK agent to pause with a structured
"needs you" signal when a required secret is missing (e.g. `GEMINI_API_KEY`) or
GCP is not connected, wait for the operator, then resume.

Read §0 first. Several ADK surfaces look like they solve this and do not.

## 0. Verification log

Fetched live on 2026-08-23 (primary sources only):

- https://google.github.io/adk-docs/tools-custom/function-tools/
- https://google.github.io/adk-docs/tools-custom/authentication/
- https://google.github.io/adk-docs/tools-custom/
- https://google.github.io/adk-docs/context/
- https://google.github.io/adk-docs/callbacks/
- https://google.github.io/adk-docs/callbacks/types-of-callbacks/
- https://google.github.io/adk-docs/callbacks/design-patterns-and-best-practices/
- https://google.github.io/adk-docs/plugins/
- https://google.github.io/adk-docs/safety/
- https://google.github.io/adk-docs/sessions/state/
- https://google.github.io/adk-docs/events/
- https://google.github.io/adk-docs/runtime/event-loop/
- https://google.github.io/adk-docs/runtime/resume/
- https://google.github.io/adk-docs/graphs/human-input/
- https://google.github.io/adk-docs/api-reference/python/google-adk.html
- https://adk.dev/tools-custom/function-tools/
- https://adk.dev/tools-custom/authentication/
- https://github.com/google/adk-python/tree/main/contributing/samples/human_in_loop
- https://github.com/google/adk-python/tree/main/contributing/samples/hitl/tool_confirmation
- https://developers.googleblog.com/build-long-running-ai-agents-that-pause-resume-and-never-lose-context-with-adk/
- https://discuss.google.dev/t/how-to-force-an-agent-loop-to-wait-for-user-input-human-in-the-loop/320876
- https://docs.cloud.google.com/run/docs/configuring/services/secrets
- https://cloud.google.com/run/docs/configuring/jobs/secrets
- https://cloud.google.com/secret-manager/docs/access-secret-version
- https://cloud.google.com/secret-manager/docs/authentication
- https://cloud.google.com/docs/authentication/application-default-credentials
- https://docs.cloud.google.com/model-armor/model-armor-vertex-integration
- https://docs.cloud.google.com/model-armor/model-armor-agent-gateway-integration
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/configure-model-armor
- https://raw.githubusercontent.com/google/adk-docs/refs/heads/main/examples/python/snippets/tools/function-tools/human_in_the_loop.py

Inspected on this machine (works-here evidence, not documentation):

| Check | Result |
|---|---|
| `uv run python -c "importlib.metadata.version('google-adk')"` | `google-adk==2.1.0` |
| `google-genai` | `1.75.0` |
| `google.adk.tools.LongRunningFunctionTool.__init__` | `(self, func: Callable)` — sets `self.is_long_running = True` |
| `google.adk.tools.FunctionTool.__init__` | `(self, func, *, require_confirmation: bool \| Callable[..., bool] = False)` |
| `ToolContext` | alias of `google.adk.agents.context.Context` |
| `Context.request_confirmation(*, hint=None, payload=None)` | writes `EventActions.requested_tool_confirmations[function_call_id]` |
| `Context.request_credential(auth_config)` | writes `EventActions.requested_auth_configs[function_call_id]` |
| Special function-call names | `adk_request_confirmation`, `adk_request_credential`, `adk_request_input` |
| `google.adk.events.RequestInput` | `interrupt_id`, `payload`, `message`, `response_schema` |
| `google.adk.apps.App` | fields `name`, `root_agent`, `plugins`, `resumability_config` |
| `ResumabilityConfig` | `@experimental`; `is_resumable: bool = False`; at-least-once tool resume |
| `google.adk.tools.get_user_choice` | official sample tool: `LongRunningFunctionTool` that returns `None` |

**Not verified:** no live `runner.run_async` HITL pause, no Agent Runtime deploy, no Secret Manager write. Claims about runtime pause/resume behaviour are documentation plus installed-package source, not an observed end-to-end result.

## 1. What this use case actually is

PatchAPI already has three different "needs a human" ideas. They must not collapse into one ADK API.

| Signal | Owner today | Resumable? | Meaning |
|---|---|---|---|
| `RunState.HUMAN_REQUIRED` | Postgres state machine (`packages/schemas/run_state.py`) | **No** — terminal, empty outgoing set | Policy / verification fail-closed. Analysis-only. Roadmap §9: `HUMAN_REQUIRED --> [*]` |
| `record_human_required` | Shared ADK function tool (`agents/tools/shared.py`) | No | Specialist cannot proceed honestly. Orchestrator advances to terminal `HUMAN_REQUIRED` |
| UI / notifications "This run is waiting on you. Connect GCP or add GEMINI_API_KEY…" | Mock runs + `packages/state/notifications.py` (`RUN_WAITING_KEY`) | **Yes, in the mock** — path continues `HUMAN_REQUIRED → PATCHING` | Operator setup, not a policy verdict |

The mocked banner is **not** the same event as policy `HUMAN_REQUIRED`. Overloading the terminal state is the first anti-pattern.

Google's own long-running-agent writeup (2026-08, Developers Blog) is the closest official architecture: persist a checkpoint, sleep through idle time, wake the same session with a `state_delta` when the external event arrives. That is a **state machine + session**, not "ask the model to wait."

## 2. Exact ADK APIs that exist (2.1.0)

Four official pause/resume surfaces. Only one is a good fit for "missing secret," and even that one is a *mid-turn* mechanism, not the outer run loop.

### 2.1 `LongRunningFunctionTool` — the HITL tool for `LlmAgent`

**Docs:** https://google.github.io/adk-docs/tools-custom/function-tools/  
**Sample:** https://github.com/google/adk-python/tree/main/contributing/samples/human_in_loop  
**Snippet:** https://raw.githubusercontent.com/google/adk-docs/refs/heads/main/examples/python/snippets/tools/function-tools/human_in_the_loop.py  
**Package:** `google.adk.tools.long_running_tool.LongRunningFunctionTool`  
**Export:** `from google.adk.tools import LongRunningFunctionTool`

```python
class LongRunningFunctionTool(FunctionTool):
    def __init__(self, func: Callable):
        super().__init__(func)
        self.is_long_running = True
```

Documented behaviour (function-tools page, fetched 2026-08-23):

1. The model calls the tool.
2. The function returns immediately — typically `{"status": "pending", "ticket_id": "..."}`.
3. The `Runner` **pauses the agent run** and yields an `Event` whose `long_running_tool_ids` contains that function-call id.
4. The **agent client** (our control API, not the model) waits for the external / human action.
5. The client resumes by sending a `types.Content(role="user")` whose part is a `types.FunctionResponse` with the **same `id` and `name`** as the original `FunctionCall`.
6. If the app is configured with Resume (`ResumabilityConfig.is_resumable=True`), the resume call must also pass the original `invocation_id`. Otherwise ADK starts a new invocation.

Official Python resume shape (docs + sample):

```python
from google.adk.tools import LongRunningFunctionTool
from google.genai import types

updated = types.Content(
    role="user",
    parts=[
        types.Part(
            function_response=types.FunctionResponse(
                id=original_function_call.id,   # required
                name=original_function_call.name,
                response={"status": "approved"},  # or secret-ready payload
            )
        )
    ],
)
async for event in runner.run_async(
    user_id=user_id,
    session_id=session.id,
    new_message=updated,
    # only if App.resumability_config.is_resumable:
    # invocation_id=paused_invocation_id,
):
    ...
```

`Event.long_running_tool_ids: set[str] | None` is the client-side detector. Installed source (`google.adk.events.event.Event`): "Agent client will know from this field about which function call is long running. only valid for function call event."

The official built-in example of this pattern is `google.adk.tools.get_user_choice`:

```python
# google/adk/tools/get_user_choice_tool.py (2.1.0)
def get_user_choice(options: list[str], tool_context: ToolContext) -> Optional[str]:
    """Provides the options to the user and asks them to choose one."""
    tool_context.actions.skip_summarization = True
    return None

get_user_choice_tool = LongRunningFunctionTool(func=get_user_choice)
```

That is Google's "ask the user" tool: wrap a function, return pending/`None`, let the client complete the `FunctionResponse`.

### 2.2 Tool confirmation — yes/no approval, not "paste a key"

**Docs:** https://google.github.io/adk-docs/graphs/human-input/ (section "Tool-confirmation")  
**Sample:** https://github.com/google/adk-python/tree/main/contributing/samples/hitl/tool_confirmation  
**Package:** `google.adk.tools.function_tool.FunctionTool`, `google.adk.tools.tool_confirmation.ToolConfirmation`

Two ways:

```python
# Static: framework pauses before the function body runs.
FunctionTool(func=close_account, require_confirmation=True)
# require_confirmation may also be Callable[..., bool]

# Dynamic: inside the tool, after inspecting args.
tool_context.request_confirmation(
    hint="Approve transfer of $500 to acct-9?",
    payload={"amount": 500, "recipient": "acct-9"},
)
return {"error": "This tool call requires confirmation, please approve or reject."}
```

Installed signatures (2.1.0):

```text
FunctionTool.__init__(self, func, *, require_confirmation: bool | Callable[..., bool] = False)

Context.request_confirmation(*, hint: str | None = None, payload: Any | None = None) -> None
# requires function_call_id
# writes EventActions.requested_tool_confirmations[function_call_id] = ToolConfirmation(...)

class ToolConfirmation:  # @experimental(FeatureName.TOOL_CONFIRMATION)
    hint: str = ""
    confirmed: bool = False
    payload: Optional[Any] = None
```

The framework emits a function call named **`adk_request_confirmation`** (`REQUEST_CONFIRMATION_FUNCTION_CALL_NAME` in `google.adk.flows.llm_flows.functions`). The client replies with a `FunctionResponse` for that id carrying `{"confirmed": true}` (or the `ToolConfirmation` dump). ADK then **re-invokes the original tool** with `tool_context.tool_confirmation` populated.

This is the right API for "may I close the account / transfer funds / open a PR?" It is the **wrong** API for "the key is missing." Confirmation is boolean approval of a tool the model already chose. A missing secret is a **precondition**, not an approval.

### 2.3 `request_credential` — OAuth / API-key collection for a *tool*

**Docs:** https://google.github.io/adk-docs/tools-custom/authentication/  
**Context page:** https://google.github.io/adk-docs/context/  
**Package:** `google.adk.auth.auth_tool.AuthConfig`, `google.adk.auth.AuthCredential`, `AuthCredentialTypes`

```python
from google.adk.auth import AuthConfig, AuthCredential, AuthCredentialTypes
from google.adk.tools import ToolContext

def call_vendor(query: str, tool_context: ToolContext) -> dict:
    cached = tool_context.get_auth_response(AuthConfig(...))
    if cached:
        return do_call(cached)
    tool_context.request_credential(AuthConfig(
        auth_scheme=auth_scheme,
        raw_auth_credential=auth_credential,
    ))
    return {"pending": True, "message": "Awaiting user authentication."}
```

Installed types:

```text
AuthCredentialTypes: API_KEY='apiKey' | HTTP='http' | OAUTH2='oauth2'
                     | OPEN_ID_CONNECT='openIdConnect' | SERVICE_ACCOUNT='serviceAccount'

class AuthConfig:
    auth_scheme: AuthScheme
    raw_auth_credential: AuthCredential | None
    exchanged_auth_credential: AuthCredential | None
    credential_key: ...

Context.request_credential(auth_config: AuthConfig) -> None
Context.get_auth_response(auth_config) -> AuthCredential | None
Context.load_credential(auth_config) / save_credential(auth_config)
```

Client detects `part.function_call.name == "adk_request_credential"` **and** `part.function_call.id in event.long_running_tool_ids`. Resume is a `FunctionResponse` named **`adk_request_credential`** whose `response` is the updated `AuthConfig.model_dump()`. ADK then exchanges tokens and **retries the original tool**.

Official warning on that same page (fetched 2026-08-23):

> Storing sensitive credentials such as access tokens and especially refresh tokens directly in the session state can pose security risks… For production… use a secrets manager… Google Cloud Secret Manager.

And: for API keys / client secrets in production, "use a secrets manager," not `.env` and not `InMemorySessionService`.

`request_credential` is the right API when a **tool** needs the *operator's* OAuth consent (Calendar, a customer SaaS). It is the wrong API for PatchAPI's platform verifier key:

- `GEMINI_API_KEY` is not an OAuth redirect. There is no `auth_uri`.
- The Gemini / Vertex call is made by ADK itself (`LlmAgent.model`), not by a `FunctionTool` we wrap in `AuthConfig`.
- Putting the key into `tool_context.state` after `get_auth_response` is exactly the storage pattern Google warns against.
- Connect-GCP is a service-account JSON we already vault in Secret Manager (`packages/state/gcp_connections.py`). ADK `SERVICE_ACCOUNT` auth is for *calling an OpenAPI tool as that SA*, not for "the operator uploaded a viewer key."

### 2.4 Graph `RequestInput` — ADK Workflow HITL node (Python v2.0+)

**Docs:** https://google.github.io/adk-docs/graphs/human-input/  
**Package:** `google.adk.events.RequestInput`, `google.adk.Workflow`

```python
from google.adk.events import RequestInput
from google.adk import Workflow

def ask_for_key():
    yield RequestInput(
        message="Add GEMINI_API_KEY so the agent can continue.",
        payload={"need": "secret", "secret_name": "GEMINI_API_KEY"},
        response_schema=str,
    )

root_agent = Workflow(name="root_agent", edges=[("START", ask_for_key, next_step)])
```

Installed `RequestInput` fields: `interrupt_id: str` (uuid default), `payload`, `message`, `response_schema`.

The framework emits **`adk_request_input`**. This is the cleanest *graph* HITL. It is **not** how PatchAPI orchestrates. Roadmap §9 and `agents/orchestrator.py` are a Postgres table, not `google.adk.Workflow`. Do not introduce a Workflow graph just to pause for a secret — that would move orchestration out of the state machine and into an LLM/graph, which the competition spec forbids.

### 2.5 App-level resume (crash / long-running, not HITL by itself)

**Docs:** https://google.github.io/adk-docs/runtime/resume/  
**Package:** `google.adk.apps.App`, `google.adk.apps._configs.ResumabilityConfig` (`@experimental`)

```python
app = App(
    name="patchapi-fleet",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
# later
async for event in runner.run_async(
    user_id=..., session_id=..., invocation_id="invocation-123"
):
    ...
```

Installed docstring: pause on a long-running function call; resume from the last event; **at-least-once** tool execution; temp/`in-memory` state is lost. Tools that must not double-fire (purchases, PR open) must be idempotent.

Resume is complementary to §2.1. It does not invent a "needs you" signal. It only lets the same invocation continue after the client supplies the `FunctionResponse` (or after a crash).

### 2.6 Callbacks and plugins — detect, do not wait

**Docs:**  
- https://google.github.io/adk-docs/callbacks/  
- https://google.github.io/adk-docs/callbacks/types-of-callbacks/  
- https://google.github.io/adk-docs/plugins/  
- https://google.github.io/adk-docs/safety/

Python callback parameter names are **keyword-only contracts**. Wrong names raise `TypeError`. PatchAPI already follows this in `agents/guardrails.py`.

| Hook | Required names | Return to short-circuit |
|---|---|---|
| `before_agent_callback` | `callback_context` | `types.Content` |
| `after_agent_callback` | `callback_context` | `types.Content` |
| `before_model_callback` | `callback_context`, `llm_request` | `LlmResponse` |
| `after_model_callback` | `callback_context`, `llm_response` | `LlmResponse` |
| `before_tool_callback` | `tool`, `args`, `tool_context` | `dict` (becomes the tool result; function is skipped) |
| `after_tool_callback` | `tool`, `args`, `tool_context`, `tool_response` | `dict` (replaces the result) |
| `on_tool_error_callback` | `tool`, `args`, `tool_context`, `error` | `dict` |

`BasePlugin` (runner-global, **runs before** agent-level callbacks) adds:

- `on_user_message_callback(*, invocation_context, user_message)`
- `before_run_callback(*, invocation_context)` — returning content **halts the runner**
- `on_event_callback` / `after_run_callback`
- the same agent / model / tool / error hooks

Official safety page: plugins are the recommended place for **cross-agent** guardrails. That is the right hook to *refuse a tool* or *skip a model call* when a secret is missing. It is not a wait. A plugin that returns a dict from `before_tool_callback` skips the tool and hands the dict to the model — the invocation continues. A plugin that returns from `before_run_callback` ends the run. Neither parks a run for hours.

`before_tool_callback` *may* call `tool_context.request_credential(...)` (callbacks design-patterns page). That still ends in the §2.3 client protocol, not in a Postgres pause.

### 2.7 Session / state / events (how a pause is persisted *inside* ADK)

**Docs:** https://google.github.io/adk-docs/sessions/state/ · https://google.github.io/adk-docs/events/ · https://google.github.io/adk-docs/runtime/event-loop/ · https://google.github.io/adk-docs/context/

| Type | Role |
|---|---|
| `Session` | `state` dict + `events` history. Managed only by `SessionService`. |
| `InvocationContext` | One `run_async` / `run_live` call. Fields include `session`, `invocation_id`, `end_invocation`, services. |
| `ToolContext` / `Context` | Injected into tools by **type**, not by name. `state` writes become `EventActions.state_delta`. |
| `Event` | `invocation_id`, `author`, `actions`, `long_running_tool_ids`, `content` |
| `EventActions` (2.1.0 fields) | `skip_summarization`, `state_delta`, `artifact_delta`, `transfer_to_agent`, `escalate`, `requested_auth_configs`, `requested_tool_confirmations`, `end_of_agent`, `agent_state`, … |

Rule from the state page: **never assign `session.state[...]` on a Session you loaded yourself.** Write through `tool_context.state` / `callback_context.state` so the `SessionService.append_event` path commits the delta.

Prefixes with a persistent `SessionService`: `app:`, `user:`, `temp:` (invocation-only). PatchAPI currently uses `InMemorySessionService` per run (`agents/adk.py:new_session_service`). That dies when the process exits. A secret-wait that outlives a Cloud Run instance **cannot** live only in that session.

Official production session backends (same docs family, not re-fetched as a dedicated page this pass): `DatabaseSessionService`, `VertexAiSessionService` (Agent Runtime Sessions). Roadmap already names Agent Platform Sessions as the institutional short-term store. Postgres remains the **run-state** authority (CLAUDE.md constraint 7).

## 3. What Google says *not* to do

From the pages above, plus the Dev Forum answer on forcing a loop to wait (https://discuss.google.dev/t/how-to-force-an-agent-loop-to-wait-for-user-input-human-in-the-loop/320876):

1. **Do not "wait" by prompting the model harder.** A text question does not suspend the runner. The next loop iteration starts immediately.
2. **Do not put HITL inside `LoopAgent` as another LLM turn.** Use `RequestInput` (graph) or `LongRunningFunctionTool` (LLM agent), then end the invocation.
3. **Do not store API keys / refresh tokens in `session.state`.** Authentication page, in bold. Secret Manager (or an auth manager) is the production store.
4. **Do not use LangGraph `interrupt_before` on Agent Engine.** Official Agent Engine HITL notebook is LangGraph. Competition constraint 1: ADK only. That notebook is a forbidden path, not a template.
5. **Do not treat Model Armor as HITL.** Model Armor screens prompts/responses (prompt injection, SDP). It blocks or inspects. It does not pause for a secret. Ingress sanitization for ADK on Agent Runtime is `reasoningEngines.streamQuery` only (Agent Gateway + Model Armor docs, 2026).
6. **Do not resume a mutated graph.** Resume docs: "Do not modify a stopped agent workflow before resuming it."
7. **Do not assume resume is exactly-once.** `ResumabilityConfig` is at-least-once. `record_*` and Secret Manager writes must stay idempotent (PatchAPI already keys notifications on `dedupe_key`).
8. **Do not inject customer project secrets as Cloud Run env `latest`.** Cloud Run secrets page: env vars resolve at instance start; pin a version. Volume mounts re-read Secret Manager (better for rotation). Customer `GEMINI_API_KEY` is per-project in *our* Secret Manager (`project_secrets`), not a Cloud Run service env.

## 4. Secret Manager + ADC + Cloud Run (the actual secret path)

**Cloud Run services:** https://docs.cloud.google.com/run/docs/configuring/services/secrets  
**Access API:** https://cloud.google.com/secret-manager/docs/access-secret-version  
**ADC search order:** https://cloud.google.com/docs/authentication/application-default-credentials

Google's production pattern, in order:

1. **Platform identity = attached service account + ADC.** On Cloud Run, do not set `GOOGLE_APPLICATION_CREDENTIALS` to a JSON key. ADC step 3 (metadata server) is the documented production method.
2. **IAM:** Cloud Run runtime SA needs `roles/secretmanager.secretAccessor` on each secret (or a folder/project IAM grant). Missing this is a documented Cloud Run startup failure mode.
3. **Two injection styles:**
   - Volume mount — Cloud Run fetches current Secret Manager value on read. Preferred for rotation.
   - Env var — resolved at instance start. Pin `VERSION`, do not use `latest` in production.
4. **Client access** (what PatchAPI already does in `packages/state/secret_manager.py`):

```python
from google.cloud import secretmanager
client = secretmanager.SecretManagerServiceClient()  # ADC
name = f"projects/{project}/secrets/{secret_id}/versions/{version}"
response = client.access_secret_version(request={"name": name})
payload = response.payload.data.decode("utf-8")
```

5. **Never return the payload over HTTP.** PatchAPI `project_routes.py` already lists names + `secret_arn` only. Keep that boundary.

Split of secrets for this product:

| Secret | Where it lives | Who reads it | HITL? |
|---|---|---|---|
| `patchapi-database-url`, session, GitHub App PEM | Terraform Secret Manager → Cloud Run `--set-secrets` | Control API process | No — platform |
| Customer `GEMINI_API_KEY` / `GOOGLE_API_KEY` / `GOOGLE_GENERATIVE_AI_API_KEY` | `project_secrets` row + Secret Manager (`packages/state/secrets.py`) | Verifier / live Gemini call | **Yes — operator** |
| Customer GCP viewer SA JSON | `gcp_connections` row + Secret Manager | Inspector / live-verify broker | **Yes — operator** |
| Vertex ADC for *our* Agent Runtime | Cloud Run attached SA | ADK `LlmAgent` | No — platform |

`packages/state/notifications.py` already encodes the operator condition:

```sql
EXISTS (project_change_findings.status = 'needs_you')
AND NOT EXISTS (project_secrets.secret_name IN GEMINI_API_KEY | GOOGLE_API_KEY | GOOGLE_GENERATIVE_AI_API_KEY)
AND NOT EXISTS (gcp_connections)
```

That query is the correct **detector**. It does not need an LLM.

## 5. Recommended architecture for PatchAPI

Keep the Google split: **deterministic outer loop, ADK only inside a specialist turn.**

```
                    Postgres run-state (authority)
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
    gate: secrets?      ADK Runner            gate: policy
    (Python)            (one specialist)      (Python)
         │                    │                    │
    missing ──► PAUSED /      │              HUMAN_REQUIRED
    NEEDS_YOU     │           │              (terminal)
         │        │      LongRunningFunctionTool
         │        │      only if already in a turn
         ▼        ▼
    Secrets tab / Connect GCP
         │
         ▼
    Secret Manager write + pointer
         │
         ▼
    resume orchestrator from saved stage
    (new ADK invocation, same run_id)
```

### 5.1 Detect (do this in Python, before `run_async`)

Add a `RuntimeNeed` check in the orchestrator / control-API worker, **not** in an `LlmAgent` instruction.

```text
need = None
if not project_has_verifier_key(project_id):   # names in _VERIFIER_SECRET_NAMES
    need = "secret"
elif not project_has_gcp_connection(project_id) and stage_requires_gcp(stage):
    need = "gcp"
```

If `need` is set: **do not construct `LlmAgent`, do not call Vertex.** Persist the pause. Emit the notification (`RUN_WAITING_KEY` already exists). Return the run to the dashboard.

This matches the official forum guidance: write durable `needs_user_input` state, end the invocation, resume when the human replies. It also matches the Developers Blog onboarding agent: the model is not in a spin-wait.

`before_run_callback` / `before_model_callback` on a plugin is a *second* fence if someone calls `run_turn` anyway. Returning content from `before_run_callback` halts that runner. It is defense in depth, not the system of record.

### 5.2 Persist a *resumable* pause — do not reuse terminal `HUMAN_REQUIRED`

`RunState.HUMAN_REQUIRED` is terminal by design (roadmap §9, `ALLOWED_RUN_STATE_TRANSITIONS[HUMAN_REQUIRED] = {}`). Policy "analysis only" and verification "INCONCLUSIVE" belong there.

The secret/GCP banner is a **hold**. Recommended (pick one, do not invent both):

**Option A (preferred, smallest spec change):** add `RunState.WAITING_ON_OPERATOR` (or `PAUSED`) that is **non-terminal**, with edges:

```text
{POLICY_EVALUATION, PATCHING, BUILDING, TESTING, VERIFYING, PR_CREATING}
    → WAITING_ON_OPERATOR
WAITING_ON_OPERATOR → {same stage, or PATCHING if the hold was pre-patch}
WAITING_ON_OPERATOR → FAILED
```

Store on the run row (or a `run_holds` table):

```json
{
  "hold_kind": "runtime_secret",
  "need": "secret" | "gcp",
  "secret_names": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"],
  "paused_from": "PATCHING",
  "adk_session_id": "run-uuid:patch",
  "adk_invocation_id": null,
  "function_call_id": null
}
```

`adk_*` ids are null when we paused *before* a turn. They are filled only for §5.3.

**Option B:** keep `HUMAN_REQUIRED` terminal for policy, and drive the banner only from `project_notifications` + finding status, without a run-state change. Weaker: the Runs panel already maps `HUMAN_REQUIRED` → "Needs you" and the mock path continues to `PATCHING`, which the real state machine forbids.

Do not make `HUMAN_REQUIRED` non-terminal without updating roadmap §9, `TERMINAL_RUN_STATES`, policy schema (`human_review_required`), and every test that treats it as an end.

### 5.3 Mid-turn pause (only if a tool discovers the gap after the model has started)

If Patch is already inside `run_turn` and a sandbox / live-verify tool finds the key missing:

1. Implement `ensure_runtime_credentials(...)` as a **`LongRunningFunctionTool`**.
2. The function writes the hold row (Postgres) and returns `{"status": "pending", "need": "secret", "hold_id": "..."}`.
3. `run_turn` must detect `event.long_running_tool_ids`, stop iterating, persist `function_call_id` + `invocation_id` + `session_id` on the run, and leave ADK.
4. Do **not** ask the model to call `record_human_required` for this case. That tool means "stop forever."

Resume of a mid-turn pause (Google client protocol):

```python
async for event in runner.run_async(
    user_id=user_id,
    session_id=saved.adk_session_id,
    invocation_id=saved.adk_invocation_id,  # if App is resumable
    new_message=types.Content(
        role="user",
        parts=[types.Part(function_response=types.FunctionResponse(
            id=saved.function_call_id,
            name="ensure_runtime_credentials",
            response={"status": "ready", "need": saved.need},
        ))],
    ),
):
    ...
```

The FunctionResponse **must not include the secret value**. The tool, on resume, reads Secret Manager via the existing vault (ADC). Same as `get_auth_response` but our store, not ADK session state.

This path requires a persistent `SessionService` if Cloud Run may scale to zero during the wait. `InMemorySessionService` cannot survive that. Until Agent Runtime Sessions are wired, treat mid-turn HITL as **out of scope** and only pause *between* orchestrator stages (§5.1). That is the honest hackathon cut.

### 5.4 Resume after the human acts

Existing write paths are the wake-up:

- `POST /{project_id}/secrets` → `upsert_secret` → Secret Manager + `project_secrets`
- `POST /{project_id}/gcp-connections` → `upsert_owned_gcp_connection`

After a successful upsert, the control API should:

1. Re-run the detector. If still missing the other of `{secret, gcp}` and the hold asked for both, keep paused.
2. Dismiss `RUN_WAITING_KEY` (already have `_DISMISS_KEY_SQL`).
3. `assert_transition(WAITING_ON_OPERATOR, paused_from)` and continue the orchestrator from that stage.
4. If a mid-turn `function_call_id` is stored, complete §5.3 instead of restarting the specialist from scratch.

Do not pass the pasted key into the agent prompt or into `new_message` text.

### 5.5 What the ADK specialist still owns

`record_human_required` stays the fail-closed exit for **ambiguous migrations**, feed disagreement, missing GitHub tools, verification `INCONCLUSIVE`. Those remain terminal `HUMAN_REQUIRED`. The operator-setup hold is a different enum value and a different notification `dedupe_key`.

## 6. Concrete contracts

### 6.1 Tool (mid-turn only)

```text
Name:    ensure_runtime_credentials
Kind:    LongRunningFunctionTool
Grant:   SHARED_TOOLS (every specialist) — or only PATCH + VERIFICATION
Args:    need: Literal["secret", "gcp", "any"]
Returns: {
           "status": "pending" | "ready" | "unavailable",
           "need": "secret" | "gcp",
           "hold_id": "<uuid>",
           "message": "Connect GCP or add GEMINI_API_KEY so the agent can continue."
         }
Never:   the secret value, the SA JSON, a path under .secrets/
```

On first call: if the vault already has the key, return `ready` immediately (no pause). If not, persist hold + `pending`. On resume call (same session, FunctionResponse already applied): vault.reveal pointer only, return `ready` or `unavailable`.

### 6.2 Events (control plane, not ADK Event.author)

| Event | When | Payload (no secrets) |
|---|---|---|
| `run.hold.requested` | Detector or LRF tool parks the run | `run_id`, `need`, `paused_from`, `hold_kind=runtime_secret` |
| `run.hold.satisfied` | Secret or GCP upsert cleared the detector | `run_id`, `need`, `secret_name` or `connection_id` (ids only) |
| `run.hold.resumed` | Orchestrator left `WAITING_ON_OPERATOR` | `run_id`, `next_state` |

ADK-level events the client must recognise if mid-turn HITL is enabled:

| Detector | Meaning |
|---|---|
| `event.long_running_tool_ids` contains `part.function_call.id` | Pause; save ids |
| `part.function_call.name == "adk_request_confirmation"` | Yes/no UI (not this feature) |
| `part.function_call.name == "adk_request_credential"` | OAuth/API-key UI (not this feature) |
| `part.function_call.name == "adk_request_input"` | Graph HITL (not our orchestrator) |

### 6.3 State transitions (proposed)

```text
… → PATCHING
PATCHING → WAITING_ON_OPERATOR     # key missing before / during sandbox
WAITING_ON_OPERATOR → PATCHING     # key present; continue
WAITING_ON_OPERATOR → FAILED       # abandoned / timeout
VERIFYING → HUMAN_REQUIRED         # unchanged: inconclusive / needs a person
POLICY_EVALUATION → HUMAN_REQUIRED # unchanged: analysis-only
```

UI already has `need: "secret" | "gcp"` and `HUMAN_REQUIRED_PAUSE`. Point those at `WAITING_ON_OPERATOR`, not at policy `HUMAN_REQUIRED`.

## 7. Mapping onto what is already in the tree

| Existing piece | Keep | Change |
|---|---|---|
| `agents/tools/shared.py` `record_human_required` | Yes — fail-closed | Do not use it for missing `GEMINI_API_KEY` |
| `agents/guardrails.py` `before_tool` / `after_tool` | Yes — allowlist + trace | Optional plugin twin that refuses live-verify tools when the vault is empty |
| `agents/adk.py` `InMemorySessionService` | Fine for one-shot turns | Insufficient for mid-turn HITL across Cloud Run scale-to-zero |
| `packages/state/secrets.py` + Secret Manager | This **is** Google practice | Resume hook after upsert |
| `packages/state/gcp_connections.py` | Same | Resume hook after upsert |
| `packages/state/notifications.py` `RUN_WAITING_*` | Copy is correct | Tie dismiss/create to the new hold state |
| `RunState.HUMAN_REQUIRED` terminal | Yes for policy/verify | Do not reopen it for secrets |
| UI mock path `HUMAN_REQUIRED → PATCHING` | Shows the product intent | Needs a real non-terminal state or the mock is lying |
| Model Armor / Agent Gateway | Later governance | Not part of this pause |

## 8. Anti-patterns specific to this repo

1. Teaching the specialist "if Gemini fails, call `record_human_required` with the key name" and then treating that as resumable. The tool docstring says stop. The state machine says terminal.
2. Passing `GEMINI_API_KEY` into `LlmAgent` instruction or `new_message` so the model can "use it." The model never needs the raw key; the Vertex / google-genai client does, via env or ADC.
3. Wrapping the Gemini client in `request_credential(AuthConfig(API_KEY=...))` so ADK Web can pop an auth dialog. That stores the key in session state and fights Secret Manager.
4. `FunctionTool(..., require_confirmation=True)` on `ensure_runtime_credentials`. Confirmation is "approve this call," not "here is the key."
5. Introducing `google.adk.Workflow` + `RequestInput` as the fleet orchestrator. That replaces the Postgres machine.
6. Copying the Agent Engine LangGraph HITL notebook.
7. Using Model Armor floor settings as a substitute for a hold. A blocked prompt is not "waiting on you."
8. Cloud Run `--set-secrets=GEMINI_API_KEY=customer-secret:latest` for a multi-tenant project key. Wrong tenant boundary; pin + per-project vault.

## 9. Suggested implementation order (research only — not a build plan)

1. Split the enum: `WAITING_ON_OPERATOR` vs terminal `HUMAN_REQUIRED`. Update roadmap §9 in the same change.
2. Orchestrator gate before `run_turn` using the existing `_VERIFIER_READY_SQL` predicates.
3. Resume from `upsert_secret` / `upsert_owned_gcp_connection`.
4. Point the Runs banner + `RUN_WAITING_KEY` at the hold row.
5. Only then: persistent ADK `SessionService` + `LongRunningFunctionTool` for in-turn discovery. Optional `App(resumability_config=ResumabilityConfig(is_resumable=True))`.
6. Never enable ADK `request_credential` for this banner.

## 10. Package map (`google-adk==2.1.0`, this venv)

```text
google.adk.tools.FunctionTool
google.adk.tools.LongRunningFunctionTool
google.adk.tools.ToolContext          # = google.adk.agents.context.Context
google.adk.tools.tool_confirmation.ToolConfirmation
google.adk.tools.get_user_choice      # official LRF "ask user" sample tool
google.adk.events.Event               # long_running_tool_ids, actions
google.adk.events.EventActions        # requested_auth_configs, requested_tool_confirmations, state_delta
google.adk.events.RequestInput        # graph HITL
google.adk.auth.AuthConfig
google.adk.auth.AuthCredential
google.adk.auth.AuthCredentialTypes
google.adk.apps.App
google.adk.apps._configs.ResumabilityConfig   # @experimental
google.adk.plugins.base_plugin.BasePlugin
google.adk.runners.Runner
google.adk.sessions.in_memory_session_service.InMemorySessionService
google.adk.agents.LlmAgent            # before_tool_callback, after_tool_callback, …
google.adk.agents.InvocationContext
google.adk.flows.llm_flows.functions.REQUEST_CONFIRMATION_FUNCTION_CALL_NAME
                                     # = "adk_request_confirmation"
google.adk.flows.llm_flows.functions.REQUEST_EUC_FUNCTION_CALL_NAME
                                     # = "adk_request_credential"
google.adk.flows.llm_flows.functions.REQUEST_INPUT_FUNCTION_CALL_NAME
                                     # = "adk_request_input"
```

## 11. One-sentence answer

Google's practice for "the agent cannot continue until a human supplies a secret" is: **detect the gap in deterministic code, persist a checkpoint, end the invocation, store the secret in Secret Manager, then resume the same run with a new `runner.run_async` (or a `FunctionResponse` to a `LongRunningFunctionTool` if you paused mid-turn).** Do not use tool confirmation, do not use OAuth `request_credential` for `GEMINI_API_KEY`, do not ask Gemini to wait, and do not overload terminal `HUMAN_REQUIRED`.
