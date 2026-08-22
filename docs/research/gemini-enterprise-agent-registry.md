# Gemini Enterprise agent registration, versioning, CI/CD — 2026-08-22

Scope: how an ADK agent gets *registered, published, versioned, and continuously
updated* on the Gemini Enterprise Agent Platform, plus the current rules for ADK
built-in tools, grounding freshness, and agent observability.

Read the terminology section first. Google renamed most of this stack on
2026-04-22 and the old names still appear in URLs, SDK imports, and API resource
paths, so a search that "finds nothing" is usually a naming problem.

## 0. Verification log

Fetched live on 2026-08-22 (primary sources only):

- https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-registry
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/manage-revisions-and-traffic
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/deploy-an-agent
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/url-context
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-google-search
- https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-adk-agent
- https://docs.cloud.google.com/agent-registry/concepts
- https://docs.cloud.google.com/agent-registry/register-custom-adk-agents
- https://google.github.io/agents-cli/cli/
- https://google.github.io/agents-cli/guide/deployment/
- https://google.github.io/agents-cli/guide/cicd/
- https://google.github.io/agents-cli/reference/from-agent-starter-pack/
- https://raw.githubusercontent.com/google/adk-docs/main/docs/tools/limitations.md
- https://github.com/google-github-actions/auth
- https://github.com/GoogleCloudPlatform/agent-starter-pack/

Run on this machine (works-here evidence, not documentation):

| Command | Result |
|---|---|
| `uv run python -c "importlib.metadata.version(...)"` | `google-adk 2.1.0`, `google-genai 1.75.0`, `google-cloud-aiplatform` **not installed** |
| `uv run adk deploy --help` | subcommands `agent_engine`, `cloud_run`, `gke` |
| `uv run adk deploy agent_engine --help` | full flag list captured in §3.1 |
| `python -c "dir(google.adk.tools)"` | exports include `google_search`, `url_context`, `enterprise_web_search`, `VertexAiSearchTool`, `DiscoveryEngineSearchTool`, `ApiRegistry`, `google_maps_grounding` |
| `inspect.signature(GoogleSearchTool.__init__)` | `(*, bypass_multi_tools_limit: bool = False, model: str \| None = None)` |
| `gcloud version` | `540.0.0`, components dated `2025.09.23` |
| `gcloud agent-registry --help` | **`Invalid choice: 'agent-registry'`** — surface missing from this install; needs `gcloud components update` |

**Not verified:** no GCP API call, deploy, or registration was executed. Every
claim below about runtime behaviour is documentation, not an observed result.

## 1. Terminology (2026-04-22 rename)

| Old name | Current name | API resource / package (unchanged) |
|---|---|---|
| Vertex AI / Vertex AI Agent Builder | Gemini Enterprise Agent Platform | — |
| Vertex AI Agent Engine / Reasoning Engine | **Agent Runtime** | `projects/*/locations/*/reasoningEngines/*` |
| Agentspace | **Gemini Enterprise** (the employee-facing app) | `discoveryengine.googleapis.com` |
| — (new) | **Agent Registry** | `agentregistry.googleapis.com` |
| — (new) | **Agent Gateway** | `networkservices` agent gateways |
| Agent Starter Pack | **Agents CLI** (`agents-cli`) | PyPI `google-agents-cli` |

The rename is cosmetic at the API layer. `reasoningEngines` is still the resource
collection, `google-cloud-aiplatform` is still the Python package, and doc URLs
still contain `/vertex-ai/` and `/agentspace/` in places. `roadmap.md` §11 already
records this; nothing here contradicts it.

## 2. There are three different "registries". Do not conflate them.

This is the single most important finding. "Registering an ADK agent" means three
different things depending on which consumer you want.

### 2.1 Agent Runtime — the deployment, not a registry

`projects/PROJECT/locations/LOCATION/reasoningEngines/RESOURCE_ID`. GA. This is
where the code runs. Creating one is a deploy, not a publication. Nothing
discovers your agent because it exists here — but see §2.2, which ingests it.

### 2.2 Agent Registry — org-wide governance catalog (GA 2026-06-18)

`agentregistry.googleapis.com`. Confirmed GA on **2026-06-18** in the Agent
Platform release notes (same date as Agent Gateway GA and Agent Observability GA).
The `v1` API and client libraries for C#, Go, Java, Node.js, PHP, Python, and Ruby
are GA. Terraform support for it is GA. The Agent Registry **MCP server** and
**agent skill governance** are still Preview.

Resource model, from the key-concepts page:

- Write path is a single resource: **`Service`**. You create/update/delete a
  `Service` to register anything.
