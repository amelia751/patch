#!/usr/bin/env python3
"""Live proof that the pinned Gemini image model returns real image bytes.

    uv run --all-packages python scripts/smoke_gemini_image.py

Companion to `scripts/smoke_gemini_vertex.py`, which proves the reasoning model.
Together they are the two live checks setup.md T-gemini-live requires before the
Egaki migration can claim it has a replacement for Imagen 4.

Three outcomes, and only three. `PASS` means Vertex returned inline bytes that
carry an image file signature and those bytes are now on disk. `SKIP` means
credentials are genuinely absent and nothing was called. `FAIL` means the call
was attempted and did not satisfy the assertions. There is no path that prints
`PASS` without a response from Google, and none that accepts bytes it could not
identify as an image.

The artifact is written under `.secrets/` because the default location is
gitignored: generated media is evidence for a run, not source.

Exit codes: 0 PASS, 1 FAIL, 3 SKIP.
"""

import argparse
import base64
import binascii
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.providers.dotenv import (  # noqa: E402 - path setup must precede the import
    apply_defaults,
    read_env_files,
)
from packages.providers.google.config import (  # noqa: E402
    MINIMUM_IMAGE_GENERATION,
    VERTEX_SCOPES,
    GoogleProviderConfig,
    load_config,
    parse_gemini_generation,
    require_supported_image_model,
)
from packages.providers.google.errors import (  # noqa: E402
    GoogleProviderError,
    MissingCredentialsError,
    VertexCallError,
)
from packages.providers.google.vertex import credentials_available  # noqa: E402

EXIT_PASS: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_SKIP: Final[int] = 3

# Deterministic, cheap, and unmistakably an image if it renders at all.
DEFAULT_PROMPT: Final[str] = (
    "A single flat vector icon of an orange cat wearing a space helmet, "
    "centered on a plain white background."
)

DEFAULT_OUTPUT_DIR: Final[Path] = REPO_ROOT / ".secrets" / "smoke-artifacts"
DEFAULT_OUTPUT_STEM: Final[str] = "gemini-image-smoke"

# Longest error body echoed back. Provider errors are untrusted text.
_MAX_ERROR_CHARS: Final[int] = 600

# Below this an "image" is an error placeholder or a truncated response, not a
# generation worth calling proof.
_MIN_IMAGE_BYTES: Final[int] = 1024

# File signatures, checked on the decoded bytes rather than trusting the
# `mimeType` the provider claims.
_SIGNATURES: Final[tuple[tuple[str, str, bytes], ...]] = (
    ("PNG", ".png", b"\x89PNG\r\n\x1a\n"),
    ("JPEG", ".jpg", b"\xff\xd8\xff"),
    ("GIF", ".gif", b"GIF8"),
)


def _apply_repo_pins() -> Path:
    """Layer the repository's non-secret pins under the real environment."""
    apply_defaults(read_env_files([REPO_ROOT / ".env", REPO_ROOT / ".env.example"]))
    return REPO_ROOT


def _load_credentials(config: GoogleProviderConfig) -> Any:
    """Resolve service-account or ADC credentials for the Vertex scopes.

    Imported lazily so `--help` and import-time checks do not require google-auth.
    """
    try:
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError
        from google.oauth2 import service_account
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise MissingCredentialsError("google-auth is not installed in this environment") from exc

    key_path = config.credentials_path
    if key_path is not None:
        if not key_path.is_file():
            raise MissingCredentialsError(
                f"GOOGLE_APPLICATION_CREDENTIALS points at {key_path}, which does not exist"
            )
        return service_account.Credentials.from_service_account_file(
            str(key_path), scopes=list(VERTEX_SCOPES)
        )

    try:
        credentials, _ = google.auth.default(scopes=list(VERTEX_SCOPES))
    except DefaultCredentialsError as exc:
        raise MissingCredentialsError(
            "no Google application default credentials; set GOOGLE_APPLICATION_CREDENTIALS "
            "or run `gcloud auth application-default login`"
        ) from exc
    return credentials


def identify_image(data: bytes) -> tuple[str, str] | None:
    """Return `(format, suffix)` for recognized image bytes, else `None`.

    WebP is matched on the RIFF container rather than a fixed prefix, so it is
    handled separately from the simple signature table.
    """
    for name, suffix, magic in _SIGNATURES:
        if data.startswith(magic):
            return name, suffix
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "WEBP", ".webp"
    return None


