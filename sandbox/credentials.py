"""Credentials a sandbox may observe, and only during live verification.

Names live here so the local session, the GKE session, and the plan loader
share one allowlist. A host `GITHUB_TOKEN` or `GOOGLE_APPLICATION_CREDENTIALS`
is never on this list, so it cannot leak by being added to the operator shell.
"""

from __future__ import annotations

from typing import Final

# The only environment variables a step may request, and only during
# live_verification. GOOGLE_GENERATIVE_AI_API_KEY is the Egaki / AI Studio
# path. GOOGLE_API_KEY is the same material under the older name.
LIVE_VERIFICATION_CREDENTIALS: Final[frozenset[str]] = frozenset(
    {
        "GOOGLE_API_KEY",
        "GOOGLE_GENERATIVE_AI_API_KEY",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_GENAI_USE_VERTEXAI",
    }
)
