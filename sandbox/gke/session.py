"""A claim / exec / destroy session over GKE Agent Sandbox.

One run claims one sandbox, drives it over the exec API, and deletes the claim.
The claim is the lifetime handle: deleting it cascades to the Sandbox and its
Pod through the controller's owner reference, and it is the only cleanup path
that stops the billed workload
(`.local/research/gke-agent-sandbox-lifecycle.md` §1.4).

Two lifetime bounds, because one of them is not enough:

* `spec.lifecycle.shutdownTime` — an absolute expiry written at claim time, the
  only hard maximum the v1alpha1 CRD exposes. There is no `idleTimeoutSeconds`
  and no `ttlSecondsAfterFinished` on this API; do not add either.
* `close()` in a finally-equivalent — the normal path, so a sandbox lives for
  the length of a step rather than the length of the expiry window.

Exec goes through `kubectl exec` into the template's `sleep infinity` container.
The `k8s-agent-sandbox` SDK is deliberately not used: it speaks HTTP to a
runtime on port 8888 that the PatchAPI runner image does not serve.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from ..credentials import LIVE_VERIFICATION_CREDENTIALS
from ..session import (
    ExecutionResult,
    SandboxError,
    SandboxPathError,
    SandboxUnavailableError,
    resolve_within,
)
from . import kubeconfig

_GKE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _GKE_DIR.parents[1]
_CONFIG_ENV = _GKE_DIR / "config.env"
_CLAIM_MANIFEST = _GKE_DIR / "sandbox-claim.yaml"

# Substituted in the committed manifest. Both markers must disappear from the
# rendered claim; see `render_claim_manifest`.
_CLAIM_NAME_MARKER = "PATCHAPI_SANDBOX_CLAIM"
_SHUTDOWN_TIME_MARKER = "# PATCHAPI_SANDBOX_SHUTDOWN_TIME"

# The template mounts one emptyDir at /sandbox; the checkout under test lives in
# a subdirectory of it so session-owned scratch (the patch file, caches) is
# never mistaken for repository content.
_POD_WORKSPACE = PurePosixPath("/sandbox/workspace")
_RUNNER_CONTAINER = "runner"
_POD_LABEL_SELECTOR = "app.kubernetes.io/name=patchapi-sandbox-runner"
# The controller stamps the owning claim's UID on the pod. It is the only label
# that distinguishes concurrent sandboxes allocated from one template.
_CLAIM_UID_LABEL = "agents.x-k8s.io/claim-uid"

_DEFAULT_MAX_LIFETIME_SECONDS = 20 * 60
_DEFAULT_READY_TIMEOUT_SECONDS = 180.0
_DELETE_TIMEOUT_SECONDS = 180.0
_KUBECTL_TIMEOUT_SECONDS = 60.0
_MAX_CLAIM_NAME_LENGTH = 63

# Read and write through python3 rather than a shell redirect: `kubectl exec --
# sh -c '…'` would put a caller-controlled string in front of a shell inside the
# sandbox, and the whole point of this session is that only argv crosses the
# boundary. python3 is present in the runner image and asserted by the verifier.
# kubectl exec has no --workdir. LocalSession runs with cwd=workspace; without
# this wrapper `python3 generate.py` starts in the container root and exits 2.
_CHDIR_EXEC_PROGRAM = (
    "import os,sys\n"
    "root=sys.argv[1]\n"
    "if os.path.isdir(root):\n"
    "    os.chdir(root)\n"
    "os.execvp(sys.argv[2], sys.argv[2:])\n"
)
# Loads extra_env from a JSON file written over stdin (never argv), unlinks it,
# then execs. The live key must not appear on the kubectl command line.
_LIVE_ENV_EXEC_PROGRAM = (
    "import json,os,sys\n"
    "root,env_path=sys.argv[1],sys.argv[2]\n"
    "data=json.loads(open(env_path,encoding='utf-8').read())\n"
    "os.unlink(env_path)\n"
    "if not isinstance(data,dict):\n"
    "    raise SystemExit('live env is not an object')\n"
    "os.environ.update({str(k):str(v) for k,v in data.items()})\n"
    "if os.path.isdir(root):\n"
    "    os.chdir(root)\n"
    "os.execvp(sys.argv[3], sys.argv[3:])\n"
)
_PHASE_FILES = {
    "dependencies": "phase-dependency-install.yaml",
    "live_verification": "phase-live-verification.yaml",
}
_READ_PROGRAM = "import pathlib,sys; sys.stdout.write(pathlib.Path(sys.argv[1]).read_text())"
_WRITE_PROGRAM = (
    "import pathlib,sys; p=pathlib.Path(sys.argv[1]); "
    "p.parent.mkdir(parents=True, exist_ok=True); p.write_text(sys.stdin.read())"
)
# Reads a base64 gzipped tar from stdin and extracts it under argv[1].
#
# Members are checked and written one at a time rather than handed to
# `extractall`. `extractall(filter='data')` would say the same thing in one line,
# and the sandbox image runs Python 3.11.2, where that keyword does not exist —
# the alternative is `extractall` with no filter at all, which is the traversal
# that keyword was added to stop. The orchestrator writes this archive, so the
# check is defence in depth rather than the only guard; `write_tree` has already
# resolved every path against the workspace before sending.
#
# Base64 rather than raw bytes because `kubectl exec` stdin is plumbed here as
# text, and a binary pipe buys nothing on a tree this size.
_EXTRACT_PROGRAM = (
    "import base64,io,os,pathlib,sys,tarfile\n"
    "root=pathlib.Path(sys.argv[1]).resolve()\n"
    "root.mkdir(parents=True, exist_ok=True)\n"
    "blob=base64.b64decode(sys.stdin.read())\n"
    "with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as tar:\n"
    "    for member in tar.getmembers():\n"
    "        if not member.isfile():\n"
    "            raise SystemExit('refused non-file member %s' % member.name)\n"
    "        dest=pathlib.Path(os.path.normpath(str(root / member.name)))\n"
    "        if root not in dest.parents:\n"
    "            raise SystemExit('refused member outside the workspace: %s' % member.name)\n"
    "        dest.parent.mkdir(parents=True, exist_ok=True)\n"
    "        source=tar.extractfile(member)\n"
    "        dest.write_bytes(b'' if source is None else source.read())\n"
    "        os.chmod(dest, member.mode & 0o755)\n"
)

_ASSIGNMENT = re.compile(r'^([A-Z][A-Z0-9_]*)="?(.*?)"?$')
_DEFAULTED = re.compile(r"^\$\{([A-Z][A-Z0-9_]*):-(.*)\}$")
_NON_DNS1123 = re.compile(r"[^a-z0-9-]+")


class SandboxLeakError(SandboxError):
    """A claim survived `close()`; something is still billing."""


@dataclass(frozen=True)
class ClusterConfig:
    """Cluster coordinates, read from sandbox/gke/config.env."""

    project: str
    location: str
    cluster: str
    namespace: str


def load_cluster_config(path: Path | None = None) -> ClusterConfig:
    """Parse `config.env` so no cluster name is inlined at a call site.

    The file is shell, but only in the `NAME="${NAME:-default}"` form, so it is
    parsed rather than sourced: sourcing operator-supplied shell to learn a
    namespace is a needlessly large blast radius.
    """

    source = _CONFIG_ENV if path is None else path
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise SandboxUnavailableError(f"cannot read cluster config {source}: {exc}") from exc

    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGNMENT.match(stripped)
        if match is None:
            continue
        name, raw = match.group(1), match.group(2)
        defaulted = _DEFAULTED.match(raw)
        if defaulted is not None:
            values[name] = os.environ.get(defaulted.group(1), defaulted.group(2))
        else:
            values[name] = raw

    try:
        return ClusterConfig(
            project=values["PATCHAPI_GKE_PROJECT"],
            location=values["PATCHAPI_GKE_LOCATION"],
            cluster=values["PATCHAPI_GKE_CLUSTER"],
            namespace=values["PATCHAPI_SANDBOX_NAMESPACE"],
        )
    except KeyError as exc:
        raise SandboxUnavailableError(f"{source} does not define {exc.args[0]}") from exc


def claim_name_for(run_id: str) -> str:
    """Return a DNS-1123 claim name unique to `run_id`.

    Uniqueness is what lets many claims target one template concurrently; a
    shared name would make two runs contend for one object.
    """

    name = _NON_DNS1123.sub("-", f"patchapi-run-{run_id}".lower()).strip("-")
    name = re.sub(r"-{2,}", "-", name)[:_MAX_CLAIM_NAME_LENGTH].rstrip("-")
    if not name:
        raise ValueError(f"run_id {run_id!r} yields no DNS-1123 claim name")
    return name


def max_lifetime_seconds() -> int:
    """Hard claim lifetime, overridable per environment."""

    raw = os.environ.get("PATCHAPI_SANDBOX_MAX_LIFETIME_SEC")
    if raw is None:
        return _DEFAULT_MAX_LIFETIME_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"PATCHAPI_SANDBOX_MAX_LIFETIME_SEC={raw!r} is not an integer") from exc
    if value <= 0:
        raise ValueError("PATCHAPI_SANDBOX_MAX_LIFETIME_SEC must be positive")
    return value


def render_claim_manifest(
    run_id: str,
    *,
    lifetime_seconds: int | None = None,
    now: datetime | None = None,
    manifest_path: Path | None = None,
) -> tuple[str, str]:
    """Render the committed claim for one run.

    Returns `(claim_name, manifest_text)`. Both markers must be present in the
    source manifest: a claim applied without `shutdownTime` never expires, so
    failing to substitute is a leak and is raised, not warned about.
    """

    source = _CLAIM_MANIFEST if manifest_path is None else manifest_path
    text = source.read_text(encoding="utf-8")
    if _CLAIM_NAME_MARKER not in text:
        raise SandboxError(f"{source} has no {_CLAIM_NAME_MARKER} marker to substitute")
    if _SHUTDOWN_TIME_MARKER not in text:
        raise SandboxError(f"{source} has no {_SHUTDOWN_TIME_MARKER} marker to substitute")

    seconds = max_lifetime_seconds() if lifetime_seconds is None else lifetime_seconds
    moment = datetime.now(UTC) if now is None else now.astimezone(UTC)
    shutdown_time = (moment + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

    name = claim_name_for(run_id)
    rendered = text.replace(_CLAIM_NAME_MARKER, name).replace(
        _SHUTDOWN_TIME_MARKER, f'shutdownTime: "{shutdown_time}"'
    )
    return name, rendered


class GkeSession:
    """One sandbox, claimed for one run and destroyed with it."""

    def __init__(
        self,
        run_id: str,
        *,
        cluster: ClusterConfig | None = None,
        lifetime_seconds: int | None = None,
        ready_timeout_seconds: float = _DEFAULT_READY_TIMEOUT_SECONDS,
        scratch_root: Path | None = None,
    ) -> None:
        self._run_id = run_id
        self._cluster = load_cluster_config() if cluster is None else cluster
        self._lifetime_seconds = lifetime_seconds
        self._ready_timeout = ready_timeout_seconds
        self._claim_name = claim_name_for(run_id)
        # Cluster credentials are run-scoped and deleted with the session; they
        # never touch ~/.kube, mirroring scripts/verify_sandbox_gke.sh.
        default_root = _REPO_ROOT / "tmp-patchapi" / "sandbox-session"
        root = default_root if scratch_root is None else Path(scratch_root)
        self._scratch = root / self._claim_name
        self._kubeconfig = self._scratch / "kubeconfig"
        self._claim_uid: str | None = None
        self._pod: str | None = None
        self._applied = False
        self._closed = False
        self._phase_policies: list[str] = []

    # -- identity ---------------------------------------------------------

    @property
    def working_dir(self) -> PurePosixPath:
        return _POD_WORKSPACE

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def claim_name(self) -> str:
        return self._claim_name

    @property
    def claim_uid(self) -> str | None:
        return self._claim_uid

    @property
    def pod_name(self) -> str | None:
        return self._pod

    # -- lifecycle --------------------------------------------------------

    def open(self) -> GkeSession:
        """Claim a sandbox and block until its pod is Ready."""

        if self._closed:
            raise SandboxError(f"session {self._claim_name} is already closed")
        if self._applied:
            return self

        self._require_tools()
        self._scratch.mkdir(parents=True, exist_ok=True)
        self._authenticate()

        name, manifest = render_claim_manifest(
            self._run_id, lifetime_seconds=self._lifetime_seconds
        )
        manifest_file = self._scratch / "sandbox-claim.rendered.yaml"
        manifest_file.write_text(manifest, encoding="utf-8")

        applied = self._kubectl(["apply", "-f", str(manifest_file)])
        # The claim may exist even when apply reports failure, so cleanup is
        # armed before the result is inspected.
        self._applied = True
        if applied.returncode != 0:
            self.close()
            raise SandboxUnavailableError(f"cannot create claim {name}: {applied.stderr.strip()}")

        try:
            self._claim_uid = self._await_claim_uid()
            self._pod = self._await_ready_pod()
            made = self.execute(["mkdir", "-p", str(_POD_WORKSPACE)], timeout_seconds=30)
            if made.exit_code != 0:
                raise SandboxUnavailableError(
                    f"cannot create {_POD_WORKSPACE} in {self._pod}: {made.stderr.strip()}"
                )
        except BaseException:
            # Anything that goes wrong after apply still owns a billed pod.
            self.close()
            raise
        return self

    def close(self) -> None:
        """Delete the claim and prove the sandbox is gone. Safe to call twice."""

        if self._closed:
            return
        self._closed = True
        try:
            for policy_name in list(self._phase_policies):
                self.clear_network_phase(policy_name)
            if not self._applied:
                return
            self._kubectl(
                [
                    "delete",
                    "sandboxclaim",
                    self._claim_name,
                    "--ignore-not-found",
                    "--wait=true",
                    f"--timeout={int(_DELETE_TIMEOUT_SECONDS)}s",
                ],
                timeout=_DELETE_TIMEOUT_SECONDS + 30,
            )
            self._assert_claim_gone()
        finally:
            shutil.rmtree(self._scratch, ignore_errors=True)

    def __enter__(self) -> GkeSession:
        return self.open()

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- execution --------------------------------------------------------

    def execute(
        self,
        argv: list[str],
        timeout_seconds: float = 300,
        *,
        extra_env: Mapping[str, str] | None = None,
    ) -> ExecutionResult:
        """Run `argv` inside the sandbox container. Never a shell string."""

        if not argv:
            raise ValueError("argv must not be empty")
        pod = self._require_pod()
        if extra_env:
            unknown = sorted(set(extra_env) - LIVE_VERIFICATION_CREDENTIALS)
            if unknown:
                raise ValueError(
                    f"extra_env names outside the live-verification allowlist: {unknown}"
                )
            env_path = f"/tmp/{self._claim_name}.live-env.json"
            staged = self._exec_python(_WRITE_PROGRAM, env_path, stdin=json.dumps(dict(extra_env)))
            if staged.exit_code != 0:
                return staged
            completed = self._kubectl(
                [
                    "exec",
                    pod,
                    "-c",
                    _RUNNER_CONTAINER,
                    "--",
                    "python3",
                    "-c",
                    _LIVE_ENV_EXEC_PROGRAM,
                    str(_POD_WORKSPACE),
                    env_path,
                    *argv,
                ],
                timeout=timeout_seconds,
            )
        else:
            completed = self._kubectl(
                [
                    "exec",
                    pod,
                    "-c",
                    _RUNNER_CONTAINER,
                    "--",
                    "python3",
                    "-c",
                    _CHDIR_EXEC_PROGRAM,
                    str(_POD_WORKSPACE),
                    *argv,
                ],
                timeout=timeout_seconds,
            )
        if completed is _TIMED_OUT:
            return ExecutionResult(exit_code=-1, timed_out=True)
        return ExecutionResult(
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

    def apply_network_phase(self, phase: str) -> str:
        """Open a run-scoped egress policy. Caller must `clear_network_phase`."""
        filename = _PHASE_FILES.get(phase)
        if filename is None:
            raise ValueError(f"unknown network phase {phase!r}")
        uid = self._claim_uid
        if not uid:
            raise SandboxError(f"session {self._claim_name} has no claim uid yet")
        policy_name = f"phase-{phase.replace('_', '-')}-{self._claim_name}"
        text = (_GKE_DIR / filename).read_text(encoding="utf-8")
        rendered = text.replace("PATCHAPI_PHASE_POLICY_NAME", policy_name).replace(
            "PATCHAPI_SANDBOX_CLAIM_UID", uid
        )
        path = self._scratch / f"{policy_name}.yaml"
        path.write_text(rendered, encoding="utf-8")
        applied = self._kubectl(["apply", "-f", str(path)])
        if applied.returncode != 0:
            raise SandboxUnavailableError(
                f"cannot apply {phase} policy: {applied.stderr.strip()}"
            )
        self._phase_policies.append(policy_name)
        return policy_name

    def clear_network_phase(self, policy_name: str) -> None:
        self._kubectl(
            ["delete", "networkpolicy", policy_name, "--ignore-not-found", "--wait=true"],
            timeout=60,
        )
        self._phase_policies = [name for name in self._phase_policies if name != policy_name]

    def read_file(self, relpath: str) -> str:
        path = resolve_within(_POD_WORKSPACE, relpath)
        result = self._exec_python(_READ_PROGRAM, str(path))
        if result.exit_code != 0:
            raise SandboxPathError(f"cannot read {path} in {self._claim_name}: {result.stderr}")
        return result.stdout

    def write_file(self, relpath: str, content: str) -> None:
        path = resolve_within(_POD_WORKSPACE, relpath)
        result = self._exec_python(_WRITE_PROGRAM, str(path), stdin=content)
        if result.exit_code != 0:
            raise SandboxPathError(f"cannot write {path} in {self._claim_name}: {result.stderr}")

    def write_tree(self, tree: Path, relpaths: Sequence[str]) -> None:
        """Put many files into the workspace in one call.

        A pod's only write path was `write_file`, and a checkout went in a file at
        a time. Each one is a `kubectl exec`: a TLS handshake to the API server, a
        SPDY upgrade, a container attach. Measured on the demo tree that is 9s of
        API round-trips for 20 small files, which was the largest remaining wait
        before the agent's first action once the run itself stopped waiting for a
        container. One archive is one round-trip, so it does not grow with the
        repository.

        Paths are relative and resolved through the same guard as `write_file`, so
        a tree cannot place a file outside the workspace; extraction re-checks
        with tar's `data` filter, because the archive is what the pod trusts.

        Binary files are included. `write_file` could not carry them and skipped
        them, which quietly gave the sandbox a tree that was not the commit.
        """
        members = [(tree / relpath, relpath) for relpath in relpaths]
        for source, relpath in members:
            resolve_within(_POD_WORKSPACE, relpath)
            if not source.is_file():
                raise SandboxPathError(f"cannot stage {relpath}: not a file under {tree}")

        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for source, relpath in members:
                info = tar.gettarinfo(str(source), arcname=relpath)
                # Ownership and timestamps from the orchestrator's disk describe
                # nothing about the commit and would differ between a laptop and
                # Cloud Run. Mode is narrowed to the read/write bit so nothing
                # arrives executable that was not.
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                info.mode = 0o755 if info.mode & 0o100 else 0o644
                with source.open("rb") as handle:
                    tar.addfile(info, handle)

        payload = base64.b64encode(buffer.getvalue()).decode("ascii")
        result = self._exec_python(_EXTRACT_PROGRAM, str(_POD_WORKSPACE), stdin=payload)
        if result.exit_code != 0:
            raise SandboxPathError(
                f"cannot stage {len(members)} files into {self._claim_name}: {result.stderr}"
            )

    def apply_unified_diff(self, diff: str, timeout_seconds: float = 120) -> ExecutionResult:
        """Stage the diff in the pod and apply it with `git apply -p1`.

        `kubectl exec` gives git no working directory of its own, so the diff is
        written to a claim-scoped file and applied with `git -C`.
        """

        self._require_pod()
        diff_path = PurePosixPath("/tmp") / f"{self._claim_name}.diff"
        staged = self._exec_python(_WRITE_PROGRAM, str(diff_path), stdin=diff)
        if staged.exit_code != 0:
            return staged
        result = self.execute(
            [
                "git",
                "-C",
                str(_POD_WORKSPACE),
                "apply",
                "-p1",
                "--whitespace=nowarn",
                str(diff_path),
            ],
            timeout_seconds=timeout_seconds,
        )
        # The diff is evidence of what was attempted, but it belongs beside the
        # run record on the orchestrator, not in a sandbox that outlives it.
        self.execute(["rm", "-f", str(diff_path)], timeout_seconds=30)
        return result

    # -- internals --------------------------------------------------------

    def _require_pod(self) -> str:
        if self._closed:
            raise SandboxError(f"session {self._claim_name} is closed")
        if self._pod is None:
            raise SandboxError(f"session {self._claim_name} is not open")
        return self._pod

    def _require_tools(self) -> None:
        # gcloud is deliberately not required. Credentials are written directly
        # from Application Default Credentials, so the job image carries kubectl
        # and nothing else.
        if shutil.which("kubectl") is None:
            raise SandboxUnavailableError("kubectl is not installed")

    def _authenticate(self) -> None:
        try:
            kubeconfig.write(self._cluster, self._kubeconfig)
        except kubeconfig.KubeconfigError as exc:
            raise SandboxUnavailableError(str(exc)) from exc

    def _refresh_credentials(self) -> None:
        """Rewrite the kubeconfig before its token ages out mid-run.

        A remediation can outlive an access token. Discovering that as an
        unauthorized `kubectl exec` halfway through a patch would look like a
        sandbox fault, so the file is replaced on age instead.
        """
        if not self._applied or not kubeconfig.stale(self._kubeconfig):
            return
        try:
            kubeconfig.write(self._cluster, self._kubeconfig)
        except kubeconfig.KubeconfigError:
            # The existing token may still have minutes left; failing the call
            # that noticed is worse than letting it try.
            pass

    def _await_claim_uid(self) -> str:
        deadline = _deadline(self._ready_timeout)
        while True:
            result = self._kubectl(
                [
                    "get",
                    "sandboxclaim",
                    self._claim_name,
                    "-o",
                    "jsonpath={.metadata.uid}",
                ]
            )
            if result is not _TIMED_OUT and result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            if _expired(deadline):
                raise SandboxUnavailableError(f"claim {self._claim_name} never reported a UID")
            _sleep(2)

    def _await_ready_pod(self) -> str:
        deadline = _deadline(self._ready_timeout)
        last = ""
        while True:
            found = self._kubectl(
                [
                    "get",
                    "pods",
                    "-l",
                    f"{_CLAIM_UID_LABEL}={self._claim_uid}",
                    "-o",
                    "jsonpath={.items[0].metadata.name}",
                ]
            )
            pod = "" if found is _TIMED_OUT else found.stdout.strip()
            if pod:
                ready = self._kubectl(
                    ["wait", "--for=condition=Ready", f"pod/{pod}", "--timeout=10s"]
                )
                if ready is not _TIMED_OUT and ready.returncode == 0:
                    return pod
                last = "" if ready is _TIMED_OUT else ready.stderr.strip()
            if _expired(deadline):
                raise SandboxUnavailableError(
                    f"no Ready sandbox pod for claim {self._claim_name} "
                    f"within {self._ready_timeout:.0f}s: {last or 'no pod matched the claim UID'}"
                )
            _sleep(5)

    def _assert_claim_gone(self) -> None:
        """Fail loudly if the claim outlived its delete."""

        result = self._kubectl(
            [
                "get",
                "sandboxclaim",
                self._claim_name,
                "-o",
                "jsonpath={.metadata.deletionTimestamp}",
            ]
        )
        if result is _TIMED_OUT:
            raise SandboxLeakError(f"cannot confirm claim {self._claim_name} was deleted")
        if result.returncode != 0:
            return  # NotFound: the claim and its sandbox are gone.
        if result.stdout.strip():
            return  # Terminating: the controller owns the rest of the teardown.
        raise SandboxLeakError(
            f"claim {self._claim_name} still exists after delete; its sandbox is still billing"
        )

    def _exec_python(self, program: str, *args: str, stdin: str | None = None) -> ExecutionResult:
        pod = self._require_pod()
        argv = ["exec"]
        if stdin is not None:
            argv.append("-i")
        argv += [pod, "-c", _RUNNER_CONTAINER, "--", "python3", "-c", program, *args]
        completed = self._kubectl(argv, stdin=stdin)
        if completed is _TIMED_OUT:
            return ExecutionResult(exit_code=-1, timed_out=True)
        return ExecutionResult(
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

    def _kubectl(
        self,
        argv: list[str],
        *,
        stdin: str | None = None,
        timeout: float = _KUBECTL_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]:
        self._refresh_credentials()
        return self._run(
            ["kubectl", "-n", self._cluster.namespace, *argv], stdin=stdin, timeout=timeout
        )

    def _run(
        self,
        argv: list[str],
        *,
        stdin: str | None = None,
        timeout: float = _KUBECTL_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]:
        # These are control-plane calls made by the orchestrator, not by
        # generated code, so they inherit the operator's environment — with
        # KUBECONFIG forced to the run-scoped scratch file so a session can
        # never mutate or read ~/.kube.
        env = dict(os.environ)
        env["KUBECONFIG"] = str(self._kubeconfig)
        try:
            return subprocess.run(
                argv,
                input=stdin,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return _TIMED_OUT
        except OSError as exc:
            return subprocess.CompletedProcess(argv, 127, "", str(exc))


# Sentinel for "the control-plane call did not answer in time". Comparing
# against it by identity keeps the timeout path distinct from a command that
# legitimately exited non-zero.
_TIMED_OUT: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
    args=[], returncode=-1, stdout="", stderr="timed out"
)


def _deadline(seconds: float) -> float:
    return time.monotonic() + seconds


def _expired(deadline: float) -> bool:
    return time.monotonic() >= deadline


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


__all__ = [
    "ClusterConfig",
    "GkeSession",
    "SandboxLeakError",
    "SandboxUnavailableError",
    "claim_name_for",
    "load_cluster_config",
    "max_lifetime_seconds",
    "render_claim_manifest",
]