- Read path is projected, read-only: **`Agent`**, **`McpServer`**, **`Endpoint`**.
  You `Get`/`List`/`Search` those; you cannot write them.
- RPC surface on `google.cloud.agentregistry.v1.AgentRegistry`:
  `CreateService`, `GetService`, `ListServices`, `DeleteService`,
  `GetAgent`, `ListAgents`, `SearchAgents`,
  `GetMcpServer`, `ListMcpServers`, `SearchMcpServers`,
  `GetEndpoint`, `ListEndpoints`,
  `CreateBinding`, `GetBinding`, `ListBindings`, `FetchAvailableBindings`,
  `UpdateBinding`, `DeleteBinding`.

Two registration mechanisms:

- **Automatic**: supported Google Cloud AI runtimes are ingested with no action.
  Agent Runtime is explicitly named. Scoped to a single project — cross-project
  agents need manual registration.
- **Manual**: create a `Service` for custom, external, or cross-project components.

Identifiers are URNs, and the format encodes where the agent runs:

```text
Agent Runtime:  urn:agent:projects-NUM:projects:NUM:locations:REGION:reasoningEngines:AGENT_ID
Cloud Run:      urn:agent:projects-NUM:projects:NUM:locations:REGION:run:services:SERVICE_NAME
GKE:            urn:agent:projects-NUM:projects:NUM:locations:REGION:containers:CLUSTER:namespace:NS:deployment:DEP
Manual:         urn:agent:projects-NUM:projects:NUM:locations:REGION:agentregistry:AGENT_ID
```

The IAM principal is derived from the compute path, which is why the SPIFFE-style
string in `roadmap.md` §12 embeds `reasoningEngines/ENGINE_ID`:

```text
principal://agents.global.org-ORG_ID.system.id.goog/resources/aiplatform/projects/NUM/locations/REGION/reasoningEngines/ENGINE_ID
```

**A2A Agent Cards are the manual registration payload — for self-hosted agents.**
For an ADK agent you host yourself (Cloud Run, GKE, your own box), the documented
path is: serve an Agent Card at `/.well-known/agent-card.json`, save it locally,
then:

```bash
gcloud agent-registry services create AGENT_NAME \
  --project=PROJECT_ID \
  --location=LOCATION \
  --display-name="DISPLAY_NAME" \
  --agent-spec-type=a2a-agent-card \
  --agent-spec-content=agent-card.json
```

Spec file max size is **10 KB**. Agent Registry parses the card, projects a
read-only `Agent`, and indexes its A2A skills for search. Supported A2A spec
versions are **0.3 and 1.0**; 1.0 adds the `supportedInterfaces` array declaring
transport endpoints and protocol bindings. So: an Agent Card *is* the registration
mechanism for manual/self-hosted registration — it is *not* how an Agent
Runtime deployment registers, because that is automatic.

### 2.3 Gemini Enterprise app agents — the end-user gallery

Entirely separate API (`discoveryengine.googleapis.com`, `v1alpha`), and this is
what makes an agent appear to employees in the Gemini Enterprise web app. Resource
path:

```text
projects/PROJECT_ID/locations/global/collections/default_collection/engines/APP_ID/assistants/default_assistant/agents/AGENT_ID
```

Register with `POST` to
`https://ENDPOINT_LOCATION-discoveryengine.googleapis.com/v1alpha/.../agents`:

```json
{
  "displayName": "DISPLAY_NAME",
  "description": "DESCRIPTION",
  "icon": { "uri": "ICON_URI" },
  "adkAgentDefinition": {
    "provisionedReasoningEngine": {
      "reasoningEngine": "projects/PROJECT_ID/locations/RESOURCE_LOCATION/reasoningEngines/RESOURCE_ID"
    }
  },
  "authorizationConfig": {
    "toolAuthorizations": ["projects/PROJECT_NUMBER/locations/global/authorizations/AUTH_ID"]
  }
}
```

Notes that matter operationally:

- `ENDPOINT_LOCATION` is `us`, `eu`, or `global`. Agent Runtime region must be
  compatible with the app location or you get an error: `global` app accepts any
  region, `us` app accepts `us-*` only, `eu` app accepts `europe-*` only.
- `description` is **not cosmetic** — the orchestrating LLM uses it to decide
  whether to route a user query to your agent. It is effectively a tool
  description.
- Update is `PATCH` on the agent resource name; `displayName` and `description`
  are required on update, and `reasoningEngine` is the field you repoint.
- List / get / delete are plain `GET`/`GET`/`DELETE` on the same paths. Delete
  returns an LRO.
- Requires `roles/discoveryengine.admin` (Gemini Enterprise Admin) and the
  Discovery Engine API enabled.
