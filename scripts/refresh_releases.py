"""Run the release refresh loop against a local DSN.

    uv run --all-packages python scripts/refresh_releases.py

The loop itself lives in `packages.state.refresh`, because Cloud Scheduler runs
the same code as a Cloud Run job and a script under `scripts/` does not ship in
the image. This wrapper only resolves the local proxy DSN that the deployed job
gets from Secret Manager.
"""

import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DSN_FILE: Final[Path] = REPO_ROOT / ".secrets" / "database-url-proxy.txt"
EXIT_FAIL: Final[int] = 1


def main() -> int:
    from packages.state.refresh import main as refresh_main

    argv = sys.argv[1:]
    if not any(arg.startswith("--dsn") for arg in argv):
        if not DEFAULT_DSN_FILE.is_file():
            print(f"FAIL: no DSN at {DEFAULT_DSN_FILE}")
            return EXIT_FAIL
        argv = [*argv, "--dsn", DEFAULT_DSN_FILE.read_text(encoding="utf-8").strip()]
    return refresh_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
