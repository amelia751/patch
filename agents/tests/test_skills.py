"""The skill packages, and how ADK exposes them to the Patch agent.

Two properties are worth a test, and neither is about the prose. First, every
package under `skills/` is loadable by ADK's own reader — a package that fails
the Agent Skill specification is invisible at runtime and silently costs the
Patch agent its method. Second, the toolset the agent gets is the granted one:
three tools, without the script runner ADK adds by default.
"""

import asyncio

import pytest

from agents.adk import (
    adk_unavailable_reason,
    build_skill_toolset,
    repo_root,
    skill_packages,
)
from agents.config import SKILL_ENTRYPOINT, SKILL_TOOLS, AgentId, tool_allowlist
from agents.errors import SkillsUnavailableError

pytestmark = pytest.mark.skipif(
    adk_unavailable_reason() is not None,
    reason=adk_unavailable_reason() or "",
)

SKILLS_ROOT = repo_root() / "skills"


def _tool_names(toolset):
    return {tool.name for tool in asyncio.run(toolset.get_tools(None))}


def test_the_repository_ships_at_least_one_skill_package():
    assert skill_packages(SKILLS_ROOT), f"no {SKILL_ENTRYPOINT} package under {SKILLS_ROOT}"


@pytest.mark.parametrize("package", skill_packages(SKILLS_ROOT), ids=lambda path: path.name)
def test_every_package_loads_through_adk(package):
    """The spec validates the frontmatter; a bad `name` or description fails here."""
    from google.adk.skills import load_skill_from_dir

    skill = load_skill_from_dir(package)

    assert skill.name == package.name
    assert skill.frontmatter.description.strip()
    # The version the Patch agent puts on its plan. `load_skill` hands the model
    # the whole frontmatter, so an unversioned package yields a plan that names
    # a skill it cannot pin.
    assert skill.frontmatter.metadata.get("version")


def test_no_package_carries_a_general_change_id():
    """A skill is a method. Pinning one change to it is the design this replaced."""
    for package in skill_packages(SKILLS_ROOT):
        assert not (package / "skill.json").exists(), (
            f"{package.name} carries a bespoke manifest; the frontmatter is the manifest"
        )


def test_the_toolset_is_exactly_the_patch_grant():
    granted = {str(name) for name in tool_allowlist(AgentId.PATCH) & SKILL_TOOLS}

    assert _tool_names(build_skill_toolset(SKILLS_ROOT)) == granted


def test_the_script_runner_never_reaches_the_model():
    """ADK generates `run_skill_script`; executing belongs to the sandbox alone."""
    assert "run_skill_script" not in _tool_names(build_skill_toolset(SKILLS_ROOT))


def test_an_empty_skills_tree_fails_the_run_rather_than_degrading_it(tmp_path):
    with pytest.raises(SkillsUnavailableError):
        build_skill_toolset(tmp_path)
