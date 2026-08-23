"""A run-scoped kubeconfig, without the Google Cloud SDK.

`gcloud container clusters get-credentials` is the documented way to do this and
the wrong dependency for the two places that now need it. A Cloud Run job would
have to carry the whole SDK — hundreds of megabytes and a Python runtime of its
own — to write one small file, and a developer machine would have to have gcloud
installed and logged in before a sandbox could open at all.

Everything gcloud writes is available directly: the cluster's endpoint and CA
come from the Container API, and the bearer token comes from Application Default
Credentials, which in Cloud Run is the job's own service account and locally is
whatever the developer already authenticated as. So this writes the file itself.

The credential is a bearer token with about an hour of life, which is shorter
than a remediation may take. `stale` exists so the caller can rewrite the file
mid-run rather than discovering the expiry as an unauthorized `kubectl exec`
somewhere in the middle of a patch.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:  # pragma: no cover
    from sandbox.gke.session import ClusterConfig

CONTAINER_API: Final[str] = "https://container.googleapis.com/v1"
SCOPE: Final[str] = "https://www.googleapis.com/auth/cloud-platform"
REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0

# Google's tokens last an hour. Rewriting at forty minutes leaves room for a
# long `kubectl exec` that started just before the check.
MAX_AGE_SECONDS: Final[float] = 40 * 60

CONTEXT: Final[str] = "patchapi-sandbox"


class KubeconfigError(RuntimeError):
    """The cluster could not be described, or no credentials were available."""


def access_token() -> str:
    """A bearer token for the ambient identity."""
    try:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(scopes=[SCOPE])
        credentials.refresh(google.auth.transport.requests.Request())
    except Exception as exc:
        raise KubeconfigError(f"no Google credentials are available: {exc}") from exc
    token = str(credentials.token or "")
    if not token:
        raise KubeconfigError("Google credentials produced no access token")
    return token


def describe(cluster: ClusterConfig, token: str) -> dict[str, Any]:
    """The cluster's endpoint and certificate authority."""
    url = (
        f"{CONTAINER_API}/projects/{cluster.project}"
        f"/locations/{cluster.location}/clusters/{cluster.cluster}"
    )
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise KubeconfigError(
            f"cannot describe cluster {cluster.cluster} ({cluster.location}): HTTP {exc.code}"
        ) from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise KubeconfigError(f"cannot reach the Container API: {exc}") from exc

    endpoint = str(payload.get("endpoint") or "")
    authority = str((payload.get("masterAuth") or {}).get("clusterCaCertificate") or "")
    if not endpoint or not authority:
        raise KubeconfigError(
            f"cluster {cluster.cluster} reported no endpoint or certificate authority"
        )
    return {"endpoint": endpoint, "authority": authority}


def write(cluster: ClusterConfig, path: Path) -> Path:
    """Write a kubeconfig for `cluster` at `path`, and return it.

    The file is written 0600 and lives under the session's own scratch
    directory, which is deleted with the session. It never touches `~/.kube`, so
    a run cannot read or disturb whatever the operator has configured there.
    """
    token = access_token()
    described = describe(cluster, token)

    path.parent.mkdir(parents=True, exist_ok=True)
    authority = path.parent / "cluster-ca.crt"
    authority.write_bytes(base64.b64decode(described["authority"]))
    authority.chmod(0o600)

    # kubectl reads YAML, and JSON is YAML. Emitting JSON avoids depending on a
    # YAML writer for a file with four keys.
    document = {
        "apiVersion": "v1",
        "kind": "Config",
        "current-context": CONTEXT,
        "clusters": [
            {
                "name": CONTEXT,
                "cluster": {
                    "server": f"https://{described['endpoint']}",
                    "certificate-authority": str(authority),
                },
            }
        ],
        "users": [{"name": CONTEXT, "user": {"token": token}}],
        "contexts": [
            {
                "name": CONTEXT,
                "context": {
                    "cluster": CONTEXT,
                    "user": CONTEXT,
                    "namespace": cluster.namespace,
                },
            }
        ],
    }
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    path.chmod(0o600)
    return path


def stale(path: Path, *, max_age_seconds: float = MAX_AGE_SECONDS) -> bool:
    """Whether the token in `path` is old enough to be worth replacing."""
    try:
        written = path.stat().st_mtime
    except OSError:
        return True
    return (time.time() - written) > max_age_seconds


__all__ = [
    "CONTEXT",
    "MAX_AGE_SECONDS",
    "KubeconfigError",
    "access_token",
    "describe",
    "stale",
    "write",
]
