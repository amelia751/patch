"""Structured failures.

Every error the control plane returns carries a machine-readable `error` code,
because the dashboard and the fleet both branch on the reason a call failed —
"the state store is not wired" and "that run does not exist" are different
facts and must not both surface as an empty result.
"""

from typing import Final

from fastapi import HTTPException, status

DEPENDENCY_UNAVAILABLE: Final[str] = "dependency_unavailable"
DISPATCH_INTEGRITY: Final[str] = "dispatch_integrity"
RUN_NOT_FOUND: Final[str] = "run_not_found"


def dependency_unavailable(dependency: str, reason: str) -> HTTPException:
    """503 for a dependency the control plane needs but does not have.

    Fail closed: a missing workflow store or event transport means the caller
    is told the request was not performed, never that it succeeded.
    """
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"error": DEPENDENCY_UNAVAILABLE, "dependency": dependency, "reason": reason},
    )


def dispatch_integrity(expected_key: str, returned_key: str) -> HTTPException:
    """502 when a dispatcher acknowledges a key other than the one it was sent.

    The acknowledgement is the only evidence that the enqueued work matches the
    request; a mismatched key means deduplication downstream would key off
    something this service never derived, so the request is reported as failed.
    """
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "error": DISPATCH_INTEGRITY,
            "expected_idempotency_key": expected_key,
            "returned_idempotency_key": returned_key,
        },
    )


def run_not_found(run_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": RUN_NOT_FOUND, "run_id": run_id},
    )
