"""The orchestrator: a state machine that calls agents, not an agent that decides.

Roadmap §9 is explicit that the critical workflow must not be "supervisor agent,
decide what everyone should do". So the orchestrator here is ordinary Python. It
owns the run state, advances it through `packages.schemas.run_state` — which
refuses an illegal transition — and invokes exactly one specialist per stage.
Specialists cannot transfer to each other, so the sequence in this file is the
only sequence that can happen.

What a stage produced is read from `RunContext`, never from the model's closing
sentence. A stage whose agent recorded nothing is a failed stage even if the
agent said it succeeded.
"""

from dataclasses import dataclass
from typing import Any, Final

from agents.change_intelligence import build_change_intelligence_agent
from agents.config import AgentId
from agents.context import RunContext
from agents.impact import build_impact_agent
from agents.patch import build_patch_agent
from agents.policy import build_policy_agent
from agents.pr import build_pr_agent
from agents.runtime import TurnResult, run_turn
from agents.trace import ToolTrace
from agents.verification import build_verification_agent
from packages.schemas.run_state import RunState, assert_transition

# Agent -> the contract a completed stage must have committed.
STAGE_CONTRACTS: Final[dict[AgentId, str]] = {
    AgentId.CHANGE_INTELLIGENCE: "change_manifest",
    AgentId.IMPACT: "impact_report",
    AgentId.POLICY: "policy_decision",
    AgentId.PATCH: "patch_plan",
    AgentId.VERIFICATION: "verification_report",
}

_BUILDERS: Final[dict[AgentId, Any]] = {
    AgentId.CHANGE_INTELLIGENCE: build_change_intelligence_agent,
    AgentId.IMPACT: build_impact_agent,
    AgentId.POLICY: build_policy_agent,
    AgentId.PATCH: build_patch_agent,
    AgentId.VERIFICATION: build_verification_agent,
    AgentId.PR: build_pr_agent,
}


def build_fleet(context: RunContext, trace: ToolTrace) -> dict[AgentId, Any]:
    """Construct all six specialists against one run context and trace.

    Building the whole fleet is how the smoke proves the topology is real:
    every agent constructs, every allowlist resolves to implemented tools, and
    every tool callback is attached, before any model is called.
    """
    return {agent: builder(context, trace) for agent, builder in _BUILDERS.items()}


@dataclass(slots=True)
class StageResult:
    """What one stage of the run produced."""

    agent: AgentId
    state: RunState
    turn: TurnResult
    output: Any | None
    human_required: tuple[dict[str, str], ...]

    @property
    def completed(self) -> bool:
        """Whether the stage committed the contract it is responsible for."""
        return self.output is not None


class Orchestrator:
    """Drives one remediation run through the deterministic state machine.

    Only the stages whose inputs exist are implemented. Later stages need a
    sandbox workspace and sandbox evidence, and an orchestrator that pretended
    to run them would be reporting outcomes nothing produced.
    """

    def __init__(self, context: RunContext, trace: ToolTrace) -> None:
        self._context = context
        self._trace = trace
        self._state = RunState.RECEIVED
        self._agents = build_fleet(context, trace)

    @property
    def state(self) -> RunState:
        return self._state

    @property
    def context(self) -> RunContext:
        return self._context

    @property
    def trace(self) -> ToolTrace:
        return self._trace

    @property
    def fleet(self) -> dict[AgentId, Any]:
        """The constructed specialists, keyed by identity."""
        return dict(self._agents)

    def agent(self, agent: AgentId) -> Any:
        """The constructed ADK agent for `agent`."""
        return self._agents[agent]

    def _advance(self, target: RunState) -> None:
        assert_transition(self._state, target)
        self._state = target

    async def run_change_intelligence(self, change_id: str) -> StageResult:
        """Normalize one provider notice into a `ChangeManifest`.

        RECEIVED → SANITIZED once the notice has passed the untrusted-text gate
        the tool applies, then → NORMALIZED once a manifest is committed. A
        stage that commits nothing ends the run FAILED rather than leaving the
        state where a later stage could read it as success.
        """
        agent = AgentId.CHANGE_INTELLIGENCE
        self._advance(RunState.SANITIZED)

        prompt = (
            f"Produce the ChangeManifest for provider change {change_id!r}. "
            "Read the notice, compare it against the deterministic parse, and record "
            "the manifest only if they agree."
        )
        turn = await run_turn(self._agents[agent], prompt, trace=self._trace)
        output = self._context.output(STAGE_CONTRACTS[agent])

        if output is None:
            self._advance(RunState.FAILED)
        else:
            self._advance(RunState.NORMALIZED)

        return StageResult(
            agent=agent,
            state=self._state,
            turn=turn,
            output=output,
            human_required=tuple(self._context.human_required),
        )


__all__ = ["STAGE_CONTRACTS", "Orchestrator", "StageResult", "build_fleet"]
