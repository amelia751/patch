"""The loop that keeps the Releases tab current.

Classification reads `identifier_probes` to decide whether a model is gone for
real or merely dated in a watchlist. Nothing writes that table during a request:
probing every indexed identifier means several calls to a Google surface, which
is far too slow to hang off a page load. So the tab can only be as fresh as the
last time this loop ran.

Four steps, in order:

1. Poll: probe every identifier the repo indexer has stored, diff against the
   last poll, and publish `provider-change-detected` for each transition. This
   is the step that belongs here permanently.
2. Write a change event for any identifier that stopped resolving and that no
   existing notice covers — the break nobody announced.
3. Refresh the watchlist / catalog / release-note corpus for each subscribed
   project.
4. Reclassify, so probe evidence moves live call sites out of Watching.

Steps 2 to 4 duplicate what the `provider-change-detected` subscribers do, and
are kept only until events are carrying the load. They are the net: while the
pipeline is being wired, a dropped message degrades the tab's freshness rather
than its correctness. Delete them once the subscribers are proven, not before.

Safe to re-run, which is what makes it schedulable: events are insert-if-absent,
probes upsert, and a human-dismissed finding stays dismissed.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

DEFAULT_PROVIDER: Final[str] = "google"
EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1

_SUBSCRIBED_SQL: Final[str] = """
SELECT DISTINCT p.id, p.name
FROM projects p
JOIN project_provider_subscriptions s ON s.project_id = p.id
JOIN providers pr ON pr.id = s.provider_id AND pr.slug = $1
ORDER BY p.name
"""


async def refresh_releases(
    connection: asyncpg.Connection, *, provider: str = DEFAULT_PROVIDER
) -> dict[str, Any]:
    """Run the full refresh and return what it observed."""
    from packages.state.discovery import record_discovered_retirements, refresh_subscribed
    from packages.state.findings import refresh_project_findings
    from packages.state.inbox_corpus import ensure_inbox_corpus
    from packages.state.provider_poll import poll_provider

    outcome = await poll_provider(connection, provider=provider)
    results = outcome.results
    for change in outcome.transitions:
        log.info(
            "transition %s %s -> %s",
            change.identifier,
            change.previous_status,
            change.current_status,
        )
    log.info("announced %d provider change events", len(outcome.published))

    buckets: dict[str, list[str]] = {"resolves": [], "not_found": [], "unknown": []}
    for result in results:
        buckets.setdefault(str(result.status), []).append(result.identifier)
    for status in ("not_found", "unknown", "resolves"):
        names = ", ".join(sorted(buckets[status])) or "(none)"
        log.info("probe %-9s %3d  %s", status, len(buckets[status]), names)

    discovered = await record_discovered_retirements(connection, provider=provider, results=results)
    for external_id in discovered:
        log.info("recorded undocumented retirement %s", external_id)

    rows = await connection.fetch(_SUBSCRIBED_SQL, provider)
    projects: dict[str, int] = {}
    for row in rows:
        counts = await ensure_inbox_corpus(connection, row["id"], provider)
        written = await refresh_project_findings(connection, row["id"], provider)
        projects[str(row["name"])] = written
        log.info(
            "%s: %d findings (watchlist %d, catalog %d, notes %d)",
            row["name"],
            written,
            counts["watchlist"],
            counts["catalog"],
            counts["notes"],
        )
    if not rows:
        log.info("no project is subscribed to %s", provider)
        await refresh_subscribed(connection, provider)

    return {
        "provider": provider,
        "probed": len(results),
        "not_found": tuple(sorted(buckets["not_found"])),
        "unknown": tuple(sorted(buckets["unknown"])),
        "announced": outcome.published,
        "discovered": tuple(discovered),
        "projects": projects,
    }


async def _run(provider: str, dsn: str | None) -> int:
    import asyncpg

    from packages.state.config import database_url

    connection = await asyncpg.connect(dsn or database_url())
    try:
        summary = await refresh_releases(connection, provider=provider)
    finally:
        await connection.close()
    log.info(
        "refresh complete: probed %d, %d undocumented, %d projects",
        summary["probed"],
        len(summary["discovered"]),
        len(summary["projects"]),
    )
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--dsn", default=None, help="overrides DATABASE_URL")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    # httpx logs the full request URL at INFO. Defence in depth behind the
    # header change in the probe: this job's output goes to Cloud Logging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        return asyncio.run(_run(args.provider, args.dsn))
    except Exception as exc:
        log.error("FAIL: %s: %s", type(exc).__name__, exc)
        return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
