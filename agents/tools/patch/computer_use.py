"""One Patch-agent verb: look at a page and act. Same loop as `run_command`.

Playwright is the mouse. Gemini Computer Use (when Vertex is wired) proposes
`click_at` / `type_text_at` from a screenshot. Without Vertex the step still
loads the page, writes a PNG + HTML dump, and scores a goal from visible text —
so the slice is exercisable when the model is absent.

The agent decides when to call this, interleaved with apply_patch / run_command.
This module does not start a product `npm run dev`; it serves the workspace
long enough to take a screenshot of `viewer/` (written by the fixture check).
"""

from __future__ import annotations

import json
import os
import re
import struct
import threading
import zlib
from collections.abc import Callable
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final
from urllib.error import URLError
from urllib.request import urlopen

from agents.config import AgentId
from agents.tools.results import ReasonCode, ok, refusal
from packages.schemas.change_manifest import ChangeManifest

AGENT: Final[AgentId] = AgentId.PATCH
DEFAULT_VIEWER: Final[str] = "/viewer/index.html"
MAX_CU_STEPS: Final[int] = 8
CONTRACT: Final[str] = "change_manifest"
_BINDING: Final[re.Pattern[str]] = re.compile(
    r"^(?:export\s+)?(?:const\s+)?MODEL\s*=\s*(['\"])([^'\"]*)\1",
    re.MULTILINE,
)


def _workspace(context: Any) -> Path | dict[str, Any]:
    sandbox = getattr(context, "sandbox", None)
    working = getattr(sandbox, "working_dir", None) if sandbox is not None else None
    if isinstance(working, Path):
        return working
    root = getattr(context, "workspace_root", None)
    if isinstance(root, Path):
        return root
    return refusal(
        ReasonCode.STAGE_NOT_READY,
        "computer_use_step needs a local workspace path; the session has none",
    )


def _png(path: Path, *, width: int = 8, height: int = 8) -> None:
    """Write a tiny valid PNG so evidence always has a screenshot file."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    raw = b"".join(b"\x00" + b"\x80\x90\xa0" * width for _ in range(height))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return


def _serve(root: Path) -> tuple[ThreadingHTTPServer, str]:
    handler = partial(_QuietHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}"


def _fetch(url: str) -> str:
    try:
        with urlopen(url, timeout=10) as response:
            return response.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError) as exc:
        return f"error: {type(exc).__name__}"


def _playwright_shot(url: str, dest: Path) -> str | None:
    """Take a real screenshot when Playwright + Chromium are installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1024, "height": 768})
            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            page.screenshot(path=str(dest), full_page=True)
            text = page.inner_text("body")
            browser.close()
        return text
    except Exception:
        return None


def _gemini_actions(goal: str, screenshot: Path) -> list[dict[str, Any]]:
    """Ask Gemini Computer Use for the next UI actions. Empty when unwired.

    Opt-in via PATCHAPI_COMPUTER_USE=1 so a leftover ADC client is not opened
    during deterministic or CI runs.
    """
    if os.environ.get("PATCHAPI_COMPUTER_USE") != "1":
        return []
    if os.environ.get("PATCHAPI_PATCH_LOOP_DETERMINISTIC") == "1":
        return []
    try:
        from google import genai
    except ImportError:
        return []
    try:
        client = genai.Client()
        image = screenshot.read_bytes()
        interaction = client.interactions.create(
            model="gemini-3.5-flash",
            input=[
                {"role": "user", "content": f"{goal}\nStay on this origin."},
                {"type": "image", "data": image},
            ],
            tools=[{"type": "computer_use", "environment": "browser"}],
        )
    except Exception:
        return []
    actions: list[dict[str, Any]] = []
    outputs = getattr(interaction, "outputs", None) or getattr(interaction, "output", None) or []
    for item in outputs:
        name = getattr(item, "name", None) or getattr(item, "type", None)
        args = getattr(item, "arguments", None) or getattr(item, "args", None) or {}
        if name:
            actions.append({"name": str(name), "arguments": dict(args) if args else {}})
    return actions


