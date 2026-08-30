"""Where the Memory Bank lives, and the vocabulary written into every memory.

Scope keys and fact kinds are pinned here rather than at call sites for the same
reason span names are: a recall query that stops matching what a write produced
fails silently, returning "we know nothing about this repository" instead of an
error. Renaming one has to be a single visible change.
"""

from typing import Final

# Agent Engine is regional and the engine id is an opaque number, so both are
# configuration. `MEMORY_BANK_ENGINE` accepts either the bare id or the full
# `projects/.../reasoningEngines/...` resource name.
ENV_MEMORY_BANK_ENGINE: Final[str] = "PATCHAPI_MEMORY_BANK_ENGINE"
ENV_MEMORY_BANK_LOCATION: Final[str] = "PATCHAPI_MEMORY_BANK_LOCATION"
# Both names, in this order, matching `packages/state/provider_check.py`. The
# deployment sets `GCP_PROJECT`; the Google SDKs read `GOOGLE_CLOUD_PROJECT`.
PROJECT_VARS: Final[tuple[str, ...]] = ("GCP_PROJECT", "GOOGLE_CLOUD_PROJECT")

DEFAULT_LOCATION: Final[str] = "us-central1"

# Memory Bank scopes are string maps, and a scope is an exact-match partition:
# two writes with different scopes are never returned by one another's recall.
# Repository is the partition PatchAPI reasons about.
SCOPE_REPO: Final[str] = "repo"
SCOPE_KIND: Final[str] = "kind"

# Two kinds of memory, kept apart because they are consumed differently. The
# profile is structured state a deterministic gate reads; a migration is prose a
# model retrieves by similarity. Mixing them would put JSON into the model's
# context and prose into a policy decision.
KIND_PROFILE: Final[str] = "repository_profile"
KIND_MIGRATION: Final[str] = "previous_migration"

# The profile is stored as one JSON fact behind this marker so a human reading
# the Memory Bank console can tell machine state from recalled narrative.
PROFILE_MARKER: Final[str] = "patchapi.repository_profile.v1"

RETRIEVE_TOP_K: Final[int] = 10

# A recall on the critical path of a run. Institutional context is worth waiting
# a moment for and never worth stalling a migration over.
REQUEST_TIMEOUT_SECONDS: Final[float] = 10.0

__all__ = [
    "DEFAULT_LOCATION",
    "ENV_MEMORY_BANK_ENGINE",
    "ENV_MEMORY_BANK_LOCATION",
    "KIND_MIGRATION",
    "KIND_PROFILE",
    "PROFILE_MARKER",
    "PROJECT_VARS",
    "REQUEST_TIMEOUT_SECONDS",
    "RETRIEVE_TOP_K",
    "SCOPE_KIND",
    "SCOPE_REPO",
]
