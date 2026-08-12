"""Derivation of the idempotency keys the control plane hands to dispatchers.

Roadmap §9 requires every externally visible action to carry a key that is a
pure function of the action's inputs, so replaying the same trigger converges
instead of opening a second run. Deriving the key here — rather than accepting
one from the caller — means two callers naming the same work cannot disagree
about whether it is the same work.
"""

from datetime import UTC, datetime
from hashlib import sha256

from patchapi_control_api.config import IDEMPOTENCY_KEY_NAMESPACE

# A literal that cannot appear in any of the hashed components, so the joined
# string cannot be forged into a different tuple of inputs.
_SEPARATOR = "\x1f"


def provider_check_key(provider_id: str, since: datetime | None) -> str:
    """Return the hex sha256 identifying one provider-check request.

    `requested_by` is deliberately excluded: two engineers asking for the same
    provider window are asking for the same work, and attributing the trigger
    must not create a duplicate run.

    `since` must carry a timezone. A naive timestamp would hash to a different
    key depending on where the caller runs, which is exactly the divergence
    idempotency exists to prevent.
    """
    if since is not None and since.tzinfo is None:
        raise ValueError("`since` must be timezone-aware to derive a stable idempotency key")
    window = since.astimezone(UTC).isoformat() if since is not None else ""
    payload = _SEPARATOR.join((IDEMPOTENCY_KEY_NAMESPACE, provider_id, window))
    return sha256(payload.encode("utf-8")).hexdigest()
