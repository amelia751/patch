"""Execution of one planned command with capture, timeout, and teardown.

Every step writes `logs/<name>.txt`. A step with no captured output still
produces the file, because "PASS with no evidence" is not a claim this system is
allowed to make.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .config import Step

StepStatus = Literal["PASS", "FAIL", "TIMEOUT", "ERROR"]

# Grace between the group terminate and the group kill on timeout. Short: a
# sandbox that will not stop on request has already forfeited its turn.
_KILL_GRACE_SECONDS = 5


@dataclass(frozen=True)
class StepResult:
    """The full record of one command: what ran, what happened, where the log is."""

    name: str
    argv: tuple[str, ...]
    phase: str
    status: StepStatus
    exit_code: int | None
    duration_seconds: float
    log_path: Path
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "argv": list(self.argv),
            "phase": self.phase,
            "status": self.status,
            "exit_code": self.exit_code,
            "duration_seconds": round(self.duration_seconds, 3),
            "log": self.log_path.name,
            "detail": self.detail,
        }


def run_step(
    step: Step,
    *,
    workspace: Path,
    logs_dir: Path,
    environment: Mapping[str, str],
) -> StepResult:
    """Run one step to completion, a timeout, or a launch failure."""

    log_path = logs_dir / f"{step.name}.txt"
    cwd = (workspace / step.workdir).resolve()
    started = time.monotonic()

    if not cwd.is_dir():
        log_path.write_text(f"workdir {cwd} does not exist\n", encoding="utf-8")
        return StepResult(
            name=step.name,
            argv=step.argv,
            phase=step.phase,
            status="ERROR",
            exit_code=None,
            duration_seconds=time.monotonic() - started,
            log_path=log_path,
            detail=f"workdir {step.workdir!r} missing in workspace",
        )

    header = (
        f"$ {' '.join(step.argv)}\n"
        f"# workdir: {step.workdir}\n"
        f"# phase: {step.phase}\n"
        f"# timeout: {step.timeout_seconds}s\n\n"
    )
    with log_path.open("w", encoding="utf-8") as log:
        log.write(header)
        log.flush()
        try:
            # start_new_session puts the child in its own process group so a
            # timeout reaps the whole tree, not just the command that was named.
            # argv is a validated list of strings; the runner never builds a
            # shell string out of plan data.
            process = subprocess.Popen(
                step.argv,
                cwd=cwd,
                env=dict(environment),
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            log.write(f"\nfailed to launch: {exc}\n")
            return StepResult(
                name=step.name,
                argv=step.argv,
                phase=step.phase,
                status="ERROR",
                exit_code=None,
                duration_seconds=time.monotonic() - started,
                log_path=log_path,
                detail=f"failed to launch: {exc}",
            )

        try:
            exit_code = process.wait(timeout=step.timeout_seconds)
        except subprocess.TimeoutExpired:
            _terminate_group(process)
            duration = time.monotonic() - started
            log.write(f"\n[timeout] exceeded {step.timeout_seconds}s; process group destroyed\n")
            return StepResult(
                name=step.name,
                argv=step.argv,
                phase=step.phase,
                status="TIMEOUT",
                exit_code=None,
                duration_seconds=duration,
                log_path=log_path,
                detail=f"exceeded {step.timeout_seconds}s",
            )

    duration = time.monotonic() - started
    return StepResult(
        name=step.name,
        argv=step.argv,
        phase=step.phase,
        status="PASS" if exit_code == 0 else "FAIL",
        exit_code=exit_code,
        duration_seconds=duration,
        log_path=log_path,
    )


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    """Destroy the timed-out process group; never leave a dirty sandbox."""

    try:
        group = os.getpgid(process.pid)
    except ProcessLookupError:
        return
    for sig, wait in ((signal.SIGTERM, _KILL_GRACE_SECONDS), (signal.SIGKILL, _KILL_GRACE_SECONDS)):
        try:
            os.killpg(group, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue
