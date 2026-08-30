"""Memory Bank backed by a Vertex AI Agent Engine (roadmap §10.2).

The engine is provisioned once and holds memories keyed by scope. Two shapes are
stored under one repository scope: a single JSON profile that deterministic code
reads, and one prose fact per migration outcome that a model retrieves by
similarity. `packages/memory/config.py` explains why those are kept apart.

Every read here is fail-soft and every failure is distinguishable. A recall that
cannot reach the engine raises `MemoryUnavailableError` rather than returning
`None`, because "the prohibitions could not be read" and "there are no
prohibitions" must never collapse into the same answer — the first has to be able
to stop a run, and the second must not.

Deliberately not the `google-cloud-aiplatform` SDK: this package is imported by
the agent lane, and the REST surface it needs is four calls. `google-auth` for
credentials and the standard library for transport keeps the dependency that
reaches production small enough to audit.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Final, Self

from packages.memory.client import MemoryUnavailableError
from packages.memory.config import (
    DEFAULT_LOCATION,
    ENV_MEMORY_BANK_ENGINE,
    ENV_MEMORY_BANK_LOCATION,
    KIND_MIGRATION,
    KIND_PROFILE,
    PROFILE_MARKER,
    PROJECT_VARS,
    REQUEST_TIMEOUT_SECONDS,
    RETRIEVE_TOP_K,
    SCOPE_KIND,
    SCOPE_REPO,
)
from packages.memory.profile import PreviousMigration, RepositoryProfile

log = logging.getLogger(__name__)

_SCOPES: Final[tuple[str, ...]] = ("https://www.googleapis.com/auth/cloud-platform",)


def cloud_project(env: dict[str, str] | None = None) -> str:
    """The project a bare engine id is resolved against."""
    environ = env if env is not None else dict(os.environ)
    for name in PROJECT_VARS:
        value = environ.get(name, "").strip()
        if value:
            return value
    return ""


def memory_bank_unavailable_reason(env: dict[str, str] | None = None) -> str | None:
    """Return `None` when a Memory Bank is configured and reachable in principle."""
    environ = env if env is not None else dict(os.environ)
    engine = environ.get(ENV_MEMORY_BANK_ENGINE, "").strip()
    if not engine:
        return f"{ENV_MEMORY_BANK_ENGINE} is not set"
    if not engine.startswith("projects/") and not cloud_project(environ):
        return f"one of {', '.join(PROJECT_VARS)} is required to resolve a bare engine id"
    try:
        import google.auth  # noqa: F401
    except ImportError as exc:
        return f"google-auth is not installed ({exc})"
    return None


class VertexMemoryBank:
    """`MemoryBankClient` over one Agent Engine's memories.

    Construct with `from_env()` in production. The explicit constructor exists so
    a test can point at a fake transport without credentials.
    """

    __slots__ = ("_engine", "_location", "_transport")

    def __init__(
        self,
        *,
        engine: str,
        location: str = DEFAULT_LOCATION,
        transport: Any | None = None,
    ) -> None:
        self._engine = engine
        self._location = location
        self._transport = transport if transport is not None else _AuthorizedTransport()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Self:
        """Build from configuration, or raise if the engine is not configured."""
        environ = env if env is not None else dict(os.environ)
        reason = memory_bank_unavailable_reason(environ)
        if reason is not None:
            raise MemoryUnavailableError(reason)
        return cls(
            engine=_resolve_engine(environ),
            location=environ.get(ENV_MEMORY_BANK_LOCATION, "").strip() or DEFAULT_LOCATION,
        )

    # -- reads ---------------------------------------------------------------

    def recall(self, repo: str) -> RepositoryProfile | None:
        """The stored profile for `repo`, or `None` when the engine holds none."""
        facts = self._retrieve(repo, kind=KIND_PROFILE)
        for fact in facts:
            profile = _decode_profile(fact)
            if profile is not None:
                return profile
        return None

    def recall_migrations(self, repo: str, *, query: str = "") -> tuple[str, ...]:
        """Prose recollections of earlier migrations, most relevant first.

        Returned as text rather than parsed: these are for a model's context, and
        turning a recollection into a typed decision is exactly the promotion
        this product refuses to make on a memory's say-so.
        """
        return tuple(self._retrieve(repo, kind=KIND_MIGRATION, query=query))

    # -- writes --------------------------------------------------------------

    def remember(self, profile: RepositoryProfile) -> None:
        """Store or replace the profile for `profile.repo`."""
        self.forget(profile.repo)
        payload = json.dumps(profile.to_dict(), sort_keys=True, separators=(",", ":"))
        self._create(
            fact=f"{PROFILE_MARKER} {payload}",
            scope={SCOPE_REPO: profile.repo, SCOPE_KIND: KIND_PROFILE},
        )

    def record_migration(self, repo: str, migration: PreviousMigration) -> None:
        """Append a migration outcome as a fact a later run can retrieve.

        Written as a sentence because Memory Bank retrieval is semantic: a run
        months later asks "was something like this tried here before", and a JSON
        blob is not what that question matches against.
        """
        fact = (
            f"Migration {migration.migration_id} on {repo} was {migration.decision}."
            f" {migration.reason}".rstrip()
        )
        self._create(fact=fact, scope={SCOPE_REPO: repo, SCOPE_KIND: KIND_MIGRATION})

    def forget(self, repo: str) -> bool:
        """Delete the stored profile for `repo`. Returns whether one existed."""
        removed = False
        for name in self._memory_names(repo, kind=KIND_PROFILE):
            self._request("DELETE", f"https://{self._host()}/v1/{name}")
            removed = True
        return removed

    # -- transport -----------------------------------------------------------

    def _host(self) -> str:
        return f"{self._location}-aiplatform.googleapis.com"

    def _base(self) -> str:
        return f"https://{self._host()}/v1/{self._engine}"

    def _create(self, *, fact: str, scope: dict[str, str]) -> None:
        self._request("POST", f"{self._base()}/memories", {"fact": fact, "scope": scope})

    def _retrieve(self, repo: str, *, kind: str, query: str = "") -> list[str]:
        body: dict[str, Any] = {"scope": {SCOPE_REPO: repo, SCOPE_KIND: kind}}
        if query:
            body["similaritySearchParams"] = {"searchQuery": query, "topK": RETRIEVE_TOP_K}
        payload = self._request("POST", f"{self._base()}/memories:retrieve", body)
        retrieved = payload.get("retrievedMemories") or ()
        return [
            str(item.get("memory", {}).get("fact", ""))
            for item in retrieved
            if item.get("memory", {}).get("fact")
        ]

    def _memory_names(self, repo: str, *, kind: str) -> list[str]:
        payload = self._request("GET", f"{self._base()}/memories")
        wanted = {SCOPE_REPO: repo, SCOPE_KIND: kind}
        return [
            str(memory["name"])
            for memory in payload.get("memories") or ()
            if memory.get("name") and memory.get("scope") == wanted
        ]

    def _request(self, method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return self._transport.request(method, url, body)
        except MemoryUnavailableError:
            raise
        except Exception as exc:
            raise MemoryUnavailableError(f"{method} {url} failed: {exc}") from exc


class _AuthorizedTransport:
    """Google-signed requests over the standard library.

    Credentials are resolved once and refreshed on demand; a long-lived worker
    outlives an access token.
    """

    __slots__ = ("_credentials",)

    def __init__(self) -> None:
        self._credentials: Any | None = None

    def request(self, method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self._token()
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise MemoryUnavailableError(f"{exc.code} from Memory Bank: {detail}") from exc

    def _token(self) -> str:
        import google.auth
        import google.auth.transport.requests

        if self._credentials is None:
            self._credentials, _ = google.auth.default(scopes=_SCOPES)
        if not self._credentials.valid:
            self._credentials.refresh(google.auth.transport.requests.Request())
        return str(self._credentials.token)


def _resolve_engine(env: dict[str, str]) -> str:
    """Full resource name for the configured engine."""
    engine = env[ENV_MEMORY_BANK_ENGINE].strip()
    if engine.startswith("projects/"):
        return engine
    project = cloud_project(env)
    location = env.get(ENV_MEMORY_BANK_LOCATION, "").strip() or DEFAULT_LOCATION
    return f"projects/{project}/locations/{location}/reasoningEngines/{engine}"


def _decode_profile(fact: str) -> RepositoryProfile | None:
    """Parse a profile fact, or `None` when it is not one.

    A memory that does not parse is skipped rather than raised on: the engine is
    shared institutional storage, and one malformed entry must not make a
    repository unreadable.
    """
    if not fact.startswith(PROFILE_MARKER):
        return None
    payload = fact[len(PROFILE_MARKER) :].strip()
    try:
        return RepositoryProfile.from_dict(json.loads(payload))
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("ignoring an unreadable repository profile in Memory Bank: %s", exc)
        return None


__all__ = ["VertexMemoryBank", "memory_bank_unavailable_reason"]
