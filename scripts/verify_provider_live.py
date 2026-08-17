"""Live register / connect / disconnect / reconnect against the running API."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.state.session import COOKIE_NAME, issue, load_session_secret

API = "http://127.0.0.1:8080"
WEB = "http://127.0.0.1:3000"
USER_ID = UUID("43aaf37a-4b7b-4064-a63f-1f0a02f4fe7f")
CATALOG_URL = "https://serviceusage.googleapis.com/v1/projects/patch-505223/services"
CHANGES_URL = (
    "https://console.cloud.google.com/bigquery"
    "?p=bigquery-public-data&d=google_cloud_release_notes&t=release_notes"
)


class Failed(RuntimeError):
    pass


def _request(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    cookie: str | None = None,
    origin: str = API,
) -> tuple[int, object, float]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = f"{COOKIE_NAME}={cookie}"
    req = urllib.request.Request(f"{origin}{path}", data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    elapsed = time.perf_counter() - started
    payload: object
    try:
        payload = json.loads(raw.decode() or "null")
    except json.JSONDecodeError:
        payload = raw.decode()[:200]
    return status, payload, elapsed


def expect(status: int, wanted: int, label: str, payload: object) -> None:
    if status != wanted:
        raise Failed(f"{label}: expected HTTP {wanted}, got {status}: {payload!r}")


def poll_connection(cookie: str, slug: str, kind: str, *, timeout: float = 120.0) -> tuple[dict, float]:
    started = time.perf_counter()
    last: dict = {}
    while time.perf_counter() - started < timeout:
        status, payload, _ = _request("GET", f"/api/providers/{slug}", cookie=cookie)
        expect(status, 200, f"GET {slug} while polling {kind}", payload)
        assert isinstance(payload, dict)
        last = (payload.get("connections") or {}).get(kind) or {}
        if last.get("status") in {"connected", "error"}:
            return last, time.perf_counter() - started
        time.sleep(1.5)
    raise Failed(f"{slug} {kind} still {last.get('status')!r} after {timeout:.0f}s")


def main() -> int:
    cookie = issue(USER_ID, load_session_secret(ROOT))
    report: list[str] = []

    def log(line: str) -> None:
        print(line, flush=True)
        report.append(line)

    status, me, elapsed = _request("GET", "/api/auth/me", cookie=cookie)
    expect(status, 200, "session", me)
    assert isinstance(me, dict)
    log(f"ok  session {me.get('email')}  {elapsed*1000:.0f}ms")

    status, unauth, elapsed = _request("POST", "/api/providers", body={"name": "Nope"})
    expect(status, 401, "register without session", unauth)
    log(f"ok  register unauthenticated → 401  {elapsed*1000:.0f}ms")

    status, google, elapsed = _request("GET", "/api/providers/google")
    expect(status, 200, "GET google", google)
    assert isinstance(google, dict)
    if google.get("owner") is not None:
        raise Failed(f"google has an owner: {google['owner']!r}")
    if google.get("slug") != "google":
        raise Failed("google slug missing")
    log(f"ok  GET google owner=null status={google.get('status')}  {elapsed*1000:.0f}ms")

    status, page, elapsed = _request("GET", "/provider", origin=WEB)
    expect(status, 200, "frontend /provider", page)
    html = page if isinstance(page, str) else json.dumps(page)
    if "provider" not in html.lower() and "No provider" not in html:
        # Next streams a client tree; the document still has to load.
        if "<html" not in html.lower() and "html" not in html.lower():
            raise Failed("frontend /provider did not return a page")
    log(f"ok  GET frontend /provider  {elapsed*1000:.0f}ms")

    slug = f"e2e-acme-{int(time.time())}"
    status, created, elapsed = _request(
        "POST",
        "/api/providers",
        cookie=cookie,
        body={
            "name": "E2E Acme",
            "slug": slug,
            "website": "",
            "contact_email": "",
            "category": "ai",
            "description": "Live register check. Optional website and email omitted.",
            "attested": True,
        },
    )
    expect(status, 201, "register", created)
    assert isinstance(created, dict)
    if created.get("slug") != slug:
        raise Failed(f"registered slug {created.get('slug')!r}")
    if not created.get("owner") or created["owner"].get("user_id") != str(USER_ID):
        raise Failed(f"registered owner {created.get('owner')!r}")
    log(f"ok  POST register {slug}  {elapsed*1000:.0f}ms")

    status, listing, elapsed = _request("GET", "/api/providers")
    expect(status, 200, "list providers", listing)
    assert isinstance(listing, dict)
    slugs = {row["slug"] for row in listing.get("providers") or []}
    if "google" not in slugs or slug not in slugs:
        raise Failed(f"list missing google or {slug}: {slugs}")
    log(f"ok  GET /api/providers has google + {slug}  {elapsed*1000:.0f}ms")

    status, bad, elapsed = _request(
        "POST",
        "/api/providers/google/connections",
        cookie=cookie,
        body={"kind": "catalog", "url": "https://cloud.google.com/apis"},
    )
    expect(status, 422, "bad catalog url", bad)
    log(f"ok  bad catalog URL → 422  {elapsed*1000:.0f}ms")

    for kind, url in (("catalog", CATALOG_URL), ("changes", CHANGES_URL)):
        status, current, _ = _request("GET", "/api/providers/google", cookie=cookie)
        expect(status, 200, "GET google before connect", current)
        assert isinstance(current, dict)
        existing = (current.get("connections") or {}).get(kind)
        if existing:
            status, _, elapsed = _request(
                "DELETE",
                f"/api/providers/google/connections/{kind}",
                cookie=cookie,
            )
            expect(status, 200, f"clear leftover {kind}", _)
            log(f"ok  cleared leftover {kind}  {elapsed*1000:.0f}ms")

        status, pending, elapsed = _request(
            "POST",
            "/api/providers/google/connections",
            cookie=cookie,
            body={"kind": kind, "url": url},
        )
        expect(status, 202, f"connect {kind}", pending)
        assert isinstance(pending, dict)
        if pending.get("status") != "pending":
            raise Failed(f"connect {kind} status {pending.get('status')!r}")
        log(f"ok  POST connect {kind} → pending  {elapsed*1000:.0f}ms")

        result, waited = poll_connection(cookie, "google", kind)
        if result.get("status") != "connected":
            raise Failed(f"{kind} ingest failed: {result}")
        log(f"ok  {kind} connected after {waited:.1f}s  source={result.get('source_url')}")

        if kind == "catalog":
            status, services, elapsed = _request("GET", "/api/providers/google/services")
            expect(status, 200, "services after connect", services)
            assert isinstance(services, dict)
            count = len(services.get("services") or [])
            if count == 0:
                raise Failed("catalog connected but services list is empty")
            names = {row.get("id") for row in services["services"]}
            log(f"ok  GET services {count} rows  {elapsed*1000:.0f}ms  has_storage={('storage.googleapis.com' in names)}")
        else:
            status, notes, elapsed = _request(
                "GET",
                "/api/providers/google/changes?limit=20&since=2026-07-19&until=2026-08-17",
            )
            expect(status, 200, "changes after connect", notes)
            assert isinstance(notes, dict)
            if notes.get("trust", {}).get("classification") != "untrusted_provider_input":
                raise Failed("changes missing untrusted flag")
            if int(notes.get("total") or 0) == 0 or not notes.get("changes"):
                raise Failed("changes connected but page is empty")
            log(f"ok  GET changes total={notes.get('total')} page={len(notes['changes'])}  {elapsed*1000:.0f}ms")

        status, gone, elapsed = _request(
            "DELETE",
            f"/api/providers/google/connections/{kind}",
            cookie=cookie,
        )
        expect(status, 200, f"disconnect {kind}", gone)
        log(f"ok  DELETE disconnect {kind}  {elapsed*1000:.0f}ms")

        if kind == "catalog":
            status, services, elapsed = _request("GET", "/api/providers/google/services")
            expect(status, 200, "services after disconnect", services)
            assert isinstance(services, dict)
            if services.get("services"):
                raise Failed("services still present after disconnect")
            log(f"ok  services empty after disconnect  {elapsed*1000:.0f}ms")
        else:
            status, notes, elapsed = _request("GET", "/api/providers/google/changes?limit=5")
            expect(status, 200, "changes after disconnect", notes)
            assert isinstance(notes, dict)
            if notes.get("changes") or int(notes.get("total") or 0):
                raise Failed("changes still present after disconnect")
            log(f"ok  changes empty after disconnect  {elapsed*1000:.0f}ms")

        status, pending, elapsed = _request(
            "POST",
            "/api/providers/google/connections",
            cookie=cookie,
            body={"kind": kind, "url": url},
        )
        expect(status, 202, f"reconnect {kind}", pending)
        result, waited = poll_connection(cookie, "google", kind)
        if result.get("status") != "connected":
            raise Failed(f"{kind} reconnect failed: {result}")
        log(f"ok  reconnect {kind} connected after {waited:.1f}s  accept={elapsed*1000:.0f}ms")

        if kind == "catalog":
            status, services, _ = _request("GET", "/api/providers/google/services")
            expect(status, 200, "services after reconnect", services)
            assert isinstance(services, dict) and services.get("services")
            log(f"ok  services back after reconnect  n={len(services['services'])}")
        else:
            status, notes, _ = _request("GET", "/api/providers/google/changes?limit=5")
            expect(status, 200, "changes after reconnect", notes)
            assert isinstance(notes, dict) and notes.get("changes")
            log(f"ok  changes back after reconnect  total={notes.get('total')}")

    status, again, elapsed = _request("GET", "/api/providers/google")
    expect(status, 200, "google still loaded after leave-equivalent GET", again)
    assert isinstance(again, dict) and again.get("slug") == "google"
    log(f"ok  leave-catalog equivalent: GET google still 200  {elapsed*1000:.0f}ms")

    status, registered, elapsed = _request("GET", f"/api/providers/{slug}")
    expect(status, 200, "registered provider still loaded", registered)
    assert isinstance(registered, dict)
    log(f"ok  GET registered {slug} still loaded  {elapsed*1000:.0f}ms")

    print("\nALL LIVE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Failed as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        raise SystemExit(1)
