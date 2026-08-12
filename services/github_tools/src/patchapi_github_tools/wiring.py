"""Building the GitHub client from the environment, or declining to.

Absent credentials are a first-class state, not an error: the service starts,
reports itself not ready, and refuses invocations with a named 503. That is
what lets the local vertical slice and CI run this tree honestly without a
GitHub App, and what makes a deployed instance's readiness signal meaningful.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from patchapi_github_tools.auth import InstallationTokenProvider
from patchapi_github_tools.config import USER_AGENT, api_base
from patchapi_github_tools.credentials import (
    SecretResolver,
    credentials_are_configured,
    load_app_credentials,
)
from patchapi_github_tools.github_rest import GitHubRest

# GitHub's own guidance for App traffic: a small pool and a bounded timeout, so
# a slow upstream surfaces as a 502 rather than holding a run open.
_TIMEOUT = httpx.Timeout(10.0, connect=5.0, read=30.0)


def build_github_client(
    env: Mapping[str, str] | None = None,
    *,
    http: httpx.AsyncClient | None = None,
    secret_resolver: SecretResolver | None = None,
) -> GitHubRest | None:
    """Return a wired client, or `None` when the App is not configured.

    A malformed configuration — a key path that does not exist, a non-numeric
    App ID — raises `CredentialsUnavailableError` rather than returning `None`:
    "not configured" and "configured wrongly" must not look the same.
    """
    if not credentials_are_configured(env):
        return None
    credentials = load_app_credentials(env, secret_resolver=secret_resolver)
    base = api_base(env)
    client = (
        http
        if http is not None
        else httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT})
    )
    return GitHubRest(
        http=client,
        api_base=base,
        tokens=InstallationTokenProvider(credentials, http=client, api_base=base),
    )
