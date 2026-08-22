"""Ask the provider's own surface whether an identifier still resolves.

Every other Change Intelligence tool reads a document — a notice, a catalog
row, a search result. All of those are somebody's claim about a model, and a
claim can be stale: `imagen-4.0-generate-001` was returning 404 while the
notices still described its retirement in the future tense.

This tool is the one input that is an observation rather than a claim, so it
is the tiebreaker when a notice and reality disagree. It cannot write anything;
the surface either lists the identifier or it does not.
"""

from collections.abc import Callable
from typing import Any, Final

from agents.config import AgentId
from agents.context import RunContext
from agents.tools.results import ReasonCode, ok, refusal
from packages.providers.google.live import LiveStatus, live_identifiers

AGENT: Final[AgentId] = AgentId.CHANGE_INTELLIGENCE

# One turn should confirm a notice, not enumerate a catalog.
MAX_IDENTIFIERS: Final[int] = 12


def build_live_tools(context: RunContext) -> list[Callable[..., Any]]:
    """Build the liveness tool bound to `context`."""

    async def live_identifier(identifiers: list[str]) -> dict[str, Any]:
        """Check whether Google still publishes these model identifiers.

        Returns one result per identifier: `resolves` (the surface lists it),
        `not_found` (the surface does not — this is the same 404 the customer's
        code would get), or `unknown` (the check could not run).

        `unknown` is not evidence of retirement. If you need a retirement to be
        true and the check says `unknown`, corroborate it from the notice and
        an official page, or record HUMAN_REQUIRED. Never treat a failed check
        as a confirmed removal.
        """
        wanted = [item.strip() for item in identifiers if item and item.strip()]
        if not wanted:
            return refusal(ReasonCode.INVALID_CONTRACT, "name at least one identifier to check")
        if len(wanted) > MAX_IDENTIFIERS:
            return refusal(
                ReasonCode.INVALID_CONTRACT,
                f"check at most {MAX_IDENTIFIERS} identifiers per call; {len(wanted)} were named",
            )

        results = await live_identifiers(wanted, base_dir=context.repo_root)
        by_status: dict[str, list[str]] = {status.value: [] for status in LiveStatus}
        for result in results:
            by_status[str(result.status)].append(result.identifier)

        return ok(
            results=[result.to_evidence() for result in results],
            not_found=by_status[LiveStatus.NOT_FOUND.value],
            resolves=by_status[LiveStatus.RESOLVES.value],
            unknown=by_status[LiveStatus.UNKNOWN.value],
        )

    return [live_identifier]


__all__ = ["AGENT", "MAX_IDENTIFIERS", "build_live_tools"]
