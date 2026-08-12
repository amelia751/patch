"""Request-scoped access to the wired GitHub client and the caller's identity.

The client is a constructor argument to `create_app`, not a module global, so a
test and the local vertical slice wire fakes without patching, and an unwired
service is a visible `None` that the routes refuse to work around.
"""

from typing import Annotated, Final

from fastapi import Header, Request

from patchapi_github_tools.config import AGENT_IDENTITY_HEADER, RUN_ID_HEADER
from patchapi_github_tools.errors import dependency_unavailable, unknown_agent
from patchapi_github_tools.github_rest import GitHubRest
from patchapi_github_tools.identity import is_known_agent

GITHUB_APP_INSTALLATION: Final[str] = "github_app_installation"


async def optional_github_client(request: Request) -> GitHubRest | None:
    """The wired client, or `None` when the App is not configured."""
    return getattr(request.app.state, "github", None)


def require_github_client(github: GitHubRest | None) -> GitHubRest:
    """The wired client, or a 503 naming the missing credentials.

    Deliberately not a FastAPI dependency: a dependency would run before the
    handler resolves the capability, and a forbidden operation must be refused
    as forbidden whether or not the App is configured.
    """
    if github is None:
        raise dependency_unavailable(
            GITHUB_APP_INSTALLATION,
            "the GitHub App is not configured; no GitHub call was attempted",
        )
    return github


async def require_agent_identity(
    agent: Annotated[str | None, Header(alias=AGENT_IDENTITY_HEADER)] = None,
) -> str:
    """The calling agent's identity, or a 401.

    An absent header is treated the same as an unrecognised one: the grant set
    is selected by identity, and there is no anonymous grant set.
    """
    name = (agent or "").strip()
    if not is_known_agent(name):
        raise unknown_agent(name, AGENT_IDENTITY_HEADER)
    return name


async def optional_run_id(
    run_id: Annotated[str | None, Header(alias=RUN_ID_HEADER)] = None,
) -> str | None:
    return (run_id or "").strip() or None
