"""Narrow GitHub capability vocabulary and reference types (roadmap §7.3).

This package deliberately cannot talk to GitHub. It names what may be asked
for and what an answer refers to; `services/github_tools` owns the App
credentials and performs the calls.
"""

from packages.github.capabilities import (
    FORBIDDEN_CAPABILITIES,
    READ_CAPABILITIES,
    WRITE_CAPABILITIES,
    Capability,
    CapabilityError,
    ForbiddenCapabilityError,
    UnknownCapabilityError,
    is_write_capability,
    resolve_capability,
)
from packages.github.types import (
    BranchRef,
    CommitRef,
    PullRequestRef,
    RepositoryRef,
)

__all__ = [
    "FORBIDDEN_CAPABILITIES",
    "READ_CAPABILITIES",
    "WRITE_CAPABILITIES",
    "BranchRef",
    "Capability",
    "CapabilityError",
    "CommitRef",
    "ForbiddenCapabilityError",
    "PullRequestRef",
    "RepositoryRef",
    "UnknownCapabilityError",
    "is_write_capability",
    "resolve_capability",
]
