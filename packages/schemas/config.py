"""Pinned contract versions and shared limits.

Every version and numeric bound the contracts depend on is declared here so a
call site never inlines one. Bumping a contract means editing this file and the
models in the same change.
"""

from types import MappingProxyType
from typing import Final

# Contract name -> pinned schema version. Additive field changes keep the
# version; any change that can break a consumer bumps it, and the agents that
# emit or read the contract are updated in the same batch.
CONTRACT_VERSIONS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "change_manifest": "1.0.0",
        "impact_report": "1.0.0",
        "policy_decision": "1.0.0",
        "patch_plan": "1.0.0",
        "verification_report": "1.0.0",
    }
)

# Roadmap §8.4: a run gets a bounded number of patch attempts, each starting
# from the same pinned base SHA.
MAX_PATCH_ATTEMPTS: Final[int] = 3

# Longest excerpt an Impact finding may carry. Findings are evidence pointers,
# not a channel for shipping repository source into agent prompts.
MAX_FINDING_EXCERPT_CHARS: Final[int] = 2000

MAX_MIGRATION_SUMMARY_CHARS: Final[int] = 4000

# Evidence URIs are restricted to the artifact stores PatchAPI controls.
ALLOWED_EVIDENCE_URI_SCHEMES: Final[tuple[str, ...]] = ("gs", "https", "file")


class UnknownContractError(KeyError):
    """Raised when a model asks for a version that is not pinned here."""


def contract_version(contract: str) -> str:
    """Return the pinned schema version for `contract`.

    Fails closed: an unpinned contract name is a programming error, never a
    silently defaulted version.
    """
    try:
        return CONTRACT_VERSIONS[contract]
    except KeyError as exc:
        known = ", ".join(sorted(CONTRACT_VERSIONS))
        raise UnknownContractError(
            f"no pinned schema version for contract {contract!r}; known contracts: {known}"
        ) from exc
