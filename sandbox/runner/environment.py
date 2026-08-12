"""Environment construction for sandboxed steps.

The local runner cannot enforce gVisor or default-deny networking — GKE Agent
Sandbox does that (roadmap §13.2, §13.3). What it can enforce, identically in
both environments, is the credential rule from §13.4: generated code never sees
a GitHub key, an admin token, or a control-plane credential. That rule is
implemented here as a build-from-nothing allowlist, not a scrub-the-bad-ones
denylist, so a credential added to the developer's shell tomorrow is excluded by
default rather than leaked by omission.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from .config import Step

# Inherited verbatim when present: the minimum needed for a toolchain to run at
# all. Deliberately excludes every *_TOKEN, *_KEY, and credential-file pointer.
_INHERITED_BASE_VARS: tuple[str, ...] = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TERM",
    "SHELL",
    "SYSTEMROOT",
)


def build_step_environment(
    step: Step,
    *,
    workspace: Path,
    run_id: str,
    parent_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return the exact environment a step is allowed to observe.

    HOME and TMPDIR are redirected into the disposable workspace so a tool that
    writes a cache or a credential helper cannot reach the operator's home
    directory.
    """

    parent = os.environ if parent_environment is None else parent_environment
    env: dict[str, str] = {
        name: parent[name] for name in _INHERITED_BASE_VARS if parent.get(name) is not None
    }
    env.setdefault("PATH", os.defpath)

    home = workspace / ".sandbox-home"
    tmp = workspace / ".sandbox-tmp"
    env["HOME"] = str(home)
    env["TMPDIR"] = str(tmp)
    env["PATCHAPI_SANDBOX"] = "1"
    env["PATCHAPI_RUN_ID"] = run_id
    env["PATCHAPI_STEP"] = step.name
    env["PATCHAPI_NETWORK_PHASE"] = step.phase

    # Validated at plan load; released only for the one step that declared it.
    for name in step.credentials:
        value = parent.get(name)
        if value is not None:
            env[name] = value

    return env


def missing_credentials(
    step: Step, parent_environment: Mapping[str, str] | None = None
) -> list[str]:
    """Credentials a step declared that are absent from the host environment.

    Callers fail closed on a non-empty result rather than running a live
    verification step that would silently degrade to an offline no-op.
    """

    parent = os.environ if parent_environment is None else parent_environment
    return [name for name in step.credentials if not parent.get(name)]
