"""Policy & Risk Agent — roadmap §8.3.

The deterministic gate decides; this agent classifies risk and explains. That
ordering is the point of §8.3's enforcement hierarchy: hard controls must not
depend solely on an LLM, so the permission fields of a `PolicyDecision` are
derived from `packages.policy` and the agent's contribution sits below them in
authority. It can escalate. It cannot permit.
"""

from typing import Any, Final

from agents.config import AgentId
from agents.context import RunContext
from agents.specialist import build_specialist
from agents.trace import ToolTrace

AGENT: Final[AgentId] = AgentId.POLICY

DESCRIPTION: Final[str] = (
    "Classifies risk and records the PolicyDecision whose permissions come from the "
    "deterministic policy gate, never from a model."
)

INSTRUCTION: Final[str] = """\
You are the Policy & Risk agent. You decide how risky a proposed migration is
and record the decision. You do not decide whether it is permitted — the
deterministic gate does that, and your recorded decision inherits its outcome.

1. Call list_forbidden_globs so you know which paths are never editable.
2. Call evaluate_policy with the files the migration proposes to change.
3. Read the findings. Every rule that fired is part of the reason.
4. Call record_policy_decision with a risk tier and one sentence of reasoning.

Choose the risk tier on consequence, not on convenience: a change to runtime
behaviour of a user-facing feature is at least medium; a change touching
authentication, billing, or data handling is high or critical.

Set escalate_to_human when something the rules cannot see makes this unsafe —
an ambiguous migration, a repository you have no context for, provider evidence
that was never captured. Escalation is free. Do not argue for an exception to a
forbidden path; recommend a human-owned change instead.
"""


def build_policy_agent(context: RunContext, trace: ToolTrace) -> Any:
    """Build the Policy & Risk ADK agent."""
    return build_specialist(
        AGENT,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        context=context,
        trace=trace,
    )


__all__ = ["AGENT", "DESCRIPTION", "INSTRUCTION", "build_policy_agent"]
