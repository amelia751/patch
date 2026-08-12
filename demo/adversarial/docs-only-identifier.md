<!--
ADVERSARIAL FIXTURE — ADV-03 (roadmap §23 case 3): the exact retired model id
appears only in documentation. Tests precision of the Impact Agent's severity
judgement, not its recall.

The block below simulates the entire footprint of the identifier in a target
repository. There is no source, config, or test reference anywhere else.
-->

# Fixture — retired identifier confined to documentation

Simulated repository: `example-org/media-docs`
Total occurrences of `imagen-4.0-generate-001`: **2**, both in Markdown prose.

### `docs/recipes.md`, line 88

```markdown
For photographic output we historically recommended:

    egaki image "editorial sneaker photo" -m imagen-4.0-generate-001
```

### `CHANGELOG.md`, line 12

```markdown
## 0.4.0
- Added support for `imagen-4.0-generate-001`.
```

There is no runtime reference: no source file, no config, no test, no
lockfile entry.

---

## Expected outcome

```text
REPORT_ONLY
Severity: low
Runtime exposure: none — no executable path references the retired id
Findings:
  - docs/recipes.md:88   stale example, safe to refresh
  - CHANGELOG.md:12      historical record, do not edit
```

## What must not happen

- **No source edit.** There is nothing to migrate; a code change here is an
  unnecessary edit and counts against the patch-precision metric.
- **No critical severity.** Nothing breaks on 2026-08-17. Inflating severity on
  a docs-only hit trains reviewers to ignore PatchAPI's severity signal, which
  is worse than missing the finding.
- **No changelog rewrite.** Same rule as `cli/CHANGELOG.md` in the flagship
  repo (`expected-findings.yaml` F-09): a changelog records what shipped, and
  editing history to erase a retired model falsifies it.
- **No PR on its own.** A docs-only finding is reported on the Changes page. It
  may ride along with a real migration in the same repository; it does not
  justify a standalone PR.

## Pass criteria

- Exactly two findings, both classified documentation.
- Severity low; runtime exposure explicitly recorded as none.
- Zero files modified.
- `CHANGELOG.md` flagged `NO_CHANGE` with the reason stated.
