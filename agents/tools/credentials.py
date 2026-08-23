"""Tools the model uses to discover a missing runtime secret and ask for it.

This is not a pre-flight gate. Patch or Verification reads the workspace,
notices a live call needs an env var, then calls `list_runtime_credentials`
(names and Cloud Run refs only) and, if the name is absent, calls
`request_runtime_credentials`. ADK wraps the request as a
`LongRunningFunctionTool` so the runner pauses until the operator adds the
secret or connects GCP. Payloads never come back through these tools.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final
from uuid import uuid4

from agents.config import MAX_UNTRUSTED_EXCERPT_CHARS, AgentId
from agents.context import RunContext
from agents.tools.results import ReasonCode, ok, refusal

_SECRET_NEEDS: Final[frozenset[str]] = frozenset({"secret", "gcp", "either"})

# Names a live Gemini / AI Studio call typically reads. The model still has to
# name the one it saw in the workspace; this set only shapes the "already
# present" check when it asked for a family rather than a single name.
VERIFIER_SECRET_NAMES: Final[frozenset[str]] = frozenset(
    {
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENERATIVE_AI_API_KEY",
    }
)

_NAME_LIMIT: Final[int] = 8


@dataclass(frozen=True, slots=True)
class RuntimeCredentialsInventory:
    """What the run can see in Secret Manager / Connect GCP. Never payloads."""

    secret_names: tuple[str, ...] = ()
    gcp_connected: bool = False
    cloud_run_env_names: tuple[str, ...] = ()
    gcp_project_id: str | None = None
    bound: bool = True
    detail: str = ""


def resolve_inventory(context: RunContext) -> RuntimeCredentialsInventory:
    """Return the inventory bound to `context`, refreshing a callable each call."""
    bound = context.credentials_inventory
    if bound is None:
        return RuntimeCredentialsInventory(
            bound=False,
            detail="this run has no Secret Manager view; treat every name as missing",
        )
    if callable(bound):
        resolved = bound()
        if isinstance(resolved, RuntimeCredentialsInventory):
            return resolved
        raise TypeError("credentials_inventory callable must return RuntimeCredentialsInventory")
    return bound


def _present_names(inventory: RuntimeCredentialsInventory) -> set[str]:
    return set(inventory.secret_names) | set(inventory.cloud_run_env_names)


def _names_ready(inventory: RuntimeCredentialsInventory, names: list[str]) -> bool:
    present = _present_names(inventory)
    wanted = {name for name in names if name}
    if wanted:
        return bool(wanted & present)
    return bool(present & VERIFIER_SECRET_NAMES)


def _request_ready(inventory: RuntimeCredentialsInventory, need: str, names: list[str]) -> bool:
    if not inventory.bound:
        return False
    if need == "gcp":
        return inventory.gcp_connected
    if need == "secret":
        return _names_ready(inventory, names)
    return inventory.gcp_connected or _names_ready(inventory, names)


def build_credentials_tools(context: RunContext, agent: AgentId) -> list[Callable[..., Any]]:
    """Build the Secret Manager inspect + operator-request tools for `agent`."""

    def list_runtime_credentials() -> dict[str, Any]:
        """List runtime secret *names* this project already has, and whether GCP is connected.

        Call this after you read workspace code that uses an API key or a
        Cloud Run env var. Returns names and Cloud Run env refs only — never
        a payload, a JSON key, or a path under .secrets. Compare the names
        you saw in the code to this list. If the one you need is missing,
        call request_runtime_credentials. Do not invent a value.
        """
        inventory = resolve_inventory(context)
        return ok(
            bound=inventory.bound,
            secret_names=list(inventory.secret_names),
            gcp_connected=inventory.gcp_connected,
            cloud_run_env_names=list(inventory.cloud_run_env_names),
            gcp_project_id=inventory.gcp_project_id,
            detail=inventory.detail,
        )

    def request_runtime_credentials(
        need: str,
        reason: str,
        names: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Pause the run and ask the operator for a missing runtime secret or GCP connection.

        Use this only after list_runtime_credentials showed the name is
        absent (or no project view is bound) and you cannot honestly finish
        a live test without it. This is a pause, not record_human_required:
        the operator will add the secret or connect GCP and the same run
        continues. Never include a secret value, a service-account JSON, or
        a filesystem path.

        `need` is `secret`, `gcp`, or `either`. `names` are the env var
        names you read in the workspace (for example GEMINI_API_KEY).
        `reason` is the file and why the live check needs it.
        """
        cleaned_need = need.strip().lower()
        if cleaned_need not in _SECRET_NEEDS:
            return refusal(
                ReasonCode.INVALID_CONTRACT,
                "need must be 'secret', 'gcp', or 'either'",
            )
        cleaned_names: list[str] = []
        for raw in names or []:
            candidate = str(raw).strip()
            if not candidate:
                continue
            if not candidate.replace("_", "").isalnum() or candidate[0].isdigit():
                return refusal(
                    ReasonCode.INVALID_CONTRACT,
                    f"{candidate!r} is not an environment-variable name",
                )
            cleaned_names.append(candidate)
            if len(cleaned_names) >= _NAME_LIMIT:
                break
        if cleaned_need in {"secret", "either"} and not cleaned_names:
            return refusal(
                ReasonCode.INVALID_CONTRACT,
                "names must include the env var you read in the workspace",
            )
        why = reason.strip()[:MAX_UNTRUSTED_EXCERPT_CHARS]
        if not why:
            return refusal(ReasonCode.INVALID_CONTRACT, "reason is required")

        inventory = resolve_inventory(context)
        if _request_ready(inventory, cleaned_need, cleaned_names):
            return ok(
                ready=True,
                need=cleaned_need,
                names=cleaned_names,
                message="the vault already has what this live check needs; continue",
            )

        label = cleaned_names[0] if cleaned_names else "a runtime secret"
        if cleaned_need == "gcp":
            message = (
                "This run is waiting on you. Connect GCP so the agent can continue."
            )
        elif cleaned_need == "secret":
            message = (
                f"This run is waiting on you. Add {label} so the agent can continue."
            )
        else:
            message = (
                f"This run is waiting on you. Connect GCP or add {label} "
                "so the agent can continue."
            )
        entry = {
            "hold_id": str(uuid4()),
            "agent": str(agent),
            "need": cleaned_need,
            "names": cleaned_names,
            "reason": why,
            "message": message,
        }
        context.operator_requests.append(entry)
        # None, not a pending dict: ADK's LongRunningFunctionTool then
        # pauses the runner, the same way its own get_user_choice does.
        # The hold lives on RunContext for the orchestrator.
        return None

    return [list_runtime_credentials, request_runtime_credentials]


__all__ = [
    "VERIFIER_SECRET_NAMES",
    "RuntimeCredentialsInventory",
    "build_credentials_tools",
    "resolve_inventory",
]
