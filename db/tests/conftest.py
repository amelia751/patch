"""Make `patchapi_db` importable straight from the checkout.

The package is stdlib-only, so these tests do not need it installed — and a
plain root-level `uv sync`, which does not install workspace members, must not
turn this suite red.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
