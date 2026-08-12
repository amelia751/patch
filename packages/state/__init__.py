"""Read-only access to PatchAPI's authoritative workflow state (constraint 7).

Implements the control plane's `RunStateReader` and `DashboardReader` ports
against the schema in `db/migrations/`. Nothing in this package writes.

Names resolve on first access rather than at import. A bare `pytest` at the
repository root collects every tree using the workspace-root environment, which
does not install workspace members, and an eager import of asyncpg here would
abort collection for all of them.

Entry points:
    `packages.state.pool.create_pool` — open the connection pool.
    `packages.state.runs.PostgresRunStateReader` — the pollable run-state read.
    `packages.state.dashboard.PostgresDashboardReader` — dashboard projections.
    `packages.state.serve.build_app` — the control plane wired to Postgres.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - resolved statically, never at runtime
    from packages.state.config import (
        MissingDatabaseUrlError,
        cors_origins,
        database_url,
    )
    from packages.state.dashboard import PostgresDashboardReader
    from packages.state.pool import StateUnavailableError, create_pool, ping
    from packages.state.runs import PostgresRunStateReader
    from packages.state.serve import build_app

_EXPORTS: dict[str, str] = {
    "MissingDatabaseUrlError": "config",
    "PostgresDashboardReader": "dashboard",
    "PostgresRunStateReader": "runs",
    "StateUnavailableError": "pool",
    "build_app": "serve",
    "cors_origins": "config",
    "create_pool": "pool",
    "database_url": "config",
    "ping": "pool",
}

__all__ = [
    "MissingDatabaseUrlError",
    "PostgresDashboardReader",
    "PostgresRunStateReader",
    "StateUnavailableError",
    "build_app",
    "cors_origins",
    "create_pool",
    "database_url",
    "ping",
]


def __getattr__(name: str) -> Any:
    """Load the submodule that owns `name`, then cache the binding."""
    try:
        submodule = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(f"{__name__}.{submodule}"), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
