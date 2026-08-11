# PatchAPI

**Dependabot for APIs.** When an external API changes, PatchAPI finds the
affected code, generates and verifies a migration in an isolated environment,
and opens an evidence-backed pull request for normal human review.

Built for the [All Things Agentic Hackathon](https://allthingsagentichackathon.devpost.com/)
— Fortified Enterprise Fleet track.

## Status

Early scaffold. Authoritative plan: [`roadmap.md`](./roadmap.md).

Flagship demo target: pinned fork of [`remorses/egaki`](https://github.com/remorses/egaki),
migrating Google Imagen 4 → Gemini 3.1 Flash Image.

## Hard product boundary

PatchAPI **stops at the pull request**. It does not merge, deploy, edit branch
protection, or bypass CODEOWNERS / CI.

## Local agent fleet

Claude Code workforce tooling lives in `.fleet/` (gitignored). After cloning:

```bash
.fleet/bin/bootstrap.sh     # sync roles → .claude/agents, create ./fleet
./fleet doctor
./fleet roles
./fleet run smoke --dry-run
```

Project conventions for agents: [`CLAUDE.md`](./CLAUDE.md).
