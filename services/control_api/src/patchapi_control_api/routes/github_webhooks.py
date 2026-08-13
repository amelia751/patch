"""GitHub webhook receiver (`repo-indexer.md` §7.2).

The receiver verifies the delivery, publishes one bounded event, and returns.
It does not clone, diff, or scan: a monorepo push touching ten thousand files
would blow GitHub's delivery timeout and take the console's request loop with
it. Everything after the topic is the indexer worker's job.

Three properties this route is responsible for:

* **Authenticated.** An unsigned or wrongly signed delivery is refused before
  the body is parsed. The body is untrusted input until the HMAC says otherwise.
* **Bounded.** The published payload is five scalars — repository, branch, the
  two SHAs, and the installation. Repository content never travels in an event.
* **Idempotent.** The envelope's idempotency key is derived from
  `(repository, branch, after_sha)`, so a redelivered push is recognisably the
  same unit of work rather than a second index pass.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Final

from fastapi import APIRouter, HTTPException, Request, Response, status

from packages.events.publisher import publish_async
from packages.events.repo_events import branch_from_ref, repo_push_event
from patchapi_control_api.models import GitHubWebhookAck
from patchapi_control_api.webhooks import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    WebhookSecretMissingError,
    load_webhook_secret,
    signature_matches,
)

router = APIRouter(prefix="/github", tags=["github"])

# The label an operator sees in the 503 when nothing configured a secret. Named
# like the other dependency labels in `dependencies.py`.
WEBHOOK_SECRET: Final[str] = "github_webhook_secret"

PING_EVENT: Final[str] = "ping"
PUSH_EVENT: Final[str] = "push"

# GitHub reports a deleted branch as a push to the null SHA. There is no commit
# to index, and the branch's findings are retired by the removal path, not here.
_NULL_SHA: Final[str] = "0" * 40


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _installation_id(body: dict[str, Any]) -> int | None:
    installation = body.get("installation")
    if not isinstance(installation, dict):
        return None
    identifier = installation.get("id")
    return identifier if isinstance(identifier, int) else None


@router.post(
    "/webhooks",
    summary="Receive a signed GitHub webhook delivery",
    response_model=GitHubWebhookAck,
)
async def receive_github_webhook(request: Request, response: Response) -> GitHubWebhookAck:
    """Verify a delivery and enqueue the work it implies.

    Answers 202 for a push once the event is handed to the transport, 200 for
    the ping GitHub sends when the webhook is configured, and 202 for every
    other subscribed event — acknowledged, and deliberately not acted on.
    """
    body = await request.body()
    try:
        secret = load_webhook_secret()
    except WebhookSecretMissingError as exc:
        # Fail closed: with no secret the receiver cannot tell GitHub from
        # anyone else who found the URL, so it accepts nothing.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "dependency_unavailable",
                "dependency": WEBHOOK_SECRET,
                "reason": str(exc),
            },
        ) from exc

    if not signature_matches(secret, body, request.headers.get(SIGNATURE_HEADER)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_signature", "reason": f"{SIGNATURE_HEADER} did not verify"},
        )

    event = request.headers.get(EVENT_HEADER, "").strip().lower()
    delivery_id = request.headers.get(DELIVERY_HEADER, "").strip() or None

    if event == PING_EVENT:
        response.status_code = status.HTTP_200_OK
        return GitHubWebhookAck(event=PING_EVENT, delivery_id=delivery_id, enqueued=False)

    response.status_code = status.HTTP_202_ACCEPTED
    if event != PUSH_EVENT:
        return GitHubWebhookAck(
            event=event or "unknown",
            delivery_id=delivery_id,
            enqueued=False,
            reason="event is not subscribed to by the indexer",
        )

    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_payload", "reason": "body is not JSON"},
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_payload", "reason": "body is not a JSON object"},
        )

    repository_field = payload.get("repository")
    repository = (
        _string(repository_field.get("full_name")) if isinstance(repository_field, dict) else ""
    )
    ref = _string(payload.get("ref"))
    after_sha = _string(payload.get("after"))
    if not repository or not ref or not after_sha:
        # Never guess at a repository or a commit: an event naming the wrong
        # target would index a repository nobody pushed to.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_payload",
                "reason": "push payload needs repository.full_name, ref, and after",
            },
        )

    branch = branch_from_ref(ref)
    if branch is None:
        return GitHubWebhookAck(
            event=PUSH_EVENT,
            delivery_id=delivery_id,
            enqueued=False,
            reason=f"{ref} is not a branch",
        )
    if after_sha == _NULL_SHA:
        return GitHubWebhookAck(
            event=PUSH_EVENT,
            delivery_id=delivery_id,
            enqueued=False,
            reason="branch was deleted",
        )

    result = await publish_async(
        repo_push_event(
            repository=repository,
            branch=branch,
            before_sha=_string(payload.get("before")) or _NULL_SHA,
            after_sha=after_sha,
            installation_id=_installation_id(payload),
            occurred_at=datetime.now(UTC).isoformat(),
            delivery_id=delivery_id,
        )
    )
    return GitHubWebhookAck(
        event=PUSH_EVENT,
        delivery_id=delivery_id,
        enqueued=result.published,
        # `publisher` has already logged the failure with the topic and the
        # event id; this repeats only what the sender is allowed to know.
        reason=None if result.published else "accepted; the event transport did not acknowledge",
    )
