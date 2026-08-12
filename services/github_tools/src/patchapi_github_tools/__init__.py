"""Narrow GitHub App capability adapter (roadmap §7.3, §14).

Agents receive capabilities, never tokens. This service owns the GitHub App
private key, mints short-lived installation tokens, and exposes only the
approved read and write operations. Merge, administration, secret, and
branch-protection operations are not implemented and cannot be granted.
"""

from patchapi_github_tools.app import create_app
from patchapi_github_tools.wiring import build_github_client

__all__ = ["build_github_client", "create_app"]