def _ensure_viewer(workspace: Path, retired: tuple[str, ...]) -> None:
    """Write viewer/ if the fixture check did not. Reads MODEL from lib/gemini.ts."""
    page = workspace / "viewer" / "index.html"
    if page.is_file():
        return
    source = workspace / "lib" / "gemini.ts"
    model = ""
    if source.is_file():
        match = _BINDING.search(source.read_text(encoding="utf-8"))
        model = match.group(2) if match else ""
    ok = bool(model) and model not in retired
    status = "ok" if ok else "error"
    line = f"ok:{model}" if ok else f"error:{model or 'unknown'} retired"
    page.parent.mkdir(parents=True, exist_ok=True)
    (page.parent / "model.json").write_text(
        json.dumps({"model": model, "status": status}, indent=2) + "\n", encoding="utf-8"
    )
    page.write_text(
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>Storygen model check</title></head><body>"
        f"<h1>Storygen model check</h1><p>status:{status}</p><p>{line}</p>"
        "</body></html>\n",
        encoding="utf-8",
    )


def _retired(context: Any) -> tuple[tuple[str, ...], str | None]:
    manifest = context.output(CONTRACT)
    if isinstance(manifest, ChangeManifest):
        return tuple(manifest.affected_identifiers), manifest.recommended_replacement
    return (), None


def _goal_met(text: str, retired: tuple[str, ...], replacement: str | None) -> bool:
    lower = text.lower()
    if any(identifier.lower() in lower for identifier in retired):
        return False
    if "error:" in lower and "ok:" not in lower:
        return False
    if replacement and replacement.lower() in lower:
        return True
    return "ok:" in lower or "status" in lower


def build_computer_use_tools(context: Any) -> list[Callable[..., Any]]:
    """Build `computer_use_step` bound to this run."""

    def computer_use_step(goal: str, url: str = "") -> dict[str, Any]:
        """Open the workspace viewer, screenshot it, and optionally act.

        `url` empty means the fixture viewer (`/viewer/index.html`) on a
        loopback server of the sandbox workspace. Same agent as run_command.
        """
        if not (goal or "").strip():
            return refusal(ReasonCode.INVALID_CONTRACT, "computer_use_step needs a goal")
        workspace = _workspace(context)
        if isinstance(workspace, dict):
            return workspace

        evidence = getattr(context, "evidence_root", None)
        ui_dir = Path(evidence) / "ui" if isinstance(evidence, Path) else workspace / ".patchapi-ui"
        ui_dir.mkdir(parents=True, exist_ok=True)
        retired, _ = _retired(context)
        _ensure_viewer(workspace, retired)

        server, origin = _serve(workspace)
        try:
            target = url.strip() or f"{origin}{DEFAULT_VIEWER}"
            if not target.startswith(origin) and target.startswith("/"):
                target = origin + target
            if not target.startswith("http://127.0.0.1") and not target.startswith(
                "http://localhost"
            ):
                return refusal(
                    ReasonCode.POLICY_DENIED,
                    "computer_use_step only opens loopback URLs",
                    url=target,
                )
            screenshot = ui_dir / "screenshot.png"
            visible = _playwright_shot(target, screenshot)
            html = _fetch(target)
            if visible is None:
                visible = html
                _png(screenshot)
            (ui_dir / "page.html").write_text(html, encoding="utf-8")
            retired, replacement = _retired(context)
            actions = _gemini_actions(goal, screenshot)
            met = _goal_met(visible, retired, replacement)
            record = {
                "goal": goal,
                "url": target,
                "goal_met": met,
                "actions": actions,
                "playwright": screenshot.stat().st_size > 80,
            }
            (ui_dir / "actions.json").write_text(
                json.dumps(record, indent=2) + "\n", encoding="utf-8"
            )
            return ok(
                goal=goal,
                url=target,
                goal_met=met,
                screenshot=str(screenshot),
                actions=actions,
                visible_tail=visible[-800:],
                detail="viewer opened; Computer Use actions recorded when the model answered",
            )
        finally:
            server.shutdown()
            try:
                server.server_close()
            except OSError:
                pass

    return [computer_use_step]


__all__ = ["AGENT", "DEFAULT_VIEWER", "MAX_CU_STEPS", "build_computer_use_tools"]
