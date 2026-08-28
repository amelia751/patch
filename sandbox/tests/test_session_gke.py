"""Live GKE Agent Sandbox sessions: claim, exec, destroy — and destroy again.

This test costs money to run and is skipped, with a reason, whenever the
cluster is not reachable. It never asserts a sandbox behaviour it did not
observe: the post-condition is read back from the cluster with `kubectl`, not
inferred from the fact that `close()` returned.

Every test deletes its claims in a `finally`. A leaked claim is a Running pod
billed until a human notices.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sandbox.gke.session import (  # noqa: E402
    GkeSession,
    SandboxPathError,
    SandboxUnavailableError,
    load_cluster_config,
)

TEMPLATE_NAME = "patchapi-node22"
READY_TIMEOUT_SECONDS = 420.0
# Short enough that a claim leaked by a crashed test still expires on its own.
LIFETIME_SECONDS = 900


class Kube:
    """Read-only cluster access for the assertions, independent of a session."""

    def __init__(self, namespace: str, kubeconfig: Path) -> None:
        self.namespace = namespace
        self._env = {**os.environ, "KUBECONFIG": str(kubeconfig)}

    def run(self, *argv: str, timeout: float = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["kubectl", "-n", self.namespace, *argv],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=self._env,
        )

    def claim_names(self) -> list[str]:
        result = self.run("get", "sandboxclaims", "-o", "name")
        assert result.returncode == 0, result.stderr
        return [line.split("/", 1)[-1] for line in result.stdout.split()]


@pytest.fixture(scope="module")
def kube(tmp_path_factory):
    """Skip the whole module unless a live Agent Sandbox cluster answers."""

    for tool in ("gcloud", "kubectl"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} is not installed")

    config = load_cluster_config()
    kubeconfig = tmp_path_factory.mktemp("kube") / "kubeconfig"
    credentials = subprocess.run(
        [
            "gcloud",
            "container",
            "clusters",
            "get-credentials",
            config.cluster,
            "--location",
            config.location,
            "--project",
            config.project,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
        env={**os.environ, "KUBECONFIG": str(kubeconfig)},
    )
    if credentials.returncode != 0:
        pytest.skip(f"cluster {config.cluster} unreachable: {credentials.stderr.strip()[:400]}")

    client = Kube(config.namespace, kubeconfig)
    template = client.run("get", "sandboxtemplate", TEMPLATE_NAME, "-o", "name")
    if template.returncode != 0:
        pytest.skip(
            f"SandboxTemplate {TEMPLATE_NAME} absent from {config.namespace}: "
            f"{template.stderr.strip()[:400]}"
        )
    return client


def open_or_skip(session: GkeSession) -> GkeSession:
    try:
        return session.open()
    except SandboxUnavailableError as exc:
        pytest.skip(f"sandbox unavailable: {exc}")


def test_session_execs_then_destroys_its_claim(kube, worker_run_id):
    session = GkeSession(
        worker_run_id,
        ready_timeout_seconds=READY_TIMEOUT_SECONDS,
        lifetime_seconds=LIFETIME_SECONDS,
    )
    try:
        open_or_skip(session)
        assert session.claim_name in kube.claim_names()

        version = session.execute(["python3", "--version"], timeout_seconds=60)
        assert version.exit_code == 0, version.stderr
        assert "Python 3" in (version.stdout + version.stderr)

        session.write_file("greeting.txt", "hello\nimagen-4\n")
        assert session.read_file("greeting.txt") == "hello\nimagen-4\n"

        applied = session.apply_unified_diff(
            "--- a/greeting.txt\n"
            "+++ b/greeting.txt\n"
            "@@ -1,2 +1,2 @@\n"
            " hello\n"
            "-imagen-4\n"
            "+gemini-3.1-flash-image\n"
        )
        assert applied.exit_code == 0, applied.stderr
        assert session.read_file("greeting.txt") == "hello\ngemini-3.1-flash-image\n"

        claim_name = session.claim_name
    finally:
        session.close()

    assert claim_name not in kube.claim_names()


def test_two_sessions_run_concurrently_and_both_are_destroyed(kube, worker_run_id):
    first = GkeSession(
        f"{worker_run_id}-a",
        ready_timeout_seconds=READY_TIMEOUT_SECONDS,
        lifetime_seconds=LIFETIME_SECONDS,
    )
    second = GkeSession(
        f"{worker_run_id}-b",
        ready_timeout_seconds=READY_TIMEOUT_SECONDS,
        lifetime_seconds=LIFETIME_SECONDS,
    )
    names = [first.claim_name, second.claim_name]
    assert names[0] != names[1]
    try:
        open_or_skip(first)
        open_or_skip(second)

        # One template, two claims, two pods: the template is a blueprint, not
        # a mutex, and each session must be reading its own filesystem.
        assert first.pod_name != second.pod_name
        assert first.claim_uid != second.claim_uid

        first.write_file("who.txt", "first\n")
        second.write_file("who.txt", "second\n")
        assert first.read_file("who.txt") == "first\n"
        assert second.read_file("who.txt") == "second\n"

        live = kube.claim_names()
        assert set(names) <= set(live)
    finally:
        try:
            first.close()
        finally:
            second.close()

    remaining = kube.claim_names()
    assert not set(names) & set(remaining), remaining


def test_a_whole_tree_arrives_in_one_exec(kube, worker_run_id, tmp_path):
    """The staging path a run takes, against a real pod.

    Worth an integration test rather than a mocked one because the two things
    that can go wrong are both on the far side of `kubectl exec`: base64 over a
    text stdin, and tar's `data` filter refusing a member. Both would pass a test
    that stopped at the archive.
    """
    source = tmp_path / "checkout"
    (source / "lib").mkdir(parents=True)
    (source / "lib" / "gemini.ts").write_text('export const MODEL = "imagen-4";\n')
    (source / "package.json").write_text('{"name":"storygen"}\n')
    (source / "logo.png").write_bytes(bytes(range(256)))

    session = GkeSession(
        f"{worker_run_id}-tree",
        ready_timeout_seconds=READY_TIMEOUT_SECONDS,
        lifetime_seconds=LIFETIME_SECONDS,
    )
    try:
        open_or_skip(session)

        session.write_tree(source, ["lib/gemini.ts", "package.json", "logo.png"])

        assert session.read_file("lib/gemini.ts") == 'export const MODEL = "imagen-4";\n'
        assert session.read_file("package.json") == '{"name":"storygen"}\n'
        # Binary, which the per-file text write could not carry at all.
        listed = session.execute(
            ["python3", "-c", "import pathlib;print(len(pathlib.Path('logo.png').read_bytes()))"],
            timeout_seconds=60,
        )
        assert listed.exit_code == 0, listed.stderr
        assert listed.stdout.strip() == "256"
    finally:
        session.close()


def test_a_staged_tree_may_not_escape_the_workspace(kube, worker_run_id, tmp_path):
    source = tmp_path / "hostile"
    source.mkdir()
    session = GkeSession(
        f"{worker_run_id}-esc",
        ready_timeout_seconds=READY_TIMEOUT_SECONDS,
        lifetime_seconds=LIFETIME_SECONDS,
    )
    try:
        open_or_skip(session)
        with pytest.raises(SandboxPathError):
            session.write_tree(source, ["../escape.txt"])
    finally:
        session.close()


@pytest.fixture(scope="module")
def worker_run_id():
    """A short run id, so per-test suffixes survive DNS-1123 truncation."""

    return f"pytest-{os.getpid()}"
