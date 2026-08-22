"""Refresh the Releases tab from live evidence.

    uv run --all-packages python scripts/refresh_releases.py

Four steps, in order:

1. Probe every identifier the repo indexer has stored, and record what each
   Google surface says about it.
2. Write a change event for any identifier that stopped resolving and that no
   existing notice covers — the break nobody announced.
3. Refresh the watchlist / catalog / release-note corpus for each subscribed
   project.
4. Reclassify, so probe evidence moves live call sites out of Watching.

This is the loop that keeps the tab current. It is safe to re-run: events are
insert-if-absent, probes upsert, and a human-dismissed finding stays dismissed.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DSN_FILE: Final[Path] = REPO_ROOT / ".secrets" / "database-url-proxy.txt"
EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1


async def _refresh(dsn: str, provider: str) -> int:
    import asyncpg

    from packages.state.discovery import record_discovered_retirements, refresh_subscribed
    from packages.state.findings import probe_indexed_identifiers, refresh_project_findings
    from packages.state.inbox_corpus import ensure_inbox_corpus

    connection = await asyncpg.connect(dsn)
    try:
        print(f"probing every indexed {provider} identifier")
        results = await probe_indexed_identifiers(connection, provider=provider)
        buckets: dict[str, list[str]] = {"resolves": [], "not_found": [], "unknown": []}
        for result in results:
            buckets[str(result.status)].append(result.identifier)
        for status in ("not_found", "unknown", "resolves"):
            names = ", ".join(sorted(buckets[status])) or "(none)"
            print(f"  {status:<10} {len(buckets[status]):>3}  {names}")

        print("\nlooking for retirements with no notice")
        discovered = await record_discovered_retirements(
            connection, provider=provider, results=results
        )
        for external_id in discovered:
            print(f"  recorded {external_id}")
        if not discovered:
            print("  (none — every dead identifier is already covered by a notice)")

        print("\nrefreshing the corpus for each subscribed project")
        rows = await connection.fetch(
            """
            SELECT DISTINCT p.id, p.name
            FROM projects p
            JOIN project_provider_subscriptions s ON s.project_id = p.id
            JOIN providers pr ON pr.id = s.provider_id AND pr.slug = $1
            ORDER BY p.name
            """,
            provider,
        )
        for row in rows:
            counts = await ensure_inbox_corpus(connection, row["id"], provider)
            written = await refresh_project_findings(connection, row["id"], provider)
            print(
                f"  {row['name']}: {written} findings "
                f"(watchlist {counts['watchlist']}, catalog {counts['catalog']}, "
                f"notes {counts['notes']})"
            )
        if not rows:
            print("  (no project is subscribed to this provider)")
            await refresh_subscribed(connection, provider)
    finally:
        await connection.close()
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--provider", default="google")
    parser.add_argument("--dsn-file", type=Path, default=DEFAULT_DSN_FILE)
    args = parser.parse_args(argv)

    if not args.dsn_file.is_file():
        print(f"FAIL: no DSN at {args.dsn_file}")
        return EXIT_FAIL
    dsn = args.dsn_file.read_text(encoding="utf-8").strip()

    try:
        return asyncio.run(_refresh(dsn, args.provider))
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
