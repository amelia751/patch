"""Command line entry point: index a checkout and emit the inventory as JSON.

The worker that a push webhook will eventually drive, exposed as a command so
the same code path can be run by hand against a local checkout and by the
verifier against a fixture tree.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from patchapi_repo_indexer.config import DEFAULT_PROVIDER
from patchapi_repo_indexer.errors import IndexerError
from patchapi_repo_indexer.index import build_inventory

_EXIT_OK = 0
_EXIT_USAGE = 2

_DESCRIPTION = "Build a deterministic API usage inventory for a local checkout."


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patchapi-repo-indexer", description=_DESCRIPTION)
    parser.add_argument("--root", required=True, type=Path, help="checkout to index")
    parser.add_argument(
        "--repository", required=True, help="repository full name, e.g. amelia751/egaki"
    )
    parser.add_argument(
        "--sha",
        required=True,
        help="40-character commit SHA the tree was read at; recorded on every row",
    )
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        help=f"provider whose pinned watchlist to use (default: {DEFAULT_PROVIDER})",
    )
    parser.add_argument(
        "--identifier",
        action="append",
        dest="identifiers",
        metavar="ID",
        help="literal identifier to search for; repeatable, overrides the watchlist",
    )
    parser.add_argument(
        "--changed-path",
        action="append",
        dest="changed_paths",
        metavar="PATH",
        help="repo-relative path to restrict the scan to; repeatable, marks the "
        "inventory as a partial changed-paths index",
    )
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    parser.add_argument("--indent", type=int, default=2, help="JSON indent (default: 2)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Index a checkout, write the inventory, and return a process exit code.

    An inventory with no usages is a successful run: a repository that does not
    use the watched identifiers is an answer, not a failure. Only a scan that
    could not be performed exits non-zero.
    """
    args = _parser().parse_args(argv)

    try:
        inventory = build_inventory(
            root=args.root,
            repository=args.repository,
            observed_sha=args.sha,
            provider=args.provider,
            identifiers=args.identifiers,
            changed_paths=args.changed_paths,
        )
    except (IndexerError, ValidationError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    # `sort_keys` is off: field order is the contract's own, and the models are
    # already deterministic, so two runs of the same commit produce identical
    # bytes either way.
    document = json.dumps(inventory.model_dump(mode="json"), indent=args.indent)
    if args.out is None:
        print(document)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(document + "\n", encoding="utf-8")
        print(
            f"wrote {args.out} — {len(inventory.usages)} usage(s) across "
            f"{inventory.files_scanned} file(s)",
            file=sys.stderr,
        )
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
