# What counts as proof

The patch-producing model does not grade its own work. Everything here is about
producing evidence a separate process can re-run in a clean workspace, not
about convincing yourself.

## The gate has to name the change

A command that exits 0 without touching this change's binding proves the tree
still builds. It does not prove the migration happened. Before you nominate a
check, confirm the script it runs reads the constant you rebound or one of the
retired identifiers.

A repository can hold several bound identifiers in one file — a text model and
an image model beside it. Its default test command grades one of them.

## Red to green

Run the gate before you patch. A check that was already green cannot
demonstrate anything, and a check that stays green through a no-op edit is
worse than no check because it reads as evidence.

If the gate is green before the patch, it is the wrong gate.

## Local exit code versus live call

**A local check proves the binding.** The identifier changed, the tree still
compiles, the tests still pass. This is sufficient when the exercised path
makes no network request — a live gate there would be theatre.

**A live call proves the replacement resolves.** This is the only thing that
catches a recommended identifier the provider does not actually serve, which is
the failure that turns one outage into two. Required when the exercised path
issues a real request.

Decide which one this change needs from the code, then say which one you ran.
Never describe a local identifier check as a live provider call.

## When the live gate needs a credential you do not have

List the runtime credentials available. Compare them against the variables the
live path actually reads. If what you need is absent, request it by name and
stop — the same run continues once an operator supplies it.

Do not invent a key, do not read one back through a command, and do not record
that the change cannot be tested. An unexercised live path is a stated
assumption, not a failure.

## What to write down

- The commands that must pass, and their exit codes.
- Whether a live call was made, and against what.
- Any path this change touches that went unexercised, and why.

A reviewer who never saw the run has to be able to tell what was proven from
what was assumed. If the two are not distinguishable in what you wrote, the
evidence is not usable.
