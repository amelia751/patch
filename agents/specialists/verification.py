"""Verification Agent — roadmap §8.5.

Independent of patch generation, and independent by construction rather than by
convention: it is a separate agent with a separate prompt and a separate
allowlist, it reads only sandbox artifacts, and `VerificationReport` refuses a
report whose verifier is the agent that authored the patch.

It has veto power. No pull request is opened without a PASS from here.
"""

from typing import Any, Final

from agents.adk import build_agent
from agents.config import AgentId
from agents.context import RunContext
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
   - Did the build pass? Did the tests pass? If this change named no local
     check, those are skip — not fail, and not a reason to refuse PASS.
   - Did a live call to the replacement API succeed?
   - Are the retired identifiers gone from the exercised path?
   - Are forbidden paths untouched?
3. You may call search_web to confirm an official API error or replacement
   surface named in the evidence. Search cannot turn a missing log into
   pass, and it cannot override a failed build or test.
4. A local identifier check (generate.py / unit tests) is not live_api.
   If the app's live path needs an API key you saw in the evidence or the
   workspace, call list_runtime_credentials. When the name is missing, call
   request_runtime_credentials and stop — do not record live_api as pass,
   skip, or inconclusive just because the operator has not pasted the key
   yet. record_human_required is for unresolvable evidence, not a missing
   GEMINI_API_KEY.
5. Call record_verification_report.

A check you did not run is "skip", never "pass". A log you could not read is
"inconclusive", never "pass". Skip on build/tests plus a passing live
resolve is PASS when the retired identifiers are gone. Inconclusive is for
when neither a local gate nor a live resolve actually ran.

Passing a patch that does not work is the worst outcome available to you. It is
strictly better to be wrong in the direction of a human looking at it.
"""


def build(context: RunContext, trace: ToolTrace) -> Any:
    """Build the Verification ADK agent."""
    return build_agent(
        AGENT,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        context=context,
        trace=trace,
    )


__all__ = ["AGENT", "DESCRIPTION", "INSTRUCTION", "build"]
