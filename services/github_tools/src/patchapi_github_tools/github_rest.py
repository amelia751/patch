"""The only place in PatchAPI that speaks to the GitHub REST API.

Two defences live here rather than in the routing layer, because routing is not
the last thing that could go wrong:

* `_assert_permitted` inspects every outgoing request and refuses the merge,
  administration, secret, collaborator, and branch-protection endpoints by URL
  shape. Even a future handler with a bug cannot reach them.
* failures surface as `UpstreamError` carrying a status and a short message.
  The upstream body is never forwarded, so a GitHub error that happens to echo
  a request header cannot leak the installation token that was sent with it.
"""

from __future__ import annotations

import re
from typing import Any, Final
from urllib.parse import quote

import httpx

from patchapi_github_tools.auth import InstallationTokenProvider
from patchapi_github_tools.config import GITHUB_API_VERSION, USER_AGENT

# URL shapes for the operations listed as "explicitly absent" in roadmap §7.3,
# plus the neighbouring endpoints that would achieve the same effect.
_FORBIDDEN_PATH_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"/pulls/\d+/merge$"),
    re.compile(r"/merges$"),
    re.compile(r"/merge-upstream$"),
    re.compile(r"/branches/[^/]+/protection"),
    re.compile(r"/rulesets"),
    re.compile(r"/actions/secrets"),
    re.compile(r"/actions/variables"),
    re.compile(r"/codespaces/secrets"),
    re.compile(r"/dependabot/secrets"),
    re.compile(r"/environments/[^/]+/secrets"),
    re.compile(r"/collaborators"),
    re.compile(r"/teams"),
    re.compile(r"/pulls/\d+/reviews$"),
    re.compile(r"/\.github/workflows/"),
)

# Only these methods are ever needed by the capability surface; DELETE is not.
_ALLOWED_METHODS: Final[frozenset[str]] = frozenset({"GET", "POST", "PATCH"})


class UpstreamError(RuntimeError):
    """GitHub refused or failed a permitted call."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"GitHub returned HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class ForbiddenEndpointError(RuntimeError):
    """A request was assembled for an endpoint PatchAPI must never call."""


def _assert_permitted(method: str, path: str) -> None:
    if method.upper() not in _ALLOWED_METHODS:
        raise ForbiddenEndpointError(f"{method.upper()} is not part of the PatchAPI GitHub surface")
    for pattern in _FORBIDDEN_PATH_PATTERNS:
        if pattern.search(path):
            raise ForbiddenEndpointError(
                f"refusing to call {method.upper()} {path}: PatchAPI stops at the pull request"
            )


def path_segment(value: str) -> str:
    """Percent-encode one path segment; `/` is not safe inside a segment."""
    return quote(value, safe="")


def file_path_segments(value: str) -> str:
    """Percent-encode a repository-relative file path, preserving separators."""
    return "/".join(quote(part, safe="") for part in value.split("/"))


class GitHubRest:
    """A thin, audited REST client bound to one App installation."""

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        api_base: str,
        tokens: InstallationTokenProvider,
    ) -> None:
        self._http = http
        self._api_base = api_base.rstrip("/")
        self._tokens = tokens

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200, 201),
    ) -> Any:
        """Perform one permitted request and return its decoded body."""
        _assert_permitted(method, path)
        response = await self._http.request(
            method.upper(),
            f"{self._api_base}{path}",
            json=json,
            params=params,
            headers={
                "Authorization": await self._tokens.authorization_header(),
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "User-Agent": USER_AGENT,
            },
        )
        if response.status_code not in expected:
            raise UpstreamError(response.status_code, _short_reason(response))
        if not response.content:
            return None
        return response.json()


def _short_reason(response: httpx.Response) -> str:
    """A one-line reason drawn only from GitHub's own `message` field."""
    try:
        payload = response.json()
    except ValueError:
        return httpx.codes.get_reason_phrase(response.status_code) or "unexpected status"
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message[:300]
    return httpx.codes.get_reason_phrase(response.status_code) or "unexpected status"
