"""Fetch the public BigQuery release-notes window into the local cache.

    uv run --all-packages python scripts/fetch_google_release_notes.py

The file is gitignored. Serving reads Postgres after Connect; this cache is
for local loaders and image builds that still call ``load_google_release_notes``.
Needs the same project service account as catalog refresh.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


async def _run() -> Path:
    from packages.state.google_release_notes import (
        fetch_release_notes,
        write_google_release_notes,
    )

    snapshot = await fetch_release_notes()
    return write_google_release_notes(snapshot)


def main() -> int:
    dest = asyncio.run(_run())
    print(f"wrote {dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