- Console equivalent: Gemini Enterprise → app → Agents → Add agent → **Custom
  agent via Agent Runtime**. A full UI flow now exists; curl is no longer the
  only path.
- Optional end-user OAuth uses a separate `authorizations` resource with a fixed
  redirect URI `https://vertexaisearch.cloud.google.com/static/oauth/oauth.html`.

There is no "Agent Designer" resource in the API surface I could find. Low-code
authoring is **Agent Studio** / **Agent Designer** in the console; it is not a
registration mechanism for code-first ADK agents. Do not build against it.

## 3. Versioning: real, but Preview and `v1beta1` only

Agent revisions and traffic splitting went **public preview on 2026-05-19** and
the docs state plainly: *"At this time, revisions and traffic splitting are
available through the v1beta1 API."* Treat as Preview, not GA.

Semantics:

- A **revision** is an immutable snapshot, auto-created when you update a
  *versioned* field. Always enabled; nothing to turn on.
- States: `ACTIVE` (queryable) and `DEPRECATED` (not queryable).
- Resource: `.../reasoningEngines/RESOURCE_ID/runtimeRevisions/REVISION_ID`.

**Versioned fields** (updating any of these mints a new revision):

- `PackageSpec`: `pickleObjectGcsUri`, `dependencyFilesGcsUri`,
  `requirementsGcsUri`, `pythonVersion`
- `DeploymentSpec`: `env[]`, `secretEnv[]`, `firstPartyImageOverride`,
  `agentServerMode`, `pscInterfaceConfig`, `minInstances`, `maxInstances`,
  `resourceLimits`, `containerConcurrency`, `classMethods[]`, `agentFramework`
- `SourceCodeSpec`: `source`, `languageSpec`
- `identityType`, `agentCard[]`

Everything else is unversioned and applies across all revisions — including
`trafficConfig`, which is why retargeting traffic ships no code.

Traffic control, `PATCH .../reasoningEngines/RESOURCE_ID?update_mask=traffic_config`
on `https://LOCATION-aiplatform.googleapis.com/v1beta1`:

```json
{ "trafficConfig": { "trafficSplitAlwaysLatest": {} } }
```

```json
{
  "trafficConfig": {
    "trafficSplitManual": {
      "targets": [
        { "runtimeRevisionName": ".../runtimeRevisions/REV_1", "percent": 90 },
        { "runtimeRevisionName": ".../runtimeRevisions/REV_2", "percent": 10 }
      ]
    }
  }
}
```

Percentages are integers and must sum to 100. Default mode is always-latest.
SDK equivalents, all requiring `HttpOptions(api_version="v1beta1")`:
`client.agent_engines.runtimes.revisions.list/get/delete(...)`, and
`client.agent_engines.update(name=..., config={"traffic_config": {...}})`.

Rollback is **repointing traffic**, not a rollback verb. There is no
`rollback` method and no named aliases (no "prod"/"canary" labels). You keep
revision resource names yourself. Only queries to the root `reasoningEngine`
undergo splitting; `runtimeRevisions/REV:query` bypasses the split entirely,
which is the clean way to smoke-test a new revision before shifting traffic.

Two limitations worth internalising:

1. **Agent Gateway is incompatible with revisions.** Documented: *"Agent Gateway
   isn't supported for Agent Runtime agents that are using revisions. You won't be
   able to use versioning-related features such as traffic split configuration and
   per-revision querying if an Agent Gateway is attached to an agent's
   configuration."* This directly conflicts with `roadmap.md` §12, which makes
   Agent Gateway load-bearing ("remove it and the security demo dies"). **We
   cannot have both Agent Gateway and traffic splitting on the same agent.**
2. A manual split keeps every targeted revision warm, so `minInstances` must be
   at least the number of revisions in the split. A community write-up on
   discuss.google.dev reports the split otherwise fails with an opaque
   `code 13 INTERNAL`. Not in the official docs — treat as a field report.

Also relevant: `Agent Registry` **skill** revisions exist as a separate concept
(immutable versioned snapshots of a skill package, with a default-version
pointer), and skill governance is Preview.

### 3.1 `adk deploy agent_engine` — verified local surface

`adk deploy` offers `agent_engine`, `cloud_run`, and `gke`. Relevant
`agent_engine` flags on installed `google-adk 2.1.0`:

