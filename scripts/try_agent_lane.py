"""Run the Change Intelligence lane over one change-normalized event.

Same code path the Cloud Run service takes, minus Pub/Sub, so a turn can be
watched and its effect on the change event inspected before the image is built.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DSN_FILE = REPO_ROOT / ".secrets" / "database-url-proxy.txt"

_SNAPSHOT_SQL = """
SELECT summary, replacements, migration, source_urls, severity::text,
       fail_closed, false_positive,
       (SELECT string_agg(f.status::text, ',' ORDER BY f.status::text)
        FROM project_change_findings f WHERE f.change_event_id = e.id) AS statuses
FROM change_events e
WHERE e.external_id = $1
"""


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from packages.events.provider_events import change_normalized_event
    from packages.state.pool import create_pool
    from patchapi_agent_runner.runner import run_change_intelligence

    external_id = sys.argv[1] if len(sys.argv) > 1 else "imagen4-retirement-2026-08-17"
    identifier = sys.argv[2] if len(sys.argv) > 2 else "imagen-4.0-generate-001"

    envelope = change_normalized_event(
        provider="google",
        external_id=external_id,
        affected_identifiers=[identifier],
        origin="deterministic",
        occurred_at=datetime.now(UTC).isoformat(),
    )

    pool = await create_pool(DEFAULT_DSN_FILE.read_text(encoding="utf-8").strip())
    try:
        async with pool.acquire() as connection:
            before = await connection.fetchrow(_SNAPSHOT_SQL, external_id)
            outcome = await run_change_intelligence(connection, envelope)
            after = await connection.fetchrow(_SNAPSHOT_SQL, external_id)
    finally:
        await pool.close()

    print(f"\noutcome: {outcome}")
    if before is None or after is None:
        print(f"FAIL: no change event {external_id}")
        return 1

    print(f"\nsummary:      {after['summary']}")
    print(f"replacements: {after['replacements']}")
    print(f"migration:    {after['migration']}")
    print(f"source_urls:  {after['source_urls']}")

    moved = [
        column
        for column in ("severity", "fail_closed", "false_positive", "statuses")
        if before[column] != after[column]
    ]
    if moved:
        print(f"\nFAIL: the agent moved {', '.join(moved)}")
        return 1
    print(f"\nstatus untouched; findings still {after['statuses']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
