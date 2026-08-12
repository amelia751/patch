"""PatchAPI's Google ADK agent layer: one orchestrator, six specialists.

Google ADK is the only agent framework in this tree, and
`agents/tests/test_framework_compliance.py` asserts that no other one appears.

Two import rules keep this package usable everywhere it has to run.

*No re-exports here.* Callers import the submodule they need. A bare `pytest` at
the repository root collects every tree using the workspace-root environment,
which does not install this member or its Pydantic dependency, and an eager
import in this file would abort collection for all of them.

*No ADK at module scope.* The guardrails, the trace, the tool functions and the
contracts are plain Python and are unit-tested without google-adk installed;
only `agents.runtime` and `agents.specialist` reach for it, and they do so inside
the functions that need it. A missing ADK install is then an honest skip of the
live smoke rather than an import error.

Entry points:
    `agents.orchestrator.Orchestrator` — drives a run through the state machine.
    `agents.orchestrator.build_fleet` — constructs all six specialists.
    `agents.runtime.run_turn` — runs one agent turn against pinned Vertex Gemini.
    `agents.config` — model pin, prompt versions and every tool allowlist.
"""