| Flag | Note |
|---|---|
| `--project`, `--region` | override `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` |
| `--agent_engine_id` | **create-or-update**: omit to create, pass the resource ID to update an existing engine |
| `--display_name`, `--description` | Agent Engine metadata |
| `--adk_app` | Python file defining the app, default `agent_engine_app.py` |
| `--adk_app_object` | `root_agent` or `app` only, default `root_agent` |
| `--requirements_file`, `--env_file` | default to the agent directory's files |
| `--agent_engine_config_file` | `.agent_engine_config.json`; flags override its values |
| `--trace_to_cloud` / `--no-trace_to_cloud` | Cloud Trace |
| `--otel_to_cloud` | OpenTelemetry export |
| `--validate-agent-import` / `--skip-agent-import-validation` | import check; **skip is the default** |
| `--staging_bucket` | **deprecated — "no longer required or used"** |
| `--absolutize_imports` | deprecated |

The deprecation of `--staging_bucket` matters: `roadmap.md` §6 still passes
`"staging_bucket": f"gs://{STAGING_BUCKET}"` in the SDK create config. Harmless
but stale.

Updating an existing engine via `--agent_engine_id` is what mints a new revision
when versioned fields change (§3). So `adk deploy agent_engine --agent_engine_id`
in CI is already a revision-producing operation, without any extra work.

## 4. CI/CD from GitHub

### 4.1 There is no official GitHub Action for Agent Engine / Agent Runtime deploy

Searched and could not find one. The Google-maintained action set
(`google-github-actions/*`) covers auth, `gcloud` setup, GKE credentials,
Cloud Run deploy, and similar — **not** Agent Runtime. Every real-world example
found is `google-github-actions/auth` followed by a hand-rolled `run:` step
invoking `adk deploy`, `agents-cli deploy`, or a Python script. If a worker
claims an official Agent Engine action exists, that claim is wrong as of today.

Keyless auth is the documented pattern, and `google-github-actions/auth` is at
**`@v3`**. Both Direct WIF (omit `service_account`) and WIF-through-a-service-account
(pass `service_account`) are supported. The job needs:

```yaml
permissions:
  contents: read
  id-token: write
```

### 4.2 Google's own scaffolding: `agents-cli`, not Agent Starter Pack

**Agent Starter Pack is in maintenance mode.** Its GitHub README says active
development moved to `agents-cli` (`github.com/google/agents-cli`, PyPI
`google-agents-cli`): critical fixes only, no new features, no new templates, no
new deployment targets. New work should target `agents-cli`.

Command mapping for anyone reading older docs:

| Agent Starter Pack | agents-cli |
|---|---|
| `create` | `create` (alias of `scaffold create`) |
| `enhance` | `scaffold enhance` |
| `upgrade` | `scaffold upgrade` |
| `setup-cicd` | `infra cicd` (a.k.a. `infra setup-cicd`) |
| `register-gemini-enterprise` | **`publish gemini-enterprise`** |

Config moved from `[tool.agent-starter-pack]` in `pyproject.toml` to a dedicated
`agents-cli-manifest.yaml`.

What `agents-cli infra cicd` actually scaffolds:

- Terraform for staging and production, plus a separate CI/CD project.
- A CI pipeline on pull request (unit + integration tests).
- A staging CD pipeline on merge to `main`: build and push container to Artifact
  Registry, deploy to staging, run automated load tests.
- Production deploy **gated on manual approval**, promoting the same image that
  was tested in staging.
- Runner is either **GitHub Actions** (detected from `wif.tf`, uses Workload
  Identity Federation for keyless auth) or **Google Cloud Build** (sets up a
  Cloud Build connection to GitHub).
- Terraform variables live in `deployment/terraform/variables.tf`:
  `prod_project_id`, `staging_project_id`, `cicd_runner_project_id`, `region`
  (default `us-west1`), `repository_name`, `repository_owner`, `app_sa_roles`,
  `cicd_roles`.

`agents-cli publish gemini-enterprise` wraps §2.3. Non-interactive flags:
`--agent-runtime-id` (or read from `deployment_metadata.json`),
`--gemini-enterprise-app-id`, `--display-name`, `--description`,
`--tool-description`, `--authorization-id`, `--registration-type {a2a|adk}`,
`--agent-card-url` (A2A path), `--deployment-target {agent_runtime|cloud_run|gke}`.
It is create-or-update, so it is safe to run on every deploy.

Per the `agents-cli` deploy skill reference: on Agent Runtime, `publish` registers
with **ADK** registration (`:streamQuery` against the reasoning-engine resource
name), *not* the agent-card URL. The A2A card path is only used when you
explicitly choose A2A registration — which is the Cloud Run / GKE case.

`agents-cli deploy` to `agent_runtime` is container-based: it requires a
`Dockerfile` at the project root and Agent Runtime builds the image. A prebuilt
`--image` is **not** supported for `agent_runtime` (it is for `cloud_run`).

### 4.3 Deploy-from-Git without a CI runner: Developer Connect

Under-advertised and directly relevant. `client.agent_engines.create` accepts a
`developer_connect_source`, so Agent Runtime pulls source from a linked Git repo
itself:

