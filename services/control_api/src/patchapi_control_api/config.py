"""Pinned identity and configuration for the control plane.

Every constant a handler would otherwise inline lives here: the service name
reported to operators, the API version prefix, and the namespace that seeds
idempotency keys. Changing one of these is a deliberate edit to this file, not
a side effect of editing a route.
"""

import os
from typing import Final

SERVICE_NAME: Final[str] = "patchapi-control-api"

# Kept in step with the `version` field of this tree's `pyproject.toml`.
SERVICE_VERSION: Final[str] = "0.1.0"

# All product routes are versioned; the health probes deliberately are not, so
# a platform health check never has to follow an API version bump.
API_PREFIX: Final[str] = "/v1"

# Namespacing the digest input means a future action type cannot collide with
# provider-check keys already recorded in Postgres.
IDEMPOTENCY_KEY_NAMESPACE: Final[str] = "provider_check:v1"

_ENVIRONMENT_VAR: Final[str] = "PATCHAPI_ENV"
_DEFAULT_ENVIRONMENT: Final[str] = "local"


def environment() -> str:
    """Return the deployment environment label reported by the health probes."""
    return os.environ.get(_ENVIRONMENT_VAR, "").strip() or _DEFAULT_ENVIRONMENT
