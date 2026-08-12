#!/usr/bin/env python3
"""Live Gemini reasoning-model proof, runnable from anywhere in the repo.

    uv run --all-packages python scripts/smoke_gemini_vertex.py

A thin front end for `packages.providers.google.smoke` so the live check has a
path that does not depend on the caller's working directory or `PYTHONPATH`.
The adapter owns every decision; this file only makes the package importable.

Exit codes: 0 PASS, 1 FAIL, 3 SKIP (credentials genuinely absent).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.providers.google.smoke import main  # noqa: E402 - path setup must precede the import

if __name__ == "__main__":
    raise SystemExit(main())
