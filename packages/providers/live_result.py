"""What one liveness check said, for any surface that can be asked.

Shared by the model listing and the package registry. Both answer the same
question about different inventory — "does this still exist" — and both must keep
the third outcome separate: `UNKNOWN` means the check could not run, never that
the thing is gone. Folding the two together is how a rate-limited registry turns
into a wave of retirement notices.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class LiveStatus(StrEnum):
    """What the live surface said about an identifier."""

    RESOLVES = "resolves"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LiveResult:
    """One identifier, checked against one surface, at one moment."""

    identifier: str
    surface: str
    status: LiveStatus
    checked_at: str
    detail: str
    source_url: str

    def to_evidence(self) -> dict[str, Any]:
        """JSON-safe record for a trace, a manifest, or a PR body."""
        return {
            "identifier": self.identifier,
            "surface": self.surface,
            "status": str(self.status),
            "checked_at": self.checked_at,
            "detail": self.detail,
            "source_url": self.source_url,
        }


__all__ = ["LiveResult", "LiveStatus"]
