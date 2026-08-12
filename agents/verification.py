"""Verification Agent — roadmap §8.5.

Independent of patch generation, and independent by construction rather than by
convention: it is a separate agent with a separate prompt and a separate
allowlist, it reads only sandbox artifacts, and `VerificationReport` refuses a
report whose verifier is the agent that authored the patch.

It has veto power. No pull request is opened without a PASS from here.
"""

from typing import Any, Final

from agents.config import AgentId
from agents.context import RunContext
from agents.specialist import build_specialist
from agents.trace import ToolTrace

AGENT: Final[AgentId] = AgentId.VERIFICATION

DESCRIPTION: Final[str] = (
    "Independently grades a produced patch against sandbox evidence and records a "
    "VerificationReport. Has veto power over the pull request."
)

INSTRUCTION: Final[str] = """\
You are the Verification agent. You did not write this patch and you are not
here to defend it. You decide whether the evidence supports opening a pull
request for human review.

1. Call list_verification_evidence, then read the artifacts that matter: the
   build log, the test log, the diff, and any live API artifact.
2. Answer each question from the evidence, not from the patch's description:
   - Does the diff address the provider change the ChangeManifest describes?
   - Did it change anything outside the plan's files_expected?
   - Did the build pass? Did the tests pass?
   - Did a live call to the replacement API succeed?
   - Are the retired identifiers gone from the exercised path?
   - Are forbidden paths untouched?
3. Call record_verification_report.

A check you did not run is "skip", never "pass". A log you could not read is
"inconclusive", never "pass". If the evidence is thin but nothing failed, an
"inconclusive" verdict is the honest answer and the run stops there.

Passing a patch that does not work is the worst outcome available to you. It is
strictly better to be wrong in the direction of a human looking at it.
"""


def build_verification_agent(context: RunContext, trace: ToolTrace) -> Any:
    """Build the Verification ADK agent."""
    return build_specialist(
        AGENT,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        context=context,
        trace=trace,
    )


__all__ = ["AGENT", "DESCRIPTION", "INSTRUCTION", "build_verification_agent"]
