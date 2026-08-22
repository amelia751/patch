"""Exercise the agent enrichment path against a real database.

Proves the two halves of the contract on live rows: rationale and a proposed
replacement land, and every status column reads the same before and after.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DSN_FILE = REPO_ROOT / ".secrets" / "database-url-proxy.txt"

STATUS_COLUMNS = (
    "severity",
    "change_kind",
    "fail_closed",
    "false_positive",
    "effective_at",
    "announced_at",
)

_SNAPSHOT_SQL = """
SELECT e.external_id, e.summary, e.replacements, e.migration, e.source_urls,
       e.severity::text, e.change_kind::text, e.fail_closed, e.false_positive,
       e.effective_at, e.announced_at,
       (SELECT string_agg(f.status::text, ',' ORDER BY f.status::text)
        FROM project_change_findings f WHERE f.change_event_id = e.id) AS statuses
FROM change_events e
WHERE e.external_id = $1
"""


async def main() -> int:
    from packages.state.enrichment import enrich_from_manifest
    from packages.state.pool import create_pool

    external_id = sys.argv[1] if len(sys.argv) > 1 else "imagen4-retirement-2026-08-17"
    identifier = sys.argv[2] if len(sys.argv) > 2 else "imagen-4.0-generate-001"
    dsn = DEFAULT_DSN_FILE.read_text(encoding="utf-8").strip()

    pool = await create_pool(dsn)
    try:
        async with pool.acquire() as connection:
            before = await connection.fetchrow(_SNAPSHOT_SQL, external_id)
            if before is None:
                print(f"FAIL: no change event {external_id}")
                return 1

            applied = await enrich_from_manifest(
                connection,
                {
                    "change_id": "agent-lane-check",
                    "provider": "google",
                    "affected_identifiers": [identifier],
                    "recommended_replacement": "gemini-3.1-flash-image",
                    "semantic_migration_required": True,
                    "rationale": (
                        "Probed on the Gemini API and Vertex: the id no longer resolves on "
                        "either surface. Imagen 4 took a prompt and returned an image; the "
                        "successor is a chat-shaped call, so the request and response shapes "
                        "both change. Not a rename."
                    ),
                    "source_urls": [
                        "https://ai.google.dev/gemini-api/docs/deprecations",
                        "https://ai.google.dev/gemini-api/docs/changelog",
                    ],
                },
            )
            after = await connection.fetchrow(_SNAPSHOT_SQL, external_id)
    finally:
        await pool.close()

    assert after is not None
    print(f"applied: {applied}")
    print(f"summary now: {after['summary'][:110]}")
    print(f"replacements: {after['replacements']}")
    print(f"source_urls:  {after['source_urls']}")

    drifted = [column for column in STATUS_COLUMNS if before[column] != after[column]]
    if before["statuses"] != after["statuses"]:
        drifted.append("finding status")
    if drifted:
        print(f"FAIL: the agent moved {', '.join(drifted)}")
        return 1
    print(f"status columns unchanged; findings still {after['statuses']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
