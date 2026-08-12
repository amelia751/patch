"""Live Vertex `generateContent` client for the pinned reasoning model.

Kept to raw REST against a URL this module builds from pinned configuration, so
the endpoint that a run actually hit is readable in one place. That matters
here: Gemini 3.x is served from `locations/global`, and the regional hosts
return 404 for these model IDs.

This client only calls the model. It does not decide anything, and it never
substitutes a canned answer for a call it could not make — a missing credential
raises `MissingCredentialsError` so the caller can report an honest `SKIP`.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.providers.google.config import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    VERTEX_SCOPES,
    GoogleProviderConfig,
    require_supported_reasoning_model,
)
from packages.providers.google.errors import MissingCredentialsError, VertexCallError
from packages.schemas.base import StrictModel

# Longest error body echoed back to a caller. Provider errors are untrusted text
# and a full HTML page in a log is noise, not evidence.
_MAX_ERROR_CHARS: Final[int] = 600


class VertexTextResponse(StrictModel):
    """What a successful `generateContent` call returned.

    `model_version` is the identity the API reported, which is what a
    verification step should assert on — the requested ID only says what was
    asked for.
    """

    requested_model: str
    model_version: str
    text: str
    finish_reason: str | None = None
    total_token_count: int | None = None
    response_id: str | None = None


def _load_credentials(config: GoogleProviderConfig) -> Any:
    """Resolve service-account or ADC credentials, or say why we cannot.

    Imported lazily so importing this module — and therefore collecting the
    offline tests — does not require google-auth to be installed.
    """
    try:
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError
        from google.oauth2 import service_account
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise MissingCredentialsError("google-auth is not installed in this environment") from exc

    key_path: Path | None = config.credentials_path
    if key_path is not None:
        if not key_path.is_file():
            raise MissingCredentialsError(
                f"GOOGLE_APPLICATION_CREDENTIALS points at {key_path}, which does not exist"
            )
        try:
            return service_account.Credentials.from_service_account_file(
                str(key_path), scopes=list(VERTEX_SCOPES)
            )
        except (ValueError, KeyError) as exc:
            raise MissingCredentialsError(
                f"{key_path} is not a usable service-account key: {exc}"
            ) from exc

    try:
        credentials, _ = google.auth.default(scopes=list(VERTEX_SCOPES))
    except DefaultCredentialsError as exc:
        raise MissingCredentialsError(
            "no Google application default credentials; set GOOGLE_APPLICATION_CREDENTIALS "
            "or run `gcloud auth application-default login`"
        ) from exc
    return credentials


def credentials_available(config: GoogleProviderConfig) -> str | None:
    """Return `None` if a live call can be attempted, else the reason it cannot."""
    try:
        _load_credentials(config)
    except MissingCredentialsError as exc:
        return str(exc)
    if not config.project:
        return "no GCP project configured; set GCP_PROJECT (see .env.example)"
    return None


def extract_text(payload: Mapping[str, Any]) -> str:
    """Concatenate the visible text parts of the first candidate.

    Gemini 3.x returns thinking parts alongside the answer; those are marked and
    dropped here so a caller never mistakes reasoning tokens for the reply.
    """
    candidates: Sequence[Any] = payload.get("candidates") or []
    if not candidates:
        return ""
    parts: Sequence[Any] = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(
        part["text"]
        for part in parts
        if isinstance(part, Mapping)
        and not part.get("thought")
        and isinstance(part.get("text"), str)
    )


def parse_generate_content(
    payload: Mapping[str, Any], *, requested_model: str
) -> VertexTextResponse:
    """Turn a `generateContent` body into a typed response, or fail loudly."""
    text = extract_text(payload)
    model_version = payload.get("modelVersion")
    if not isinstance(model_version, str) or not model_version:
        raise VertexCallError("Vertex response carried no modelVersion; model identity unproven")
    candidates: Sequence[Any] = payload.get("candidates") or []
    finish_reason = candidates[0].get("finishReason") if candidates else None
    usage = payload.get("usageMetadata") or {}
    return VertexTextResponse(
        requested_model=requested_model,
        model_version=model_version,
        text=text,
        finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        total_token_count=usage.get("totalTokenCount"),
        response_id=payload.get("responseId"),
    )


class VertexClient:
    """Minimal `generateContent` caller bound to one resolved configuration."""

    def __init__(self, config: GoogleProviderConfig) -> None:
        self._config = config

    @property
    def config(self) -> GoogleProviderConfig:
        return self._config

    def generate_text(
        self,
        prompt: str,
        *,
        model: str | None = None,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        temperature: float = 0.0,
    ) -> VertexTextResponse:
        """Send one text prompt to the pinned reasoning model.

        The model pin is re-checked here rather than only at construction, so an
        explicit `model=` override cannot route PatchAPI reasoning to a
        generation the rules do not allow.
        """
        model_id = require_supported_reasoning_model(model or self._config.reasoning_model)
        url = self._config.generate_content_url(model_id)
        credentials = _load_credentials(self._config)

        import requests
        from google.auth.transport.requests import Request as AuthRequest

        credentials.refresh(AuthRequest())
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {credentials.token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self._config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise VertexCallError(f"Vertex request to {url} failed: {exc}") from exc

        if response.status_code != 200:
            raise VertexCallError(
                f"Vertex returned {response.status_code} for {model_id} at "
                f"{self._config.location}: {response.text[:_MAX_ERROR_CHARS]}",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise VertexCallError("Vertex returned a body that is not JSON") from exc
        return parse_generate_content(payload, requested_model=model_id)
