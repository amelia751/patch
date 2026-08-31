# Classifying capability loss

Work through every option the affected call sites actually pass. Options the
repository never uses do not need a disposition; do not pad the pull request
with them.

## The three dispositions

**MAP** — the replacement accepts the same thing, possibly under a different
name or nested in a different object. The patch carries it across. Say where it
moved to in the migration summary.

**HUMAN_REQUIRED** — the replacement has no equivalent, or the closest
analogue has a different value space. This is not a rename and you cannot
decide it. The option goes in the pull request body as an explicit
capability-loss callout, naming the call sites that pass it.

**REMOVE** — the option only ever configured the retired surface and has no
observable effect on the caller. Rare. If you find yourself reaching for this
to avoid a callout, the answer is HUMAN_REQUIRED.

## What makes something HUMAN_REQUIRED rather than MAP

- The analogue takes a different value space — an enum where the original took
  a number, or a size bucket where the original took pixels.
- The analogue changes the guarantee. Reproducibility, determinism, and
  ordering are guarantees a caller can depend on without ever mentioning them.
- Preserving the behaviour would require rewriting the prompt, the request, or
  the caller's own logic rather than moving an argument.

Folding a dropped option into some other field is a behaviour change wearing a
mapping's clothes. It is HUMAN_REQUIRED.

## The escalation rule

Every HUMAN_REQUIRED option that the affected call sites actually use must
appear in the pull request body as an explicit capability-loss callout.

A green build with a silently dropped option is a failed migration, not a
passing one. This is the specific failure this classification exists to
prevent: the tests still pass, because the tests never asserted on the option,
and the behaviour change reaches production unreviewed.

## Recording it

State each disposition in the patch plan's assumptions, in the form a reviewer
can check:

- `aspectRatio -> imageConfig.aspectRatio (MAP)`
- `seed: no equivalent on the replacement surface (HUMAN_REQUIRED); used by
  lib/render.ts:41`

If every affected option is MAP, say so. "No capability loss" is a finding, and
a reviewer should not have to infer it from silence.
