"""Minimal consumer of a Gemini text model — the vertical-slice migration target.

Nothing here calls the network. The sandbox loop needs a target whose exit code
is decided entirely by the model identifier in the source, so that a passing run
proves the patch landed rather than proving a provider was reachable.

Retirement facts are pinned in demo/fixtures/google-gemini20-deprecation.json.
"""

import sys

MODEL = "gemini-2.0-flash"

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
