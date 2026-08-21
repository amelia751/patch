"""Where the read model connects, and how widely.

Every value a connection would otherwise inline lives here. There is no default
DSN: a missing `DATABASE_URL` is a configuration error the caller must see, not
something to paper over by guessing at localhost. A service that silently
connected to the wrong database would report another environment's run state as
this one's.
"""

import os
from typing import Final

DSN_VAR: Final[str] = "DATABASE_URL"

# The dashboard issues several small reads per page. `db-f1-micro` has 25
# slots and reserves a few for superuser; an 8-wide pool per Cloud Run
# instance plus the indexer's pool exhausts that on a rolling deploy.
def _pool_size(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(0, value)


MIN_POOL_SIZE: Final[int] = _pool_size("PATCHAPI_DB_POOL_MIN", 1)
MAX_POOL_SIZE: Final[int] = max(_pool_size("PATCHAPI_DB_POOL_MAX", 3), 1)

# A read that has not answered by here is not going to help the request that is
# waiting on it. Failing fast surfaces an unreachable database as a 503 rather
# than as a page that hangs.
COMMAND_TIMEOUT_SECONDS: Final[float] = 10.0

# Origins permitted to call the control plane from a browser. Comma-separated;
# empty means no cross-origin access at all.
CORS_ORIGINS_VAR: Final[str] = "PATCHAPI_CORS_ORIGINS"


class MissingDatabaseUrlError(RuntimeError):
    """`DATABASE_URL` is unset or blank."""


def database_url(env: dict[str, str] | None = None) -> str:
    """Return the DSN to connect with, or raise if none is configured."""
    environ = os.environ if env is None else env
    dsn = environ.get(DSN_VAR, "").strip()
    if not dsn:
        raise MissingDatabaseUrlError(
            f"{DSN_VAR} is not set; the read model has no database to connect to"
        )
    return dsn


def cors_origins(env: dict[str, str] | None = None) -> tuple[str, ...]:
    """Return the browser origins allowed to call the control plane."""
    environ = os.environ if env is None else env
    raw = environ.get(CORS_ORIGINS_VAR, "")
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())
