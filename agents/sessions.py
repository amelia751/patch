"""Where an agent's conversation is stored between two job executions.

A remediation that needs a credential parks, and the Cloud Run job running it
exits. An in-memory session dies with that process, so the turn the model was
halfway through is gone: on Continue it would re-read every file and re-run
every command before arriving back at the same question. ADK's resume feature
answers exactly this, and its precondition is a session that outlives the
process — so the store is Postgres, the same instance that already holds the
run.

This module is configuration only: which URL, which schema, and whether a
parked turn can be resumed at all. Constructing the session service imports the
agent framework, and by `test_framework_compliance` that happens in `adk.py`
alone.

The tables belong to ADK, which creates and migrates them itself. They are kept
in their own `adk` schema (`0020_agent_hold.sql`) because `sessions` and
`events` are names PatchAPI could plausibly want, and because a schema boundary
makes it obvious which rows are ours to reason about.

Durability is optional and its absence is reported, never hidden. A checkout
with no `DATABASE_URL` still runs agents; it just cannot resume a parked turn,
and saying so is better than a resume that quietly starts over.
"""

from __future__ import annotations

import os
from typing import Final

# The schema `0020_agent_hold.sql` creates. `public` stays on the search path so
# ADK's engine can still see extensions installed there.
ADK_SCHEMA: Final[str] = "adk"
SEARCH_PATH: Final[str] = f"{ADK_SCHEMA},public"

ENV_DATABASE_URL: Final[str] = "DATABASE_URL"
ENV_SESSION_URL: Final[str] = "PATCHAPI_ADK_SESSION_URL"

# SQLAlchemy needs the driver named in the scheme, and it must be the async one:
# ADK builds an async engine. asyncpg is already how the rest of PatchAPI talks
# to this database, so no second driver is introduced.
ASYNC_SCHEME: Final[str] = "postgresql+asyncpg://"
_SYNC_SCHEMES: Final[tuple[str, ...]] = (
    "postgresql://",
    "postgres://",
    "postgresql+psycopg://",
    "postgresql+psycopg2://",
)


def session_dsn(env: dict[str, str] | None = None) -> str:
    """The async Postgres URL for the agent session store, or "" when unset."""
    environ = os.environ if env is None else env
    raw = (environ.get(ENV_SESSION_URL) or environ.get(ENV_DATABASE_URL) or "").strip()
    if not raw:
        return ""
    for scheme in _SYNC_SCHEMES:
        if raw.startswith(scheme):
            return ASYNC_SCHEME + raw[len(scheme) :]
    if raw.startswith(ASYNC_SCHEME):
        return raw
    # An unrecognised scheme is not rewritten into one that happens to import.
    # Guessing a driver would fail at the first turn instead of here.
    return ""


def engine_options() -> dict[str, object]:
    """Connect arguments that put the session tables in the `adk` schema."""
    return {"connect_args": {"server_settings": {"search_path": SEARCH_PATH}}}


def undurable_reason(env: dict[str, str] | None = None) -> str | None:
    """Return None when a parked turn could be resumed, else why it cannot."""
    if not session_dsn(env):
        return (
            f"no {ENV_DATABASE_URL}, so agent sessions are held in memory and a turn "
            "parked for the operator starts over instead of resuming"
        )
    return None


__all__ = [
    "ADK_SCHEMA",
    "ASYNC_SCHEME",
    "ENV_DATABASE_URL",
    "ENV_SESSION_URL",
    "SEARCH_PATH",
    "engine_options",
    "session_dsn",
    "undurable_reason",
]
