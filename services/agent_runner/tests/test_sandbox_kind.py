"""Which sandbox transport a remediation runs generated code in.

The isolation is the reason the patch loop is allowed to execute a model's
output at all, so the default must not be something a forgotten variable can
weaken. `local` exists for a developer's own checkout, where there is no
cluster and the local dispatcher is the only way to run the job.
"""

from __future__ import annotations

import pytest
from patchapi_agent_runner.remediation.job import SANDBOX_ENV_VAR, sandbox_kind


def test_an_unset_environment_gets_the_isolated_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SANDBOX_ENV_VAR, raising=False)
    assert sandbox_kind() == "gke"


def test_a_checkout_may_ask_for_the_local_temp_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SANDBOX_ENV_VAR, "local")
    assert sandbox_kind() == "local"


@pytest.mark.parametrize("requested", ["", "  ", "docker", "none", "off", "gvisor"])
def test_anything_else_falls_back_to_the_cluster(
    monkeypatch: pytest.MonkeyPatch, requested: str
) -> None:
    """A typo must not downgrade the boundary, and must not stop the run either.

    `PATCHAPI_SANDBOX=docker` asking for something that does not exist is a
    misconfiguration; answering it with the stronger transport is the safe
    reading, and `open_session` still refuses if the cluster is unreachable.
    """
    monkeypatch.setenv(SANDBOX_ENV_VAR, requested)
    assert sandbox_kind() == "gke"


def test_the_name_is_read_case_insensitively(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SANDBOX_ENV_VAR, "LOCAL")
    assert sandbox_kind() == "local"
