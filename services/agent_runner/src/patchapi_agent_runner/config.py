"""Where this service finds the repository and the provider feed.

In the container both are baked in at `/app`. Locally they are the checkout, so
the same code runs either place without a branch at the call site.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

ENV_REPO_ROOT: Final[str] = "PATCHAPI_REPO_ROOT"
ENV_FEED_DIR: Final[str] = "PATCHAPI_FEED_DIR"

_CHECKOUT_ROOT: Final[Path] = Path(__file__).resolve().parents[4]


def ensure_fleet_importable() -> Path:
    """Put the repository root on `sys.path` and return it.

    `patchapi-agents` declares `package = false`, so the fleet is never
    installed into the environment — it is imported from the tree. A console
    script does not put the working directory on the path, so without this the
    service imports cleanly in a shell and fails at the first delivery.
    """
    root = repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def repo_root() -> Path:
    """Base for snapshot paths and credential fallbacks."""
    configured = os.environ.get(ENV_REPO_ROOT, "").strip()
    return Path(configured) if configured else _CHECKOUT_ROOT


def feed_dir() -> Path:
    """Directory of provider notice documents."""
    configured = os.environ.get(ENV_FEED_DIR, "").strip()
    return Path(configured) if configured else repo_root() / "demo" / "fixtures"


__all__ = [
    "ENV_FEED_DIR",
    "ENV_REPO_ROOT",
    "ensure_fleet_importable",
    "feed_dir",
    "repo_root",
]
