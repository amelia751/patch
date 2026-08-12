"""PatchAPI sandbox runner.

Executes a pinned source tree plus a candidate patch in a disposable workspace
and records what happened. Phase 1 backs this with a local temp directory; the
GKE Agent Sandbox implementation consumes the same `sandbox.plan.v1` document
and emits the same `sandbox.result.v1` record, so agents do not change when the
execution environment does.
"""

from .config import PLAN_SCHEMA_VERSION, RESULT_SCHEMA_VERSION, PlanError, SandboxPlan
from .runner import RunResult, execute_plan
from .workspace import IsolationError, SourceError

__all__ = [
    "PLAN_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION",
    "IsolationError",
    "PlanError",
    "RunResult",
    "SandboxPlan",
    "SourceError",
    "execute_plan",
]
