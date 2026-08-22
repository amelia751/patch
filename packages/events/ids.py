"""Deterministic ids shared by every event family.

Pub/Sub delivers at least once and GitHub redelivers, so an event id derived
from a clock or a counter would make the same fact look like two facts. Both
helpers are pure: the same inputs give the same id in any process, which is
what lets a subscriber recognise work it has already done.
"""

from __future__ import annotations

import hashlib
import re
from typing import Final

_UNSAFE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]+")


def slug(value: str) -> str:
    """Reduce an arbitrary name to the run-id alphabet (`idempotency.py`)."""
    cleaned = _UNSAFE.sub("-", value).strip("-")
    return cleaned or "unnamed"


def digest(*parts: str) -> str:
    """A stable short digest of the facts that identify an event."""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


__all__ = ["digest", "slug"]
