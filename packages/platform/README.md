# `packages/platform`

Google Agent Registry client. PatchAPI publishes its seven
agents to the registry so "which agents does this enterprise run, and what does
each one claim it can do" is answerable from the platform rather than from a
slide.

```python
from packages.platform import AgentRegistryClient

client = AgentRegistryClient()
for agent in client.list_agents():
    print(agent.agent_id, agent.version, [skill.id for skill in agent.skills])
```

Two rules shape the module.

**Reads fail soft.** `list_agents`, `get_agent`, `search_agents`,
`list_mcp_servers`, `list_services` and `list_bindings` return empty or `None`
and log why. Nothing in a remediation run branches on the catalog, so a registry
outage costs the fleet its listing and never its run. `get_agent` returning
`None` means "not found *or* not reachable" — never "not registered".

**Writes are explicit.** `register_service` raises. Registration is something an
operator runs (`scripts/register_agent_registry.sh`), where a half-published
catalog has to be visible and fixed. A second run patches the existing Service
instead of failing, so republishing after a prompt-version bump is the same
command as the first registration.

## What the API insists on

Verified against the `v1` discovery document (revision `20260821`) and project
`patch-505223`:

- A `Service` must set exactly **one** of `agentSpec`, `mcpServerSpec`,
  `endpointSpec`.
- An `A2A_AGENT_CARD` spec must leave the Service's `interfaces` **empty**. The
  card's own `url` and `preferredTransport` carry connectivity.
- A `TOOL_SPEC` MCP Server must use protocol binding `JSONRPC`. `HTTP_JSON` is
  rejected by the create *operation*, not by the create call — which is why
  `await_operation` is not optional.
- `services.create` returns a long-running operation. The `Agent` resource only
  appears in `.../agents` once it is done.

Registration of Service resources stays in a script: there is no Terraform
provider resource for Agent Registry services in `hashicorp/google`. Terraform
owns the API enablement and the IAM (`infra/terraform/environments/dev`).

## Configuration

Pinned in `config.py`; no project, region, or URL is inlined at a call site.

| Variable | Default | Purpose |
| --- | --- | --- |
| `GCP_PROJECT` | — | Project whose catalog is read and written |
| `PATCHAPI_REGISTRY_LOCATION` | `us-central1` | Registry region (it has no `global`) |
| `PATCHAPI_REGISTRY_ENABLED` | on when `GCP_PROJECT` is set | Kill switch |
| `PATCHAPI_A2A_BASE_URL` | — | Origin the published cards point at |
| `PATCHAPI_MCP_URL` | — | Endpoint serving the *fleet's* tools over MCP JSON-RPC; registration is skipped while unset |
| `PATCHAPI_REGISTRY_TIMEOUT_SECONDS` | `30` | Per-request timeout |

The cards themselves are derived from `agents/config.py` by `agents/catalog.py`,
so an agent's published version and skills cannot drift from its tool grants.

Verified by:

```bash
uv run --all-packages pytest packages/platform/tests agents/tests/test_catalog.py
./scripts/register_agent_registry.sh --dry-run     # cards, no writes
./scripts/register_agent_registry.sh --verify-only # read the live catalog back
```
