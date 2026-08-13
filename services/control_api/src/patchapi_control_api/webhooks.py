"""Webhook secret resolution and signature verification.

Split from the route so the check is testable on bytes alone, and so the secret
has exactly one way into the process. Three rules hold here:

* The secret is never logged, never returned, and never placed in an error body.
  A verification failure says the signature did not match, and nothing else.
* Comparison is constant-time. A byte-at-a-time comparison of an HMAC leaks the
  expected digest to anyone who can time the endpoint.
* No secret means no acceptance. An unconfigured receiver refuses deliveries
  rather than trusting the sender (roadmap §14, fail closed).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import Final

SECRET_VAR: Final[str] = "PATCHAPI_GITHUB_WEBHOOK_SECRET"
SECRET_FILE_VAR: Final[str] = "PATCHAPI_GITHUB_WEBHOOK_SECRET_FILE"

# Gitignored, and mounted rather than baked into any image. Cloud Run supplies
# the secret through the environment variable above instead.
DEFAULT_SECRET_FILE: Final[str] = ".secrets/github-webhook-secret.txt"

SIGNATURE_HEADER: Final[str] = "X-Hub-Signature-256"
EVENT_HEADER: Final[str] = "X-GitHub-Event"
DELIVERY_HEADER: Final[str] = "X-GitHub-Delivery"

_SIGNATURE_PREFIX: Final[str] = "sha256="


class WebhookSecretMissingError(RuntimeError):
    """Nothing configured a webhook secret, so no delivery can be authenticated."""


def load_webhook_secret(env: dict[str, str] | None = None) -> str:
    """Return the shared secret GitHub signs deliveries with.

    Environment first so a deployment can supply it from Secret Manager without
    a writable filesystem; the gitignored file is the local-development path.
    """
    environ = os.environ if env is None else env
    value = environ.get(SECRET_VAR, "").strip()
    if value:
        return value
    path = Path(environ.get(SECRET_FILE_VAR, "").strip() or DEFAULT_SECRET_FILE)
    try:
        contents = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise WebhookSecretMissingError(
            f"no webhook secret: {SECRET_VAR} is unset and the secret file is unreadable "
            f"({type(exc).__name__})"
        ) from exc
    if not contents:
        raise WebhookSecretMissingError(
            f"no webhook secret: {SECRET_VAR} is unset and the secret file is empty"
        )
    return contents


def expected_signature(secret: str, body: bytes) -> str:
    """The `sha256=...` header value GitHub would send for `body`."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"{_SIGNATURE_PREFIX}{digest}"


def signature_matches(secret: str, body: bytes, header: str | None) -> bool:
    """Whether `header` is the signature for `body` under `secret`.

    A missing or malformed header is a mismatch, not an exception: an unsigned
    delivery and a wrongly signed one are both unauthenticated, and the caller
    answers them identically.
    """
    if not header or not header.startswith(_SIGNATURE_PREFIX):
        return False
    return hmac.compare_digest(header, expected_signature(secret, body))


__all__ = [
    "DEFAULT_SECRET_FILE",
    "DELIVERY_HEADER",
    "EVENT_HEADER",
    "SECRET_FILE_VAR",
    "SECRET_VAR",
    "SIGNATURE_HEADER",
    "WebhookSecretMissingError",
    "expected_signature",
    "load_webhook_secret",
    "signature_matches",
]
