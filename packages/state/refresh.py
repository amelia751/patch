"""The poll that starts every provider change.

Google announces a model retirement to nobody in particular, so something has to
ask. This job asks. It checks every identifier the repo indexer has stored, diffs
the answer against the last poll, and publishes `provider-change-detected` for
each transition. Recording the undocumented break and reclassifying the projects
that call it belong to the subscribers now, so neither happens here: doing both
would race the event lane to write the same row.

What has no event source is the notice corpus. Lifecycle rows arrive as a
committed snapshot and release notes arrive from a BigQuery query, neither of
which announces itself, so a pass over subscribed projects is still the only
thing that moves a newly published notice into the inbox. That pass reclassifies
only when it wrote something: a poll that finds no new notice costs a few queries
and changes nothing.

Safe to re-run, which is what makes it schedulable: events are insert-if-absent,
liveness rows upsert, and a human-dismissed finding stays dismissed.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Final

from packages.state.refresh_log import (
    RefreshSummary,
    configure_logging,
    emit,
    entry,
    failure,
)

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


@dataclass(frozen=True, slots=True)
class CorpusPromotion:
    """What one pass over the notice corpus added, and what it reclassified.

    Both, because the log entry distinguishes them: notices arriving is why a
    reclassification happened, and a pass that added none is the resting state.
    """

    notices: int = 0
    projects: dict[str, int] = field(default_factory=dict)


async def promote_corpus(
    connection: asyncpg.Connection, *, provider: str = DEFAULT_PROVIDER
) -> CorpusPromotion:
    """Pull newly published notices into the inbox, and reclassify if any landed.

    A notice is covered provider-wide, so the second project to ask for the same
    identifier inserts nothing. That makes a per-project "did I write anything"
    test the wrong gate — it would skip every project but the first. The gate is
    therefore the whole pass: if the provider gained a notice, every subscribed
    project is reclassified; if it gained none, none are.
    """
    from packages.state.findings import refresh_project_findings
    from packages.state.inbox_corpus import ensure_inbox_corpus
    from packages.state.sdk_notices import ensure_sdk_events

    rows = await connection.fetch(_SUBSCRIBED_SQL, provider)
    if not rows:
        log.debug("no project is subscribed to %s", provider)
        return CorpusPromotion()

    # Registry answers are the same for every project, so they are fetched once
    # for the provider rather than once per project inside the loop below.
    added = await ensure_sdk_events(connection, provider)
    for row in rows:
        counts = await ensure_inbox_corpus(connection, row["id"], provider)
        added += counts["watchlist"] + counts["catalog"] + counts["notes"]
    if not added:
        log.debug("no new notice for %s; %d projects left as classified", provider, len(rows))
        return CorpusPromotion()

    log.debug("%d new notices; reclassifying %d subscribed projects", added, len(rows))
    projects: dict[str, int] = {}
    for row in rows:
        written = await refresh_project_findings(connection, row["id"], provider)
        projects[str(row["name"])] = written
        log.debug("%s: %d findings", row["name"], written)
    return CorpusPromotion(notices=added, projects=projects)


async def refresh_releases(
    connection: asyncpg.Connection, *, provider: str = DEFAULT_PROVIDER
) -> RefreshSummary:
    """Poll for transitions, promote new notices, and report what moved.

    Returns rather than narrates. The census used to be printed here, one line
    per status, which put the five permanently retired identifiers on the log at
    the same weight as a new retirement; `refresh_log.entry` decides what a
    reader sees.
    """
    from packages.state.provider_poll import poll_provider

    outcome = await poll_provider(connection, provider=provider)
    results = outcome.results

    buckets: dict[str, list[str]] = {"resolves": [], "not_found": [], "unknown": []}
    for result in results:
        buckets.setdefault(str(result.status), []).append(result.identifier)
    # Reachable with `--verbose`, and the reason the entry can carry counts
    # alone without the census becoming unreadable.
    for status in ("not_found", "unknown", "resolves"):
        names = ", ".join(sorted(buckets[status])) or "(none)"
        log.debug("live %-9s %3d  %s", status, len(buckets[status]), names)

    promotion = await promote_corpus(connection, provider=provider)

    return RefreshSummary(
        provider=provider,
        checked=len(results),
        resolves=tuple(sorted(buckets["resolves"])),
        not_found=tuple(sorted(buckets["not_found"])),
        unknown=tuple(sorted(buckets["unknown"])),
        transitions=tuple(
            {
                "identifier": change.identifier,
                "surface": change.surface,
                "transition": change.transition,
                "from": change.previous_status,
                "to": change.current_status,
            }
            for change in outcome.transitions
        ),
        announced=outcome.published,
        first_seen=outcome.first_seen,
        held_back=outcome.held_back,
        notices=promotion.notices,
        reclassified=tuple(sorted(promotion.projects)),
    )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


async def _run(provider: str, dsn: str | None, *, started: float | None = None) -> int:
    import asyncpg

    from packages.state.config import database_url
    from packages.state.pool import configure_connection

    began = time.monotonic() if started is None else started
    connection = await asyncpg.connect(dsn or database_url())
    # One connection, not a pool, but the same SQL — so the same codecs. Without
    # them the job polls every surface, decides what changed, and only then
    # fails on the first jsonb argument it tries to write.
    await configure_connection(connection)
    try:
        summary = await refresh_releases(connection, provider=provider)
    finally:
        await connection.close()
    emit(entry(replace(summary, duration_ms=_elapsed_ms(began))))
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--dsn", default=None, help="overrides DATABASE_URL")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print the per-identifier census and each transition as it is found",
    )
    args = parser.parse_args(argv)

    configure_logging(logging.DEBUG if args.verbose else logging.INFO)
    # httpx logs the full request URL at INFO. Defence in depth behind the
    # header change in the liveness check: this job's output goes to Cloud Logging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    started = time.monotonic()
    try:
        return asyncio.run(_run(args.provider, args.dsn, started=started))
    except Exception as exc:
        # The one entry this job emits, in the one case where it concluded
        # nothing. On stderr and severity ERROR, because the old `log.error` went
        # to stdout and Cloud Run recorded a crashed refresh as DEFAULT.
        emit(failure(args.provider, exc, duration_ms=_elapsed_ms(started)))
        return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
