"""Pinned identity and environment contract for the GitHub tool service.

Every constant a handler would otherwise inline lives here, including the names
of the environment variables that carry GitHub App credentials. The values
themselves never appear in this repository (CLAUDE.md §9); this file only names
where to look for them.
"""

import os
from collections.abc import Mapping
from typing import Final

SERVICE_NAME: Final[str] = "patchapi-github-tools"

# Kept in step with the `version` field of this tree's `pyproject.toml`.
SERVICE_VERSION: Final[str] = "0.1.0"

# Product routes are versioned; the health probes deliberately are not, so a
# platform health check never has to follow an API version bump.
API_PREFIX: Final[str] = "/v1"

# The calling agent names itself here. It is an identity claim, not an
# authorization: the platform is expected to authenticate the caller (Cloud Run
# IAM / Agent Gateway) before the request reaches this service, and this header
# selects which grant set applies.
AGENT_IDENTITY_HEADER: Final[str] = "X-PatchAPI-Agent"

# Optional correlation for the audit trail. Absent means "not part of a run".
RUN_ID_HEADER: Final[str] = "X-PatchAPI-Run-Id"

GITHUB_API_BASE_DEFAULT: Final[str] = "https://api.github.com"
GITHUB_API_VERSION: Final[str] = "2022-11-28"
USER_AGENT: Final[str] = f"{SERVICE_NAME}/{SERVICE_VERSION}"

# GitHub rejects an App JWT whose `exp` is more than 10 minutes ahead. Nine
# leaves room for clock drift on the caller's side.
APP_JWT_LIFETIME_SECONDS: Final[int] = 9 * 60

# Installation tokens last an hour. Renewing a minute early means a token is
# never handed to a request that outlives it.
INSTALLATION_TOKEN_SKEW_SECONDS: Final[int] = 60

ENV_APP_ID: Final[str] = "GITHUB_APP_ID"
ENV_INSTALLATION_ID: Final[str] = "GITHUB_APP_INSTALLATION_ID"
ENV_PRIVATE_KEY_PATH: Final[str] = "GITHUB_APP_PRIVATE_KEY_PATH"
ENV_PRIVATE_KEY_SECRET: Final[str] = "GITHUB_APP_PRIVATE_KEY_SECRET"
ENV_API_BASE: Final[str] = "GITHUB_API_BASE"

_ENVIRONMENT_VAR: Final[str] = "PATCHAPI_ENV"
_DEFAULT_ENVIRONMENT: Final[str] = "local"


def environment() -> str:
    """Return the deployment environment label reported by the health probes."""
    return os.environ.get(_ENVIRONMENT_VAR, "").strip() or _DEFAULT_ENVIRONMENT


def api_base(env: Mapping[str, str] | None = None) -> str:
    """Return the GitHub REST base URL, overridable for GitHub Enterprise."""
    source = env if env is not None else os.environ
    return (source.get(ENV_API_BASE, "").strip() or GITHUB_API_BASE_DEFAULT).rstrip("/")
