"""Publish the PatchAPI fleet to Google Agent Registry.

Idempotent. Every agent is created on the first run and reconciled on every run
after, so republishing after a prompt-version bump or a tool-grant change is the
same command as the first registration.

Writes are explicit: a failure exits non-zero with the API's own message rather
than leaving a half-published catalog. Reads afterwards confirm what the
registry actually holds, which is not the same thing as what was sent.

Called by `scripts/register_agent_registry.sh`, which resolves the agent
runtime's origin and the credentials first.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from agents.catalog import AGENT_TITLES, agent_description, fleet_cards, mcp_tool_spec
from agents.config import FLEET_NAME, FLEET_VERSION, AgentId
from packages.platform.config import MCP_SERVICE_ID, RegistryConfig, load_config
from packages.platform.registry import AgentRegistryClient, RegistryError

# Only PatchAPI's own entries are reconciled. The Workspace agent and the
# project's Vertex reasoning engines are auto-discovered by the registry and are
# not ours to touch.
FLEET_URN_MARKER = "agentregistry:services:"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the cards that would be published and exit without writing.",
    )
    parser.add_argument(
        "--agent",
        action="append",
        choices=[agent.value for agent in AgentId],
        help="register only this agent; repeatable. Defaults to the whole fleet.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="read the catalog back without publishing anything.",
    )
    return parser.parse_args(argv)


def _selected(names: list[str] | None) -> tuple[AgentId, ...]:
    if not names:
        return tuple(AgentId)
    return tuple(AgentId(name) for name in names)


def _report_catalog(client: AgentRegistryClient) -> int:
    """Print what the registry holds. Returns the number of PatchAPI agents."""
    agents = client.list_agents()
    if not agents:
        print("registry read returned nothing (see the warning above for why)")
        return 0
    ours = 0
    for agent in sorted(agents, key=lambda a: a.display_name):
        mine = FLEET_URN_MARKER in agent.agent_id
        ours += 1 if mine else 0
        marker = "*" if mine else " "
        skills = ", ".join(skill.id for skill in agent.skills)
        print(f"{marker} {agent.display_name}  v{agent.version or '-'}")
        print(f"    {agent.agent_id}")
        if skills:
            print(f"    skills: {skills}")
    print(f"\n{ours} PatchAPI agent(s) of {len(agents)} in the catalog (* = ours)")
    return ours


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    config: RegistryConfig = load_config()

    if args.verify_only:
        return 0 if _report_catalog(AgentRegistryClient(config)) else 1

    cards = fleet_cards(config=config, agents=_selected(args.agent))

    if args.dry_run:
        print(
            json.dumps(
                {
                    "fleet": FLEET_NAME,
                    "fleetVersion": FLEET_VERSION,
                    "project": config.project,
                    "location": config.location,
                    "services": [
                        {"serviceId": service_id, "agentSpec": card}
                        for _, service_id, card in cards
                    ],
                    "mcpServer": {
                        "serviceId": MCP_SERVICE_ID,
                        "url": config.mcp_url,
                        "tools": list(mcp_tool_spec()),
                    },
                },
                indent=2,
            )
        )
        return 0

    client = AgentRegistryClient(config)
    failures: list[str] = []

    for agent, service_id, card in cards:
        try:
            result = client.register_agent_card(
                service_id=service_id,
                card=card,
                display_name=AGENT_TITLES[agent],
                description=agent_description(agent),
            )
        except RegistryError as exc:
            failures.append(f"{service_id}: {exc}")
            print(f"FAILED  {service_id}: {exc}", file=sys.stderr)
            continue
        verb = "created" if result.created else "reconciled"
        skills = len(card["skills"])
        print(f"{verb:<10} {service_id}  v{card['version']}  {skills} skill(s)")

    # Registered only against a real JSON-RPC endpoint that serves *these* tools.
    # The create operation rejects any other protocol binding, and a URL serving
    # a different tool list would publish a catalog entry the endpoint cannot
    # honour.
    if config.mcp_url:
        try:
            result = client.register_mcp_server(
                service_id=MCP_SERVICE_ID,
                url=config.mcp_url,
                tools=mcp_tool_spec(),
                display_name="PatchAPI Fleet Tools",
                description=(
                    "The PatchAPI fleet's tool surface over MCP. Which caller may reach "
                    "which tool is enforced by the fleet's guardrails, not by this listing."
                ),
            )
            verb = "created" if result.created else "reconciled"
            print(f"{verb:<10} {MCP_SERVICE_ID}  {len(mcp_tool_spec())} tool(s)")
        except RegistryError as exc:
            failures.append(f"{MCP_SERVICE_ID}: {exc}")
            print(f"FAILED  {MCP_SERVICE_ID}: {exc}", file=sys.stderr)
    else:
        print(f"skipped    {MCP_SERVICE_ID}: no JSON-RPC MCP endpoint configured")

    print()
    _report_catalog(client)

    if failures:
        print(f"\n{len(failures)} registration(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