```python
remote_agent = client.agent_engines.create(
    config={
        "developer_connect_source": {
            "git_repository_link": "projects/P/locations/L/connections/C/gitRepositoryLinks/R",
            "revision": "main",           # branch, tag, or commit SHA
            "dir": "path/to/dir",
        },
        "entrypoint_module": "agent",     # relative to `dir`
        "entrypoint_object": "root_agent",
        "requirements_file": "requirements.txt",
    },
)
```

Agent Runtime fetches the revision, installs `requirements_file`, and starts the
entrypoint. Google's own guidance calls this *"Recommended for projects managed
in a Git repository"* and *"natively supports version control, team
collaboration, and CI/CD pipelines."*

Five documented create/update methods, with Google's stated fit:

| Method | Google's stated fit |
|---|---|
| Python object (pickle) | interactive dev / Colab; struggles with non-serializable components |
| **Source files** (`source_packages`) | *"well-suited for automated workflows such as CI/CD pipelines and Infrastructure as Code"*; **8 MB total limit** |
| Dockerfile | when you need control of the API server; must meet the runtime contract |
| Container image (Artifact Registry) | control over the build, lower deploy latency |
| **Developer Connect** | Git-managed projects |

The 8 MB cap on `source_packages` is a real constraint for a monorepo — it argues
for Developer Connect or a container over inline source.

## 5. ADK built-in tools — the `google_search` rule as of today

The `adk-docs` limitations page (fetched from `main` today) is now materially
narrower than the version cited in
[docs/research/adk-google-search.md](adk-google-search.md) on 2026-08-21. Current
text:

> **ONLY for Search in ADK Python v1.15.0 and lower** — This limitation only
> applies to the use of Google Search and Agent Search tools in ADK Python
> v1.15.0 and lower. ADK Python release v1.16.0 and higher provides a built-in
> workaround to remove this limitation.

Tools still listed as exclusive-in-a-single-agent:

- Code Execution with Gemini API (TypeScript with Gemini 2.0+ is exempt)
- Google Search with Gemini API (in TypeScript, only Gemini 1.x)
- Agent Search (unavailable in TypeScript)

**Can one `LlmAgent` combine `google_search` with custom `FunctionTool`s?** Yes,
on our stack. Two documented workarounds:

1. **Workaround #1 — AgentTool.** A search-only child agent wrapped in
   `AgentTool` and handed to the parent alongside function tools. Broadest
   language support (Python, TypeScript v0.6.1+, Java, Kotlin).
2. **Workaround #2 — `bypass_multi_tools_limit=True`.** Python/Java/Kotlin only,
   and **only** for `GoogleSearchTool` and `VertexAiSearchTool`. Verified present
   in our installed 2.1.0: it is a constructor kwarg on both classes and is read
   by `google/adk/agents/llm_agent.py` at lines 154 and 165 — i.e. `LlmAgent`
   itself performs the wrapping. A maintainer comment on adk-python#3702 confirms
   the flag *"automatically creates the agent wrapper you built manually."*

Root cause is the Gemini API, not ADK: the server historically accepted only one
tool *type* per request (function declarations, Google Search, Vertex AI Search,
code execution, URL context, Google Maps grounding). Gemini 2.x returns
`400 INVALID_ARGUMENT` on a mix. Gemini 3.x adds a **Tool Combination** capability
(Preview) that removes the restriction natively; a third-party comparison matrix
reports `gemini-2.5-flash` failing and `gemini-3-flash-preview` succeeding for
both single-agent and sub-agent shapes. Since we run Gemini 3.5 Flash, the
constraint is largely historical for us — but the ADK-level workarounds remain
the documented, portable path, and I would not rely on Tool Combination while it
is Preview.

**Sub-agents remain the sharp edge.** Still documented, unchanged:

> Built-in tools cannot be used within a sub-agent, with the exception of
> `GoogleSearchTool` and `VertexAiSearchTool` in ADK Python because of the
> workaround mentioned above.

So the `AgentTool` (agent-as-tool) shape is correct and `sub_agents` is still
wrong for built-in tools. Our existing prohibition on `transfer_to_agent`
(`roadmap.md` §9) stays right.

**No documented numeric cap** on built-in tools per agent was found. The
constraint is about *type mixing*, not count.

**Vertex AI Search vs Grounding with Google Search** — different things:

- `google_search` / Grounding with Google Search: public web, Google's index.
  Limit **1M queries/day**. Requires temperature `1.0` for best results. You
  **must** display Search Suggestions (`groundingMetadata.searchEntryPoint.renderedContent`)
  in production — a licensing obligation, not a suggestion. Non-Google results
  must be visually separated.
