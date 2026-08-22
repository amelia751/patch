"""Deterministic repository scanning helpers (roadmap §7.4, §11.3).

Layer A of impact analysis: literal identifier search with a stable ordering
and a path-derived usage classification, so the expensive reasoning layer sees
candidate snippets rather than an entire checkout.
"""

from packages.repo_scan.classify import (
    RUNTIME_USAGE_KINDS,
    UsageKind,
    classify_path,
)
from packages.repo_scan.config import SCANNER_VERSION
from packages.repo_scan.dependencies import (
    DependencyHit,
    is_manifest,
    parse_manifest,
)
from packages.repo_scan.scan import (
    IdentifierHit,
    ScanResult,
    scan_text,
    scan_tree,
    should_scan_file,
)

__all__ = [
    "RUNTIME_USAGE_KINDS",
    "SCANNER_VERSION",
    "DependencyHit",
    "IdentifierHit",
    "ScanResult",
    "UsageKind",
    "classify_path",
    "is_manifest",
    "parse_manifest",
    "scan_text",
    "scan_tree",
    "should_scan_file",
]
