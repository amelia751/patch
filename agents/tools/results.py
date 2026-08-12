"""The shape every PatchAPI tool returns.

One rule: a tool that cannot answer returns a refusal saying why, and never a
plausible guess. `refusal` is therefore the only way to fail — an exception
escaping a tool would reach the model as a framework error string, which reads
like an unavailable service rather than a decision.

Refusals carry a machine-readable `reason_code` because the orchestrator, not
the model, decides what a refusal means for the run. A model deciding that
`EVIDENCE_UNVERIFIABLE` is survivable is exactly the failure this product exists
to prevent.
"""

from enum import StrEnum
from typing import Any


class ReasonCode(StrEnum):
    """Why a tool declined. Fixed vocabulary; the orchestrator switches on it."""

    # The thing asked for does not exist in the material the tool can see.
    NOT_FOUND = "not_found"
    # A path or resource outside the root this tool is bound to.
    OUT_OF_SCOPE = "out_of_scope"
    # The run has no root for this stage yet (no workspace, no evidence).
    STAGE_NOT_READY = "stage_not_ready"
    # Provider evidence is absent or does not hash to what was claimed.
    EVIDENCE_UNVERIFIABLE = "evidence_unverifiable"
    # The agent's claim disagrees with the deterministic reading of the source.
    CONTRADICTS_SOURCE = "contradicts_source"
    # The values offered do not validate against the versioned contract.
    INVALID_CONTRACT = "invalid_contract"
    # Untrusted text tried to issue instructions.
    INJECTION_DETECTED = "injection_detected"
    # Deterministic policy said no.
    POLICY_DENIED = "policy_denied"
    # The capability is not wired in this deployment. Never a silent success.
    CAPABILITY_NOT_AVAILABLE = "capability_not_available"


def ok(**fields: Any) -> dict[str, Any]:
    """A successful tool result."""
    return {"status": "ok", **fields}


def refusal(reason_code: ReasonCode, message: str, **fields: Any) -> dict[str, Any]:
    """A structured refusal: what the tool would not do, and why."""
    return {
        "status": "refused",
        "reason_code": str(reason_code),
        "message": message,
        **fields,
    }


def is_refusal(result: Any) -> bool:
    """Whether `result` is a tool refusal."""
    return isinstance(result, dict) and result.get("status") == "refused"