- `enterprise_web_search` / Web Grounding for Enterprise: compliance-indexed
  sibling for regulated industries. Explicitly a **subset** of the Google Search
  index — narrower coverage in exchange for compliance.
- `VertexAiSearchTool` / Agent Search: retrieval over **your own** configured
  data stores, not the web. Not a substitute for freshness.

`google_search` is also `GoogleSearchTool(model=...)` in 2.1.0, letting the
search sub-agent pin a different model than its parent.

## 6. Grounding freshness — "was this API actually deprecated?"

For our specific question shape, the answer is **`url_context` first, Google
Search second, Vertex AI Search never.**

`url_context` exists in ADK 2.1.0 (`from google.adk.tools import url_context`).
Source check: `UrlContextTool.process_llm_request` raises on Gemini 1.x and emits
`types.Tool(url_context=types.UrlContext())` for Gemini 2+. It is a model built-in;
no local fetch happens in our process.

Why it fits: it does a **two-stage retrieval** — Google's web index first, then a
**live fetch fallback** when the page is too new to be indexed. That is exactly
the "the deprecation notice was published yesterday" case. Google Search grounding
alone can lag; a deprecation page that just went up may not be indexed yet.

Documented limits: **20 URLs per request**; **34 MB** per URL; publicly accessible
URLs only (no localhost, private networks, or tunnels); no paywalls, YouTube,
Google Workspace files, or video/audio. Supported content types include
`text/html`, `application/json`, `text/plain`, `text/xml`, `text/csv`, PNG/JPEG/
BMP/WebP, and `application/pdf`. Safety moderation can return
`url_retrieval_status: URL_RETRIEVAL_STATUS_UNSAFE`.

Combining `url_context` with `google_search` — search broadly, then read the
specific pages deeply — is documented and is the recommended shape for our
question. It is **experimental and `v1beta1`** on Agent Platform.

Response metadata to record as evidence: `url_context_metadata.url_metadata[]`
with `retrieved_url` and `url_retrieval_status`. On the Gemini API side, inline
`url_citation` annotations carry `start_index`/`end_index`. Retrieved page content
counts against input tokens and shows up as `tool_use_prompt_token_count` in
`usage_metadata` — the example in Google's docs shows 10,309 tool-use tokens
against a 27-token prompt, so this is not cheap.

**Documentation contradiction, flagged rather than resolved.** The
`ai.google.dev` URL-context page states: *"Gemini API only: URL Context is only
available in the Gemini API, not through Gemini Enterprise Agent Platform."*
But `docs.cloud.google.com/gemini-enterprise-agent-platform/models/url-context`
is a full Agent Platform page with `gemini-3.5-flash` Python/JS/REST samples
against `https://aiplatform.googleapis.com/v1beta1/...:generateContent`. I could
not determine which is stale. **Do not treat `url_context` on Vertex as settled
until someone runs it against our project.** That is a cheap, high-value smoke
test and it is the one thing in this note most worth verifying empirically.

## 7. Observability

**Agent Observability is GA** as of 2026-06-18.

The whole mechanism is environment variables, no code:

```bash
GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY
```

Semantics, from the tracing page:

- `GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY` turns on traces, logs, and metrics
  but **excludes prompts and responses**.
- `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` opts into the current
  GenAI semantic conventions.
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY` is what actually
  captures input prompts, output responses, and `user.id`. **This is a PII
  decision**: OTel drops message content by default precisely to avoid logging
  user content. Enabling it on a service that handles customer source code needs
  a deliberate call.

Version floors, and this is where we have a gap:

- ADK **1.17.0+** includes built-in OTel support for Google Cloud Observability
  (per `cloud.google.com/stackdriver/docs/instrumentation/ai-agent-adk`).
- ADK **2.6.0+** is required for `gen_ai` application **metrics** following OTel
  GenAI semantic conventions, exported to Cloud Monitoring as user-defined
  metrics (release note, 2026-08-13). **We pin `google-adk>=2.1,<3` and have
  2.1.0 installed — traces and logs yes, `gen_ai` metrics no.**
- Viewing Observability config options requires Vertex AI SDK **>= 1.126.1**;
  agents with telemetry disabled must be redeployed.

APIs to enable: Telemetry (OTLP), Cloud Logging, Cloud Monitoring, Cloud Trace.
Roles on the agent service account: `roles/cloudtrace.agent` (or Cloud Trace
User), `roles/logging.logWriter`, `roles/monitoring.metricWriter`.

For a self-hosted runtime (which is what we have today), ADK exposes the hooks
directly:

```python
from google.adk import telemetry
from google.adk.telemetry import google_cloud

