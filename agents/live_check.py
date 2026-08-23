"""Ask the provider whether the identifier the patch wrote actually resolves.

Every other check in a run is about the repository: does it build, do its tests
pass, does the diff touch only what was planned. None of them can catch the one
mistake this product must never make — writing a model id that does not exist.
A build is perfectly happy with a plausible string, and so is a test suite that
never reaches the network.

So after the offline checks pass, the replacement is put to the provider itself,
inside the sandbox, during the one phase where egress and a credential are
allowed. The answer is written as evidence and graded by the Verification agent
like everything else. A run that cannot ask reports that it could not, which is
the difference between "unverified" and "verified false".

The credential is brokered by the orchestrator from Secret Manager and injected
into a single command. It is never returned to a model, never written to
evidence, and never leaves the phase: `sandbox.session` rejects any name outside
`LIVE_VERIFICATION_CREDENTIALS`, and the phase's NetworkPolicy is torn down with
the step.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

# Names the sandbox will carry, most specific first. A project that registered
# the key under any of them can be checked; the program reads whichever arrives.
CREDENTIAL_NAMES: Final[tuple[str, ...]] = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
)

LIVE_PHASE: Final[str] = "live_verification"
TIMEOUT_SECONDS: Final[float] = 90.0

# Run inside the sandbox. Deliberately dependency-free: the repository under
# migration may not have the provider SDK installed, and installing one to run
# a check would be a second thing that can fail for reasons unrelated to the
# answer. A GET against the models endpoint is the whole question.
PROBE: Final[str] = """
import json, os, sys, urllib.error, urllib.request

model = sys.argv[1]
key = ""
for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"):
    key = os.environ.get(name, "").strip()
    if key:
        break
if not key:
    print(json.dumps({"resolved": None, "detail": "no credential reached the sandbox"}))
    raise SystemExit(0)

url = "https://generativelanguage.googleapis.com/v1beta/models/" + model
request = urllib.request.Request(url, headers={"x-goog-api-key": key})
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    print(json.dumps({
        "resolved": True,
        "model": payload.get("name", model),
        "methods": payload.get("supportedGenerationMethods", []),
    }))
except urllib.error.HTTPError as exc:
    # 404 is the answer, not a failure: the provider is saying this id is not
    # one of its models. Anything else means the question went unanswered.
    print(json.dumps({
        "resolved": False if exc.code == 404 else None,
        "status": exc.code,
        "detail": exc.read().decode("utf-8", errors="replace")[:400],
    }))
except Exception as exc:
    print(json.dumps({"resolved": None, "detail": f"{type(exc).__name__}: {exc}"}))
"""


def _open_phase(session: Any) -> str:
    """Widen egress for the probe, if this session has a network to widen."""
    opener = getattr(session, "apply_network_phase", None)
    if not callable(opener):
        return ""
    try:
        return str(opener(LIVE_PHASE))
    except Exception:
        # A sandbox that will not open the phase still gets asked; the probe
        # then fails on the network and is reported as unasked, which is the
        # same honest answer by a slower route.
        return ""


def _close_phase(session: Any, policy: str) -> None:
    closer = getattr(session, "clear_network_phase", None)
    if policy and callable(closer):
        try:
            closer(policy)
        except Exception:
            # The claim's own shutdownTime deletes the pod and every policy
            # scoped to it, so a failed teardown is bounded, not permanent.
            pass


@dataclass(frozen=True, slots=True)
class LiveCheck:
    """What the provider said about the identifier the patch wrote."""

    identifier: str
    # True resolved, False the provider does not know it, None not asked.
    resolved: bool | None
    detail: str

    @property
    def asked(self) -> bool:
        return self.resolved is not None

    @property
    def log(self) -> str:
        if self.resolved is True:
            return (
                f"$ resolve {self.identifier}\n"
                f"{self.identifier} resolves against the provider.\n{self.detail}\n"
                "(exit 0)\n"
            )
        if self.resolved is False:
            return (
                f"$ resolve {self.identifier}\n"
                f"{self.identifier} does NOT resolve: the provider does not serve this "
                f"identifier.\n{self.detail}\n(exit 1)\n"
            )
        return (
            f"$ resolve {self.identifier}\n"
            f"Not asked. {self.detail}\n"
            "The patch is unverified against the provider; the offline checks still apply.\n"
        )


def run(session: Any, identifier: str, credentials: dict[str, str]) -> LiveCheck:
    """Ask the provider about `identifier` from inside `session`.

    `credentials` is already narrowed to the sandbox allowlist by the caller.
    An empty mapping means the project supplied nothing, which is reported
    rather than treated as a pass.
    """
    if not identifier.strip():
        return LiveCheck(identifier, None, "the change names no replacement to check")
    if not credentials:
        return LiveCheck(
            identifier,
            None,
            "no runtime credential is configured for this project, so the provider "
            "was not contacted",
        )

    # The sandbox denies all egress by default. The policy is opened around this
    # one command and torn down in `finally`, so a failure here cannot leave a
    # sandbox that can reach the internet for the rest of the run.
    policy = _open_phase(session)
    try:
        result = session.execute(
            ["python3", "-c", PROBE, identifier], TIMEOUT_SECONDS, extra_env=credentials
        )
    except Exception as exc:
        return LiveCheck(identifier, None, f"the sandbox could not run the check: {exc}")
    finally:
        _close_phase(session, policy)

    if result.exit_code != 0:
        return LiveCheck(
            identifier, None, f"the check exited {result.exit_code}: {result.stderr.strip()[:400]}"
        )
    try:
        payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return LiveCheck(identifier, None, "the check produced no answer")

    resolved = payload.get("resolved")
    if resolved is True:
        methods = ", ".join(payload.get("methods") or []) or "no methods reported"
        return LiveCheck(identifier, True, f"{payload.get('model', identifier)} — {methods}")
    if resolved is False:
        return LiveCheck(identifier, False, str(payload.get("detail", "")))
    return LiveCheck(identifier, None, str(payload.get("detail", "the provider did not answer")))


__all__ = ["CREDENTIAL_NAMES", "LIVE_PHASE", "PROBE", "LiveCheck", "run"]
