"""No-network gate for the model identifier in lib/gemini.ts.

The sandbox loop needs a target whose exit code is decided entirely by that
identifier, so a passing run proves the patch landed rather than proving a
provider was reachable. This file reads the binding; it does not declare one.

Retirement facts are pinned in demo/fixtures/google-gemini20-deprecation.json
when this tree is used as a PatchAPI fixture.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_BINDING = re.compile(
    r"^(?:export\s+)?(?:const\s+)?MODEL\s*=\s*(['\"])([^'\"]*)\1",
    re.MULTILINE,
)

# Shut down 2026-06-01 per https://ai.google.dev/gemini-api/docs/deprecations.
# Duplicated here rather than imported so the check survives being run alone
# inside a sandbox workspace.
RETIRED_MODELS: frozenset[str] = frozenset(
    {
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash-lite-001",
    }
)


def load_model(source: str | None = None) -> str:
    text = source if source is not None else _entrypoint().read_text(encoding="utf-8")
    match = _BINDING.search(text)
    if match is None:
        raise SystemExit("error: lib/gemini.ts does not assign MODEL")
    return match.group(2)


def _entrypoint() -> Path:
    return Path(__file__).resolve().parent / "lib" / "gemini.ts"


MODEL = load_model()


def main() -> int:
    """Return 0 when MODEL is still served, 1 when it has been shut down."""
    if MODEL in RETIRED_MODELS:
        print(
            f"error: {MODEL} was shut down on 2026-06-01 and no longer resolves",
            file=sys.stderr,
        )
        return 1
    print(f"ok:{MODEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
