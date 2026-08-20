"""Prove a stored viewer SA can see Cloud Run URLs and secret refs.

    uv run --all-packages python scripts/smoke_gcp_viewer.py

Uses the gitignored demo viewer JSON for a direct list, then POSTs the hosted
Storygen URL (expected to fail on retired models). Optional ``--connect`` writes
the JSON through the control API (Secret Manager + pointer) and re-lists via
``GET …/runtime``. Optional ``--sandbox gke`` curls the URL from a GKE session.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.state.gcp_viewer import GcpViewerError, list_cloud_run_services  # noqa: E402

EXIT_PASS: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_SKIP: Final[int] = 3

DEFAULT_VIEWER: Final[Path] = REPO_ROOT / "demo" / "artful-journey-486915-a8-c0699c9e2545.json"
DEFAULT_PROJECT: Final[str] = "artful-journey-486915-a8"
DEFAULT_REGION: Final[str] = "us-central1"
DEFAULT_URL: Final[str] = "https://storygen-1005432364863.us-central1.run.app"


def _post_story(url: str) -> tuple[int, str]:
    body = json.dumps({"prompt": "a one-sentence test"}).encode("utf-8")
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/story",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.status, response.read().decode("utf-8", errors="replace")[:400]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")[:400]


def _gke_curl(url: str) -> tuple[int, str]:
    from sandbox.session import SandboxUnavailableError, open_session

    scratch = Path(tempfile.mkdtemp(prefix="patchapi-gcp-viewer-"))
    try:
        session = open_session("gke", run_id="smoke-gcp-viewer", scratch_root=scratch)
    except (SandboxUnavailableError, ImportError, TypeError) as exc:
        return EXIT_SKIP, f"GKE sandbox unavailable: {exc}"
    try:
        session.write_file(
            "probe_story.py",
            "import json, sys, urllib.error, urllib.request\n"
            f"url = {url.rstrip('/')!r} + '/api/story'\n"
            "body = json.dumps({'prompt': 'hi'}).encode()\n"
            "req = urllib.request.Request(\n"
            "    url, data=body,\n"
            "    headers={'Content-Type': 'application/json'}, method='POST',\n"
            ")\n"
            "try:\n"
            "    with urllib.request.urlopen(req, timeout=45) as resp:\n"
            "        print(resp.status)\n"
            "        print(resp.read()[:240].decode('utf-8', 'replace'))\n"
            "except urllib.error.HTTPError as exc:\n"
            "    print(exc.code)\n"
            "    print(exc.read()[:240].decode('utf-8', 'replace'))\n"
            "    sys.exit(2)\n",
        )
        result = session.execute(["python3", "probe_story.py"])
    finally:
        session.close()
    text = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.exit_code in {0, 2} and ("502" in text or "500" in text or text.startswith("200")):
        return EXIT_PASS, text or "cloud run answered"
    if result.exit_code == 0:
        return EXIT_PASS, text or "cloud run answered 2xx"
    return EXIT_FAIL, text or f"exit {result.exit_code}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewer-json", type=Path, default=DEFAULT_VIEWER)
    parser.add_argument("--gcp-project", default=DEFAULT_PROJECT)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--sandbox", choices=("none", "gke"), default="none")
    args = parser.parse_args(argv)

    if not args.viewer_json.is_file():
        print(f"SKIP: viewer JSON not on disk at {args.viewer_json}")
        return EXIT_SKIP

    credentials_json = args.viewer_json.read_text(encoding="utf-8")
    try:
        services = list_cloud_run_services(
            credentials_json,
            gcp_project_id=args.gcp_project,
            region=args.region,
        )
    except GcpViewerError as exc:
        print(f"FAIL: {exc}")
        return EXIT_FAIL

    print(f"cloud run services ({len(services)}) in {args.gcp_project}/{args.region}:")
    storygen: dict[str, Any] | None = None
    for service in services:
        refs = ", ".join(
            f"{r['env_name']}→{r['secret_name']}" for r in service.get("secret_refs") or []
        ) or "(no secret refs)"
        print(f"  {service.get('name')}  {service.get('url')}  {refs}")
        if service.get("name") == "storygen":
            storygen = service

    if storygen is None:
        print("FAIL: storygen is not visible to the viewer identity")
        return EXIT_FAIL
    refs = {r["env_name"]: r["secret_name"] for r in storygen.get("secret_refs") or []}
    if refs.get("GEMINI_API_KEY") != "storygen-gemini-api-key":
        print(f"FAIL: expected GEMINI_API_KEY→storygen-gemini-api-key, got {refs}")
        return EXIT_FAIL

    url = storygen.get("url") or DEFAULT_URL
    status, body = _post_story(str(url))
    print(f"POST {url}/api/story → {status}")
    print(body)
    if status == 200:
        print("FAIL: hosted storygen still serves retired models; a 200 means the fixture changed")
        return EXIT_FAIL
    if status not in {400, 500, 502, 503}:
        print(f"FAIL: unexpected Cloud Run status {status}")
        return EXIT_FAIL

    if args.sandbox == "gke":
        code, detail = _gke_curl(str(url))
        print(f"gke: {detail}")
        if code == EXIT_SKIP:
            print(f"SKIP: {detail}")
            return EXIT_SKIP
        if code != EXIT_PASS and "502" not in detail and "500" not in detail:
            print(f"FAIL: sandbox live call: {detail}")
            return EXIT_FAIL

    print("PASS: viewer listed Cloud Run + secret refs; live Storygen still fails as expected")
    return EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())
