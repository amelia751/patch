"""Live proof that the pinned Gemini reasoning model answers.

    uv run python -m packages.providers.google.smoke

Three outcomes, and only three. `PASS` means a real Vertex call returned text
and reported a model identity at or above the pinned generation. `SKIP` means
credentials are genuinely absent, and is the only case where nothing was called.
`FAIL` means the call was attempted and did not satisfy the assertions. There is
no path that prints `PASS` without a response from Google.
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from packages.providers.dotenv import apply_defaults, read_env_files
from packages.providers.google.config import (
    MINIMUM_REASONING_GENERATION,
    load_config,
    parse_gemini_generation,
)
from packages.providers.google.errors import GoogleProviderError, MissingCredentialsError
from packages.providers.google.vertex import VertexClient, credentials_available

EXIT_PASS: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_SKIP: Final[int] = 3

# Deterministic and cheap: a fixed short reply is easy to assert on and costs
# almost nothing to run on every verification.
DEFAULT_PROMPT: Final[str] = 'Reply with exactly this JSON and nothing else: {"ping":"pong"}'

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


def _apply_repo_pins() -> Path:
    """Layer the repository's non-secret pins under the real environment.

    `.env` wins over `.env.example`, and anything already exported wins over
    both, so this makes a bare shell behave like a configured one without ever
    overriding an operator.
    """
    apply_defaults(read_env_files([_REPO_ROOT / ".env", _REPO_ROOT / ".env.example"]))
    return _REPO_ROOT


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="prompt to send")
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

    print(
        f"calling {config.reasoning_model} at {config.location} "
        f"(project {config.require_project()})"
    )
    try:
        response = VertexClient(config).generate_text(args.prompt)
    except MissingCredentialsError as exc:
        print(f"SKIP: {exc}")
        return EXIT_SKIP
    except GoogleProviderError as exc:
        print(f"FAIL: {exc}")
        return EXIT_FAIL

    if not response.text.strip():
        print(f"FAIL: {response.model_version} returned no text (finish={response.finish_reason})")
        return EXIT_FAIL

    try:
        generation = parse_gemini_generation(response.model_version)
    except GoogleProviderError as exc:
        print(f"FAIL: {exc}")
        return EXIT_FAIL
    if generation < MINIMUM_REASONING_GENERATION:
        minimum = ".".join(str(part) for part in MINIMUM_REASONING_GENERATION)
        print(
            f"FAIL: served model {response.model_version} is older "
            f"than the pinned minimum {minimum}"
        )
        return EXIT_FAIL

    if args.json:
        print(json.dumps(response.model_dump(), indent=2, sort_keys=True))
    else:
        print(f"  model_version: {response.model_version}")
        print(f"  finish_reason: {response.finish_reason}")
        print(f"  total_tokens:  {response.total_token_count}")
        print(f"  response_id:   {response.response_id}")
        print(f"  text:          {response.text.strip()[:200]}")
    print(f"PASS: live Vertex call to {response.model_version} returned text")
    return EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())
