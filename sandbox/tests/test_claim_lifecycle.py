"""The rendered claim is the only thing standing between a crash and a leak.

`shutdownPolicy: Delete` describes what happens at expiry; without
`shutdownTime` there is no expiry, and the v1alpha1 CRD has no idle timeout to
fall back on. These tests assert on the rendered manifest rather than on the
committed one, because the committed manifest must never carry an absolute
timestamp.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sandbox.gke.session import (  # noqa: E402
    ClusterConfig,
    SandboxError,
    claim_name_for,
    load_cluster_config,
    max_lifetime_seconds,
    render_claim_manifest,
)

CLAIM_MANIFEST = REPO_ROOT / "sandbox" / "gke" / "sandbox-claim.yaml"
DNS_1123 = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
SHUTDOWN_TIME = re.compile(r'^\s*shutdownTime:\s*"?([0-9T:\-]+Z)"?\s*$', re.MULTILINE)


def rendered_shutdown_time(manifest: str) -> datetime:
    match = SHUTDOWN_TIME.search(manifest)
    assert match is not None, f"no shutdownTime in rendered claim:\n{manifest}"
    return datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def fields_of(manifest: str) -> str:
    """The manifest with comments removed, so prose cannot satisfy an assertion."""

    return "\n".join(line for line in manifest.splitlines() if not line.strip().startswith("#"))


def test_committed_manifest_carries_no_absolute_timestamp():
    text = CLAIM_MANIFEST.read_text(encoding="utf-8")

    assert "shutdownPolicy: Delete" in fields_of(text)
    assert SHUTDOWN_TIME.search(text) is None
    assert "# PATCHAPI_SANDBOX_SHUTDOWN_TIME" in text
    # Neither field exists on the GKE v1alpha1 CRD; a structural schema would
    # prune them and the claim would silently never expire.
    assert "ttlSecondsAfterFinished" not in fields_of(text)
    assert "idleTimeoutSeconds" not in fields_of(text)


def test_rendered_claim_deletes_on_expiry_and_expires():
    now = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

    name, manifest = render_claim_manifest("run-abc", lifetime_seconds=1200, now=now)

    assert name == "patchapi-run-run-abc"
    assert f"name: {name}" in fields_of(manifest)
    assert "shutdownPolicy: Delete" in fields_of(manifest)
    assert rendered_shutdown_time(manifest) == now + timedelta(seconds=1200)
    assert "PATCHAPI_SANDBOX_CLAIM" not in manifest


def test_rendered_shutdown_time_is_in_the_future():
    _, manifest = render_claim_manifest("run-future")

    delta = rendered_shutdown_time(manifest) - datetime.now(UTC)
    assert timedelta(seconds=0) < delta <= timedelta(seconds=max_lifetime_seconds() + 5)


def test_lifetime_is_configurable_without_touching_the_manifest(monkeypatch):
    monkeypatch.setenv("PATCHAPI_SANDBOX_MAX_LIFETIME_SEC", "300")
    now = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

    assert max_lifetime_seconds() == 300
    _, manifest = render_claim_manifest("run-short", now=now)
    assert rendered_shutdown_time(manifest) == now + timedelta(seconds=300)


@pytest.mark.parametrize("raw", ["0", "-1", "twenty"])
def test_an_unusable_lifetime_is_rejected(monkeypatch, raw):
    monkeypatch.setenv("PATCHAPI_SANDBOX_MAX_LIFETIME_SEC", raw)

    with pytest.raises(ValueError):
        max_lifetime_seconds()


def test_rendering_fails_when_the_shutdown_marker_is_missing(tmp_path):
    stale = tmp_path / "sandbox-claim.yaml"
    stale.write_text(
        CLAIM_MANIFEST.read_text(encoding="utf-8").replace("# PATCHAPI_SANDBOX_SHUTDOWN_TIME", ""),
        encoding="utf-8",
    )

    with pytest.raises(SandboxError, match="SHUTDOWN_TIME"):
        render_claim_manifest("run-abc", manifest_path=stale)


@pytest.mark.parametrize(
    "run_id",
    ["run-1", "RUN_2", "20260813T120000Z-4242", "a/b:c", "x" * 120],
)
def test_claim_names_are_dns_1123(run_id):
    name = claim_name_for(run_id)

    assert DNS_1123.match(name), name
    assert len(name) <= 63
    assert name.startswith("patchapi-run-")


def test_claim_names_are_unique_per_run():
    run_ids = ["run-1", "run-2", "run-3", "RUN-4"]

    names = {claim_name_for(run_id) for run_id in run_ids}

    assert len(names) == len(run_ids)


def test_two_concurrent_runs_render_distinct_claims():
    first, first_manifest = render_claim_manifest("run-a", lifetime_seconds=600)
    second, second_manifest = render_claim_manifest("run-b", lifetime_seconds=600)

    assert first != second
    assert f"name: {first}" in first_manifest
    assert f"name: {second}" in second_manifest


def test_cluster_coordinates_come_from_config_env():
    config = load_cluster_config()

    assert isinstance(config, ClusterConfig)
    assert config.namespace == "patchapi-sandbox-dev"
    assert config.cluster and config.project and config.location


def test_cluster_coordinates_are_overridable_from_the_environment(monkeypatch):
    monkeypatch.setenv("PATCHAPI_SANDBOX_NAMESPACE", "patchapi-sandbox-test")

    assert load_cluster_config().namespace == "patchapi-sandbox-test"
