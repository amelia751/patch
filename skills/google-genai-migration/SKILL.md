---
name: google-genai-migration
description: Google generative AI specifics for a migration — Gemini and Imagen model identifiers, which request surface each family dispatches on, how to resolve a recommended ID against the installed SDK, and the known traps in Google's own deprecation pages. Load this in addition to api-migration when the change manifest names provider google.
license: Apache-2.0
metadata:
  version: 1.0.0
  owner: patchapi-platform
---

# Google generative AI, for migrations

Provider-family knowledge, not change knowledge. Which identifiers retire and
when comes from the ChangeManifest. What is here is true across Google
retirements and stays true after any single one is handled.

Read `api-migration` first. This skill only adds what is Google-specific.

## Where Google states a retirement

- `ai.google.dev` model pages and the deprecations table.
- The Gemini API changelog.
- `cloud.google.com` Vertex AI model reference, for the Vertex routing of the
  same models.

**These pages disagree with each other.** The deprecations table and the
changelog have named different replacements for the same retired identifier on
the same day. When they do:

- Do not pick silently. The disagreement itself is a finding.
- Prefer the identifier the ChangeManifest pinned, because it was corroborated
  and hashed at intake.
- Put the divergence in the pull request body as a stated choice.

## Reading an identifier

**Variant suffixes take variant replacements.** A `-lite` identifier migrates to
the lite replacement, not to the headline `recommended_replacement`. Same for
other tier suffixes. Applying the headline ID to every affected identifier in
the list is the most common mechanical error on a Google change.

**Route prefixes are not models.** A `vertex/` prefix in front of an identifier
is a routing decision inside the consumer repository. The prefixed and bare
forms retire together and both need the rewrite.

**Substring matches are not identifiers.** A third-party hosted model whose
name merely contains a Google model string is a different model on a different
provider. Editing it is an unnecessary change and it will be counted against
the run.

**Preview and GA identifiers differ.** The ID a provider page recommends is
frequently the GA name, while the ID that actually resolves in a given SDK
version is the preview one, or the reverse. Resolve before writing — see below.

## Resolving a recommended identifier

A Google model ID from a doc page is a claim. Before it goes into code:

1. Check the SDK installed in this workspace for its model list or catalog.
2. If the repository keeps its own catalog or allowlist of model names, check
   that too — it is the thing that will reject an unknown ID at runtime.
3. Where the exercised path makes a real request, resolve it live.

An unresolvable ID fails with an explicit unknown-model error at request time,
not at build time. Local tests pass. This is why a green build is not proof
for a change on a network path.

## Request surfaces

The migration character follows the surface, and Google's families do not all
share one. See `references/call-surfaces.md` for the side-by-side.

**Text generation to text generation** — same `generateContent` surface, same
parameters, same response handling. Mechanical. Rewriting the identifier
everywhere it dispatches a request is the complete migration.

**Image generation** — the dedicated Imagen API and Gemini native image
generation are different surfaces. Gemini produces images through the text
call with image output requested, and the image parts are read off the
response rather than returned as image results. An identifier rewritten in
place here routes a Gemini model down an endpoint it does not implement.

The options each surface carries differ, and several Imagen options have no
Gemini equivalent. Classify them with `api-migration`'s
`references/capability-loss.md`.

## Credentials

Google generative access reaches the workspace under more than one variable
name depending on the SDK and whether the repository routes through Vertex.
Do not assume a name: list what the runtime actually has, compare it against
what the live path reads, and request the specific missing name.