def extract_inline_image(payload: Mapping[str, Any]) -> tuple[bytes, str]:
    """Return the first inline image part's decoded bytes and claimed mime type.

    Raises `VertexCallError` when the response carried no image, which is what a
    text-only or blocked completion looks like.
    """
    candidates: Sequence[Any] = payload.get("candidates") or []
    if not candidates:
        raise VertexCallError("Vertex response carried no candidates")
    parts: Sequence[Any] = (candidates[0].get("content") or {}).get("parts") or []
    for part in parts:
        if not isinstance(part, Mapping):
            continue
        inline = part.get("inlineData") or part.get("inline_data")
        if not isinstance(inline, Mapping):
            continue
        encoded = inline.get("data")
        if not isinstance(encoded, str) or not encoded:
            continue
        mime_type = inline.get("mimeType") or inline.get("mime_type") or "unknown"
        try:
            return base64.b64decode(encoded, validate=True), str(mime_type)
        except (binascii.Error, ValueError) as exc:
            raise VertexCallError(f"inline image data was not valid base64: {exc}") from exc
    finish_reason = candidates[0].get("finishReason")
    raise VertexCallError(
        f"Vertex returned no inline image part (finishReason={finish_reason!r}); "
        "the model answered with something other than an image"
    )


def generate_image(config: GoogleProviderConfig, prompt: str) -> tuple[bytes, str, str]:
    """Call the pinned image model once. Returns `(bytes, mime_type, model_version)`.

    The pin is re-checked here so an environment override cannot route image
    generation back to the model family this project exists to migrate off.
    """
    model_id = require_supported_image_model(config.image_model)
    url = config.generate_content_url(model_id)
    credentials = _load_credentials(config)

    import requests
    from google.auth.transport.requests import Request as AuthRequest

    credentials.refresh(AuthRequest())
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=config.timeout_seconds,
        )
    except requests.RequestException as exc:
        raise VertexCallError(f"Vertex request to {url} failed: {exc}") from exc

    if response.status_code != 200:
        raise VertexCallError(
            f"Vertex returned {response.status_code} for {model_id} at "
            f"{config.location}: {response.text[:_MAX_ERROR_CHARS]}",
            status_code=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise VertexCallError("Vertex returned a body that is not JSON") from exc

    model_version = payload.get("modelVersion")
    if not isinstance(model_version, str) or not model_version:
        raise VertexCallError("Vertex response carried no modelVersion; model identity unproven")
    data, mime_type = extract_inline_image(payload)
    return data, mime_type, model_version


def _resolve_output(explicit: str | None, suffix: str) -> Path:
    """Pick the artifact path, matching the extension to what was actually returned."""
    if explicit:
        return Path(explicit).expanduser()
    return DEFAULT_OUTPUT_DIR / f"{DEFAULT_OUTPUT_STEM}{suffix}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="prompt to send")
    parser.add_argument(
        "--output",
        default=None,
        help=(
            f"where to write the image (default: {DEFAULT_OUTPUT_DIR}/{DEFAULT_OUTPUT_STEM}.<ext>)"
        ),
    )
    parser.add_argument("--json", action="store_true", help="print the result as one JSON object")
    args = parser.parse_args(argv)

    base_dir = _apply_repo_pins()
    try:
        config = load_config(base_dir=base_dir)
    except GoogleProviderError as exc:
        print(f"FAIL: {exc}")
        return EXIT_FAIL

    reason = credentials_available(config)
    if reason is not None:
        print(f"SKIP: {reason}")
        return EXIT_SKIP

    print(f"calling {config.image_model} at {config.location} (project {config.require_project()})")
    try:
        data, mime_type, model_version = generate_image(config, args.prompt)
    except MissingCredentialsError as exc:
        print(f"SKIP: {exc}")
        return EXIT_SKIP
    except GoogleProviderError as exc:
        print(f"FAIL: {exc}")
        return EXIT_FAIL

    identified = identify_image(data)
    if identified is None:
        head = data[:8].hex()
        print(f"FAIL: returned {len(data)} bytes claiming {mime_type}, but the leading bytes ")
        print(f"      ({head}) match no known image format")
        return EXIT_FAIL
    image_format, suffix = identified

    if len(data) < _MIN_IMAGE_BYTES:
        print(f"FAIL: {image_format} payload is only {len(data)} bytes; too small to be a render")
        return EXIT_FAIL

    try:
        generation = parse_gemini_generation(model_version)
    except GoogleProviderError as exc:
        print(f"FAIL: {exc}")
        return EXIT_FAIL
    if generation < MINIMUM_IMAGE_GENERATION:
        minimum = ".".join(str(part) for part in MINIMUM_IMAGE_GENERATION)
        print(f"FAIL: served model {model_version} is older than the pinned minimum {minimum}")
        return EXIT_FAIL

    output = _resolve_output(args.output, suffix)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    written = output.stat().st_size
    if written != len(data):
        print(f"FAIL: wrote {written} bytes to {output} but the response carried {len(data)}")
        return EXIT_FAIL

    result = {
        "requested_model": config.image_model,
        "model_version": model_version,
        "mime_type": mime_type,
        "format": image_format,
        "bytes": written,
        "output": str(output),
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"  model_version: {model_version}")
        print(f"  mime_type:     {mime_type}")
        print(f"  format:        {image_format}")
        print(f"  bytes:         {written}")
        print(f"  output:        {output}")
    print(f"PASS: live Vertex call to {model_version} returned a {image_format} image")
    return EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())
