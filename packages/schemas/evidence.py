"""Evidence objects: hashed provider snapshots and run artifacts.

Evidence is what makes a PatchAPI pull request reviewable. Both models here
carry a content hash so a reviewer can confirm the bytes an agent reasoned over
are the bytes still on disk.
"""

from datetime import datetime
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, Field, field_validator

from packages.schemas.base import StrictModel
from packages.schemas.config import ALLOWED_EVIDENCE_URI_SCHEMES
from packages.schemas.enums import EvidenceKind
from packages.schemas.fields import NonEmptyLine, Sha256Hex


class SourceSnapshot(StrictModel):
    """A captured, hashed copy of an official provider page.

    Roadmap §15.4: the demo shows the live URL but runs against a snapshot, so
    site latency or an HTML rewrite cannot change what the agents ingested. The
    hash is mandatory — an unhashed snapshot is not evidence.
    """

    source_url: AnyHttpUrl
    retrieved_at: datetime
    content_uri: str = Field(
        description="Where the captured bytes live (gs://, https:// or file://)"
    )
    content_sha256: Sha256Hex
    media_type: str = "text/html"

    @field_validator("content_uri")
    @classmethod
    def _check_scheme(cls, value: str) -> str:
        scheme = urlsplit(value).scheme
        if scheme not in ALLOWED_EVIDENCE_URI_SCHEMES:
            allowed = ", ".join(ALLOWED_EVIDENCE_URI_SCHEMES)
            raise ValueError(f"content_uri scheme {scheme!r} is not one of: {allowed}")
        return value


class EvidenceRef(StrictModel):
    """Pointer to an artifact produced during a run."""

    kind: EvidenceKind
    uri: str
    sha256: Sha256Hex | None = None
    label: NonEmptyLine | None = None

    @field_validator("uri")
    @classmethod
    def _check_scheme(cls, value: str) -> str:
        scheme = urlsplit(value).scheme
        if scheme not in ALLOWED_EVIDENCE_URI_SCHEMES:
            allowed = ", ".join(ALLOWED_EVIDENCE_URI_SCHEMES)
            raise ValueError(f"evidence uri scheme {scheme!r} is not one of: {allowed}")
        return value
