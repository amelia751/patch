# Google generative request surfaces, side by side

What makes a Google migration mechanical or semantic is which of these the
retired identifier and its replacement sit on.

## Text generation

One surface. `generateContent` with a model ID, a prompt, and generation
config. Response parts are text.

Every Gemini text model dispatches here, so moving between them is a rewrite of
the identifier and nothing else. Same request shape, same parameters, same
response handling, no option to map or drop.

## Image generation

Two surfaces, and they are not interchangeable.

| | Imagen | Gemini native image |
|---|---|---|
| Dispatch | dedicated image-model API — AI SDK image model, or Vertex `predict` | the text call, with image requested in the response modalities |
| Request | prompt plus image-specific arguments | messages, with `responseModalities` including `IMAGE` and image settings nested in an image config |
| Output | image results returned by the image call | image parts read off the response files alongside any text |
| Count | returns n candidates per call | no count argument; one image per call |

A repository usually expresses this as a dispatch branch — an image strategy
that calls the image model, and a text strategy that calls `generateText`.
Migrating from Imagen to Gemini native image means the call site moves branch,
not just constant.

## Option dispositions between those two surfaces

Classify against what the affected call sites actually pass.

| Option | Imagen | Gemini image | Disposition |
|---|---|---|---|
| `aspectRatio` | yes | yes, nested in the image config | MAP — the multimodal surface accepts a wider ratio set |
| input / reference images | yes, dedicated argument | yes, as multimodal message content | MAP |
| `seed` | yes | no | HUMAN_REQUIRED — deterministic reseeding has no equivalent; dropping it changes a reproducibility guarantee |
| image count | yes | no | HUMAN_REQUIRED — the text surface takes no count |
| inpainting | yes | no | HUMAN_REQUIRED — mask-guided edit semantics are not expressible as a prompt without changing behaviour |
| mask image | yes | no | HUMAN_REQUIRED — carrier for inpainting; the text path never forwards it |
| `negativePrompt` | yes | no | HUMAN_REQUIRED — no provider-level negative prompt. Folding it into the positive prompt is a behaviour change, not a mapping |
| quality | yes | no | HUMAN_REQUIRED — image-model-only knob |
| resolution | yes, pixel-oriented | closest analogue is an image size bucket | HUMAN_REQUIRED — different value space, so it is a decision rather than a rename |
| output format | yes | no | HUMAN_REQUIRED — the multimodal path reports the media type it produced; it does not accept a requested container |

Watermarking behaviour also differs between the surfaces and is not something
the caller opts into. If the repository documents its output as unwatermarked,
that statement is part of the migration.

## The failure this prevents

Rewriting an Imagen identifier to a Gemini one while leaving the call on the
image path produces code that builds, passes any test that does not issue a
request, and fails at runtime with an unimplemented surface. Moving it to the
text path without classifying the options produces code that works and quietly
drops behaviour the caller depended on.

Neither is caught by a green build. Both are caught by reading the dispatch
branch before planning the edit.