hooks = google_cloud.get_gcp_exporters(enable_cloud_tracing=True)
telemetry.maybe_set_otel_providers(otel_hooks_to_setup=[hooks])
```

`adk deploy agent_engine --trace_to_cloud` / `--otel_to_cloud` are the CLI
equivalents (verified locally).

Two more things bearing on "constantly monitor agent logs":

- **Revision monitoring is log-based.** The revisions doc says to track the
  revision number *as metadata in logs*. There is no per-revision metrics
  dashboard documented — correlating a regression to a revision means filtering
  logs.
- **Feedback service** (Preview, 2026-07-29) collects thumbs-up/down and labels,
  viewable alongside traces or exportable to Cloud Trace.
- Built-in Cloud Monitoring metrics for the **semantic governance policy engine**
  are Preview (2026-08-15): throughput, evaluation counts, latencies,
  `ALLOW`/`DENY` verdict distribution, LLM token consumption, queryable via the
  Monitoring v3 API and PromQL and usable in alerting policies. Directly relevant
  to our policy stage if we adopt semantic governance.

## 8. Launch-stage summary

| Capability | Stage | Date | Source |
|---|---|---|---|
| Agent Runtime (`reasoningEngines`) | GA | — | platform docs |
| Agent Registry (`agentregistry.googleapis.com`) | **GA** | 2026-06-18 | release notes |
| Agent Registry `v1` API + 7 client libs + Terraform | GA | 2026-06-18 | agent-registry release notes |
| Agent Registry MCP server | Preview | — | agent-registry release notes |
| Agent Registry skill governance | Preview | — | agent-registry release notes |
| Agent Gateway | GA | 2026-06-18 | release notes |
| Agent Observability | GA | 2026-06-18 | release notes |
| Model Armor on Agent Gateway | GA | 2026-06-24 | release notes |
| **Agent revisions + traffic splitting** | **Preview (`v1beta1`)** | 2026-05-19 | revisions doc + release notes |
| Agent Identity API (`agentidentity.googleapis.com`) | Preview (replaces `iamconnectors.googleapis.com`) | 2026-06-18 | release notes |
| Semantic governance policies | Preview | 2026-06-30 | release notes |
| Semantic governance metrics | Preview | 2026-08-15 | release notes |
| Feedback service | Preview | 2026-07-29 | release notes |
| Gemini 3.5 Flash | GA | 2026-05-19 | release notes |
| Gemini 3.6 Flash, 3.5 Flash-Lite | GA | 2026-07-21 | release notes |
| Gemini 3.7 Flash | GA | 2026-08-13 | release notes |
| Gemini 3 Flash (`gemini-3-flash-preview`) | dropped as CodeMender backend | 2026-08-18 | release notes |
| `gemini-3.1-flash-image-preview`, `gemini-3-pro-image-preview` | **retired** | 2026-07-17 | release notes |
| Gemini 3.1 Flash Image / 3 Pro Image | GA | 2026-05-26 | release notes |
| `url_context` + `google_search` combined | experimental, `v1beta1` | — | url-context doc |
| Gemini 3 Tool Combination | Preview | — | third-party report, not official docs |
| Agent Starter Pack | **maintenance mode** | — | GitHub README |

Bonus for the demo: `gemini-3.1-flash-image-preview` was **retired** on
2026-07-17 with `gemini-3.1-flash-image` as the replacement. That is a real,
dated, first-party Google deprecation with a named successor — a much stronger
fixture than a synthetic one. `demo/` should reference it.

## 9. What this means for us

Current state: an ADK multi-agent system in `agents/`, running in-process behind
a FastAPI Cloud Run service. Confirmed by inspection — the repo has no
module-level `root_agent`, no `agent_engine_app.py`, no Agent Card, and no
`reasoningEngines` deploy path. `roadmap.md` describes the target; the code has
not reached it.

**1. "Register the agent" is not one decision. It is two, and today we need only one.**
Agent Registry ingests Agent Runtime deployments automatically — deploy and the
`Agent` resource appears, no registration call. Gemini Enterprise app
registration (§2.3) is a *separate*, manual, `discoveryengine` call and is only
needed if we want PatchAPI in an employee-facing agent gallery. PatchAPI is
triggered by provider events and consumed through our own dashboard, so the
Gemini Enterprise app registration is optional. `roadmap.md` §5 already assumes
auto-registration on Agent Runtime deploy; that holds. Do not build a Gemini
Enterprise registration step to satisfy a governance-story checkbox.

**2. The blocking prerequisite is packaging, not registration.** Nothing here
works until each agent is deployable to Agent Runtime, which means a module
exposing `root_agent` (or `app`) per agent, plus a `requirements.txt`. That is
the real work item. Registration is then either free (Agent Registry) or one
idempotent CLI call (`agents-cli publish gemini-enterprise`).

**3. For GitHub → auto-update, the cheapest correct path is:**
`google-github-actions/auth@v3` with Workload Identity Federation (no exported
key, satisfies constraint 9 on secrets), then
`adk deploy agent_engine --agent_engine_id=<existing>`. That is create-or-update,
so each merge to `main` mints a new revision of the same engine — stable resource
name, no re-registration, Agent Registry entry unchanged. The workflow needs
`permissions: {contents: read, id-token: write}`. If we later want Google's
opinionated pipeline (PR tests → staging → load test → manual-approval prod),
`agents-cli infra cicd --cicd-runner github_actions` generates it as Terraform
plus `wif.tf`. Consider **Developer Connect** as the alternative: Agent Runtime
pulls a pinned `revision` from the linked repo itself, which removes the CI
runner from the trust path entirely — attractive given constraint 3 (stop at the
PR) and worth evaluating before we hand a CI runner deploy rights.

Concretely, do not adopt `source_packages` inline deploy: the **8 MB** cap will
not hold a monorepo agent tree with `packages/` dependencies. Dockerfile or
Developer Connect.

**4. Agent Gateway and traffic splitting are mutually exclusive. Pick Gateway.**
This is the one hard conflict with `roadmap.md`. The docs state Agent Gateway
disables traffic-split configuration and per-revision querying. Since §12 makes
Gateway load-bearing for the "deny `merge_pull_request` at the network layer"
demo — which is the differentiated security story — Gateway wins and we forgo
canary traffic splits. Revisions themselves still exist (they are always on and
immutable), so we keep the audit trail and can still `:query` a specific
revision; we simply cannot run a percentage split. Also note traffic splitting is
Preview `v1beta1`, so it was never a safe dependency for a submission anyway.

**5. Search tooling: our current design is right, and we can now simplify.** The
one-tool-per-agent limitation no longer applies at our version. Our four reasoning
agents can each take `GoogleSearchTool(bypass_multi_tools_limit=True)` directly
alongside their function tools, and `LlmAgent` does the wrapping internally —
that is strictly less code than hand-building a search-only `AgentTool` child.
The `AgentTool` pattern in
[docs/research/adk-google-search.md](adk-google-search.md) is not wrong, just no
longer necessary. Either is defensible; the bypass flag is less to maintain.
`sub_agents` remains forbidden for built-in tools, so our no-`transfer_to_agent`
rule stands unchanged.

**6. Change Intelligence should use `url_context`, not just `google_search`.**
"Did Google actually deprecate this?" is a read-this-specific-page question, and
`url_context`'s live-fetch fallback covers the case where a notice is too new to
be indexed — precisely our failure mode. `url_context_metadata.url_metadata[]`
gives us `retrieved_url` + `url_retrieval_status` per URL, which is exactly the
citable evidence the PR body needs, and it lets a fetch failure map cleanly to
`HUMAN_REQUIRED` instead of a guess (constraint 10). **Blocker before we commit:**
`ai.google.dev` claims `url_context` is Gemini-API-only while the Agent Platform
docs document it fully. Someone must run it against our project on
`gemini-3.5-flash` before this goes in the design. Budget for cost — retrieved
page content is billed as input tokens and Google's own example shows ~10k
tool-use tokens for a 27-token prompt.

**7. Observability: we are one pin away from metrics.** Traces and logs work at
ADK 1.17.0+, so 2.1.0 is fine. `gen_ai` metrics need **2.6.0+**. Our
`google-adk>=2.1,<3` range permits it; the lockfile does not. If "constantly
monitor agent logs" is meant to include metrics and alerting, bump the resolved
version. Separately, `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY`
is what makes prompts and responses visible, and on a service that reads customer
source code that is a deliberate privacy decision, not a default to copy from a
tutorial. Note also that per-revision monitoring is log-filtering only, so if we
keep revisions for audit we should emit the revision ID as a log field ourselves.

**8. Two stale items to fix in `roadmap.md` when someone next touches it.**
`--staging_bucket` / `"staging_bucket"` is documented as "no longer required or
used" (§6 still passes it), and the Agent Gateway vs revisions conflict in §12
needs recording. Neither is urgent; both will confuse a worker who trusts the
roadmap over the CLI.

**9. Swap in the real deprecation fixture.** `gemini-3.1-flash-image-preview` was
retired 2026-07-17 with `gemini-3.1-flash-image` named as the replacement. A
first-party, dated, cited Google retirement with a named successor is a stronger
demo artifact than anything we would construct, and it is verifiable from the
public release notes during a live demo.
