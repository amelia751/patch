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
SELECT summary, rationale, replacements, migration, source_urls, severity::text,
       fail_closed, false_positive, provenance::text, normalizer_version,
       (SELECT string_agg(f.status::text, ',' ORDER BY f.status::text)
        FROM project_change_findings f WHERE f.change_event_id = e.id) AS statuses
FROM change_events e
WHERE e.external_id = $1
"""

_IDENTIFIERS_SQL = """
SELECT i.identifier, i.role::text AS role, i.replacement, i.semantic,
       i.asserted_by::text AS asserted_by, i.corroborated_by::text AS corroborated_by,
       i.live_status::text AS live_status
FROM change_event_identifiers i
JOIN change_events e ON e.id = i.change_event_id
WHERE e.external_id = $1
ORDER BY i.role, i.identifier
"""

_IMPACTS_SQL = """
SELECT p.name AS project, i.repository, left(i.base_sha, 8) AS sha, i.affected,
       i.migration_character, i.notes,
       (SELECT count(*) FROM change_impact_findings f WHERE f.impact_id = i.id) AS findings
FROM change_impacts i
JOIN change_events e ON e.id = i.change_event_id
JOIN projects p ON p.id = i.project_id
WHERE e.external_id = $1
ORDER BY p.name, i.repository
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
            identifiers = await connection.fetch(_IDENTIFIERS_SQL, external_id)
            impacts = await connection.fetch(_IMPACTS_SQL, external_id)
    finally:
        await pool.close()

    print(f"\noutcome: {outcome}")
    if before is None or after is None:
        print(f"FAIL: no change event {external_id}")
        return 1

    print(f"\n-- corpus (provider-wide, one row for every subscriber)")
    print(f"summary (provider):  {after['summary']}")
    print(f"rationale (agent):   {after['rationale']}")
    print(f"provenance:          {after['provenance']} @ {after['normalizer_version']}")
    print(f"migration:           {after['migration']}")

    print(f"\n-- identifiers ({len(identifiers)})")
    for row in identifiers:
        target = f" -> {row['replacement']}" if row["replacement"] else ""
        seen = f" [{row['corroborated_by']}/{row['live_status']}]" if row["corroborated_by"] else ""
        print(f"  {row['role']:<11} {row['identifier']}{target}{seen}")

    print(f"\n-- impact (per project, per repository, per commit) ({len(impacts)})")
    for row in impacts:
        print(
            f"  {row['project']}/{row['repository']}@{row['sha']} "
            f"affected={row['affected']} {row['migration_character']} "
            f"{row['findings']} findings"
        )
        print(f"      {row['notes']}")

    # A rationale that names a repository is the defect this split exists to
    # prevent, and it would be invisible until a second project subscribed.
    leaked = [word for word in ("this project", "this repo") if word in after["rationale"].lower()]
    if leaked:
        print(f"\nFAIL: the provider-wide rationale claims something about a project: {leaked}")
        return 1

    # The agent authors the corpus now, so severity and fail_closed are its to
    # set. What it still may not do is move a finding: status comes from indexed
    # usage and a live check, and no sentence changes either.
    if before["statuses"] != after["statuses"]:
        print(f"\nFAIL: findings moved from {before['statuses']} to {after['statuses']}")
        return 1
    if before["false_positive"] != after["false_positive"]:
        print("\nFAIL: the agent flipped false_positive")
        return 1
    print(f"\nstatus untouched; findings still {after['statuses']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
