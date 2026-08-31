"""ast-grep integration — Layer B structural confirmation (repo-indexer.md §5.3)."""

from patchapi_repo_indexer.astgrep.runner import (
    DEFAULT_RULE_DIR,
    StructuralMatch,
    available,
    configured_rule_dir,
    rule_files,
    rule_root,
    scan_files,
)

__all__ = [
    "DEFAULT_RULE_DIR",
    "StructuralMatch",
    "available",
    "configured_rule_dir",
    "rule_files",
    "rule_root",
    "scan_files",
]
