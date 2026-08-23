"""Serving the provider bytes a pull request cites.

A PatchAPI pull request says "this migration is based on sha256:abc… of
https://ai.google.dev/…". That claim is only checkable if the digest resolves to
something a reviewer can fetch and re-hash themselves, which is what this route
is for and the reason `SourceSnapshot.content_uri` refuses schemes nobody can
dereference.

The response is deliberately inert. Captures are untrusted provider HTML, so
they are served as `text/plain` with sniffing disabled rather than as the
`text/html` they were fetched as — a release note is being shown as evidence,
not rendered as a page inside the console's origin.

No authentication: the content is a public provider page, addressed by the hash
of bytes the requester would have to already know to ask for.
"""

from __future__ import annotations

import re
from typing import Final

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from packages.state.snapshots import read_by_digest

router = APIRouter(prefix="/v1/evidence", tags=["evidence"])

_DIGEST = re.compile(r"^[0-9a-f]{64}$")

# Captures are immutable — the digest is the identity — so a reviewer, and any
# proxy between them, may keep one indefinitely.
_CACHE_CONTROL: Final[str] = "public, max-age=31536000, immutable"


@router.get("/{sha256}")
async def read_evidence(request: Request, sha256: str) -> Response:
    """Return the captured page whose contents hash to `sha256`."""
    digest = sha256.strip().lower()
    if not _DIGEST.match(digest):
        return JSONResponse({"detail": "not a sha256 digest"}, status_code=400)

    pool = getattr(request.app.state, "postgres_pool", None)
    if pool is None:
        return JSONResponse({"detail": "evidence store is unavailable"}, status_code=503)

    async with pool.acquire() as connection:
        capture = await read_by_digest(connection, digest)
    if capture is None:
        return JSONResponse({"detail": "no capture with that digest"}, status_code=404)

    return PlainTextResponse(
        capture["body"],
        headers={
            "Cache-Control": _CACHE_CONTROL,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{digest}.txt"',
            "X-Captured-From": capture["source_url"],
            "X-Captured-At": capture["retrieved_at"].isoformat(),
            "X-Captured-Media-Type": capture["media_type"],
        },
    )


__all__ = ["router"]
