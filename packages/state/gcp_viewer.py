"""Read Cloud Run metadata with a stored viewer service account.

The control plane holds the JSON only long enough to list services and, when
the identity has Secret Accessor, pull a named secret for live verification.
Payloads are never written back to Postgres.
"""

from __future__ import annotations

import json
from typing import Any

from packages.state.secret_manager import SecretStoreError


class GcpViewerError(RuntimeError):
    """The viewer identity could not complete a read."""


def _credentials(credentials_json: str) -> Any:
    try:
        info = json.loads(credentials_json)
    except json.JSONDecodeError as exc:
        raise GcpViewerError("stored connection is not valid JSON") from exc
    if not isinstance(info, dict):
        raise GcpViewerError("stored connection is not a service-account object")
    try:
        from google.oauth2 import service_account
    except ImportError as exc:  # pragma: no cover - deploy extra
        raise GcpViewerError("google-auth is not installed") from exc
    return service_account.Credentials.from_service_account_info(
        info,
        scopes=("https://www.googleapis.com/auth/cloud-platform",),
    )


def list_cloud_run_services(
    credentials_json: str,
    *,
    gcp_project_id: str,
    region: str,
) -> list[dict[str, Any]]:
    """Return service name, URL, and Secret Manager *refs* (not payloads)."""
    creds = _credentials(credentials_json)
    try:
        from google.auth.transport.requests import Request
    except ImportError as exc:  # pragma: no cover
        raise GcpViewerError("google-auth is not installed") from exc
    try:
        creds.refresh(Request())
    except Exception as exc:
        raise GcpViewerError(f"could not refresh viewer credentials: {type(exc).__name__}") from exc
    parent = f"projects/{gcp_project_id}/locations/{region}"
    url = f"https://run.googleapis.com/v2/{parent}/services"
    payload = _get_json(url, token=creds.token)
    out: list[dict[str, Any]] = []
    for service in payload.get("services") or []:
        if not isinstance(service, dict):
            continue
        refs: list[dict[str, str]] = []
        template = service.get("template") if isinstance(service.get("template"), dict) else {}
        for container in template.get("containers") or []:
            if not isinstance(container, dict):
                continue
            for env in container.get("env") or []:
                if not isinstance(env, dict):
                    continue
                source = env.get("valueSource") if isinstance(env.get("valueSource"), dict) else {}
                secret_ref = source.get("secretKeyRef") if isinstance(source.get("secretKeyRef"), dict) else {}
                env_name = env.get("name")
                secret_name = secret_ref.get("secret")
                if env_name and secret_name:
                    refs.append({"env_name": str(env_name), "secret_name": str(secret_name)})
        name = str(service.get("name") or "")
        short = name.rsplit("/", 1)[-1] if name else ""
        uri = service.get("uri")
        out.append(
            {
                "name": short or name,
                "url": str(uri) if uri else None,
                "secret_refs": refs,
            }
        )
    return out


def _get_json(url: str, *, token: str) -> dict[str, Any]:
    from urllib.error import HTTPError, URLError
    from urllib.request import Request as UrlRequest, urlopen

    request = UrlRequest(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 — Google API HTTPS
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise GcpViewerError(f"Cloud Run list failed ({exc.code})") from exc
    except URLError as exc:
        raise GcpViewerError(f"could not reach Cloud Run Admin API: {type(exc).__name__}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GcpViewerError("Cloud Run list returned non-JSON") from exc
    return parsed if isinstance(parsed, dict) else {}


def access_customer_secret(
    credentials_json: str,
    *,
    gcp_project_id: str,
    secret_name: str,
) -> str:
    """Read one customer secret version with the viewer identity.

    The return value must not be logged. Missing accessor IAM is a hard error
    so the broker can fail closed instead of inventing a key.
    """
    creds = _credentials(credentials_json)
    try:
        from google.cloud import secretmanager
    except ImportError as exc:  # pragma: no cover
        raise SecretStoreError("google-cloud-secret-manager is not installed") from exc
    resource = f"projects/{gcp_project_id}/secrets/{secret_name}/versions/latest"
    try:
        client = secretmanager.SecretManagerServiceClient(credentials=creds)
        response = client.access_secret_version(request={"name": resource})
    except Exception as exc:
        raise GcpViewerError(f"could not access {secret_name}: {type(exc).__name__}") from exc
    return response.payload.data.decode("utf-8")


def broker_live_env(
    credentials_json: str,
    *,
    gcp_project_id: str,
    region: str,
    services: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Build the live-verification allowlist from Cloud Run secret refs."""
    discovered = services if services is not None else list_cloud_run_services(
        credentials_json, gcp_project_id=gcp_project_id, region=region
    )
    env: dict[str, str] = {"GOOGLE_CLOUD_PROJECT": gcp_project_id, "GOOGLE_CLOUD_LOCATION": region}
    wanted = {"GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"}
    seen: set[str] = set()
    for service in discovered:
        for ref in service.get("secret_refs") or []:
            env_name = str(ref.get("env_name") or "")
            secret_name = str(ref.get("secret_name") or "")
            if env_name not in wanted or not secret_name or env_name in seen:
                continue
            env[env_name] = access_customer_secret(
                credentials_json,
                gcp_project_id=gcp_project_id,
                secret_name=secret_name,
            )
            seen.add(env_name)
    return env
