"""Failure modes of the agent layer.

Each is a distinct fail-closed reason. A caller distinguishes them because they
mean different things to an operator: a missing dependency is a `SKIP`, a denied
tool is a compliance stop that must be visible, and a stuck turn is a run that
ends `HUMAN_REQUIRED` rather than one that retries forever.
"""


class AgentError(Exception):
    """Base class for every PatchAPI agent-layer failure."""


class AdkUnavailableError(AgentError):
    """Google ADK is not importable in this environment.

    PatchAPI has no second orchestration framework to fall back to, so this is
    reported as a skipped verification, never worked around.
    """


class ToolDeniedError(AgentError):
    """An agent called a tool outside its allowlist.

    The call is refused before the tool function runs. Reaching this means a
    prompt or a topology change tried to widen an agent's authority, which is
    exactly the event an audit needs to see.
    """

    def __init__(self, agent: str, tool: str) -> None:
        super().__init__(f"agent {agent!r} is not permitted to call tool {tool!r}")
        self.agent = agent
        self.tool = tool


class TurnStuckError(AgentError):
    """An agent turn exceeded its tool-call budget without recording an output."""


class NoOutputRecordedError(AgentError):
    """A turn finished without committing its contract.

    An agent's output is whatever it recorded through a `record_*` tool. Prose
    in a final message is not an output, and is never parsed into one.
    """
