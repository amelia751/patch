# Egaki demo script

Flagship scenario: **Google Imagen 4 retirement → Gemini native image model**,
against a pinned fork of `remorses/egaki`.

Target length **4:00**. Every claim below is either measured (marked ✅ with the
observed result) or explicitly marked ⚠️ as not yet built. Nothing here may be
narrated as working until its row says it is.

---

## What is frozen, and why that is legitimate

| Frozen | Reason |
|---|---|
| Fork + SHA `c09e1a4` | upstream may migrate before judging; a moving baseline is not a baseline |
| Provider fixture + hashed source snapshot | website latency and HTML drift must not decide a live demo |
| `pnpm install` cache | install time is not the story |
| Image prompt | keeps the on-screen result comparable between takes |

**Never frozen:** sandbox execution, build output, test results, the live model
call, PR creation. If any of those cannot run, the demo says so on camera. A
faked result is disqualifying, and it is also unnecessary — the blocked path is
itself a legitimate part of the story (see 3:10).

---

## Pre-flight (before recording)

```bash
scripts/verify_demo_egaki.sh          # steps 1-3 must PASS
```

✅ Measured 2026-08-11 at the pinned SHA:

- checkout HEAD `c09e1a44200ff5e951746e013035e68aeb3a14b1`
- `imagen-4.0-generate-001` → **30 hits**; `-ultra-` → 10; `-fast-` → 7
  (**47 total across 14 files**)
- `pnpm install --frozen-lockfile` → PASS (19.8s, ~24 benign `.bin/egaki`
  ENOENT warnings — the workspace self-links the CLI before it is built)
- `pnpm --dir cli build` → PASS
- `pnpm --dir cli test` → **PASS, 14 files, 444 tests**

⚠️ The live replacement-model call is **BLOCKED**, not passing — see 3:10.

---

## Beat sheet

### 0:00–0:25 — The problem

> "An external API changes. Somewhere in your organization, code depends on it.
> Today, finding out is a person's job."

On screen: Google's official Imagen 4 retirement notice, **live URL**. Then cut
to the captured, hashed snapshot in `demo/fixtures/`.

> "We show you the live page. We run against a hashed snapshot of it — so the
> run is reproducible and the source stays verifiable."

### 0:25–1:00 — Detection

Dashboard → Changes → the Imagen 4 retirement, effective 2026-08-17.
Organization impact → the pinned Egaki repository.

Say the measured numbers: **47 references across 14 files.**

> "External providers are untrusted input here. The notice is data. Only our own
> agents decide what it means for your code."

### 1:00–1:50 — Impact, and the point of the whole product

This is the beat that separates PatchAPI from `sed -i`.

Show `cli/src/cli/model-catalog.ts` side by side:

```ts
const googleImagen = { strategy: 'image', features: { seed: true,  multipleImages: true,  inpainting: true  } }
const googleText   = { strategy: 'text',  features: { seed: false, multipleImages: false, inpainting: false } }
```

> "Imagen and Gemini image generation are not two spellings of the same call.
> Imagen goes through the image API and supports seed, multiple images, and
> masks. Gemini image comes back as parts of a text generation call, and does
> not. Rewriting the model id and keeping the old strategy produces code that
> compiles, passes 444 tests, and is wrong."

Then the sharpest single fact in the demo:

> "The provider notice recommends `gemini-3.1-flash-image`. That id does not
> exist in this repository's model catalog — it's
> `gemini-3.1-flash-image-preview`. We ran it: the CLI answers
> `Unknown model`. A string replace ships a broken build."

✅ Measured — this is a real observed CLI error, not an illustration.

### 1:50–2:20 — Policy (the security moment)

Feed `demo/adversarial/ci-workflow-edit-request.md`.

```text
POLICY BLOCK
Reason: path outside PatchAPI application-code mutation boundary
Path:   .github/workflows/release.yml
```

> "That's a deterministic rule, evaluated before any model proposes a diff. It
> doesn't depend on the model noticing the request was hostile."

Keep this to one security moment. Option A (forbidden path) is deterministic;
prompt-injection detection is probabilistic and does not belong on the critical
path of a recording.

### 2:20–3:10 — Sandbox: patch and verify

Patch is generated and applied **in an isolated sandbox**, never in a developer
checkout.

Show live: `pnpm --dir cli build`, then `pnpm --dir cli test` → 444 passing.

> "Different agent, different model instance. The agent that writes the patch
> does not grade it."

Call out the capability deltas the patch surfaces: `seed`, `-n`, `--mask`,
`--negative-prompt` do not survive the move to the Gemini path.

> "It doesn't quietly drop them. It reports them, and that's what makes this
> reviewable."

### 3:10–3:35 — Fail closed (do not skip this beat)

⚠️ **Current true state — say it plainly.**

> "The live call to the replacement model is blocked. Our AI Studio key is out
> of credits, and this CLI only accepts an API key for Vertex — it won't take
> our service-account credentials. So verification returns HUMAN_REQUIRED, not
> PASS. Build green and tests green are not enough when the entire point is that
> the new model works."

This is a *strength* on camera. A system that reports PASS when it could not
run the decisive check is a system nobody should trust.

If credentials are restored before recording: swap in the live generated image,
show `verification.png`, and move the verdict to PASS. Do not narrate a PASS the
run did not produce.

### 3:35–4:00 — The pull request, and stopping

Show the PR: pinned base SHA, the diff, the evidence trail, the capability-loss
callouts, the verification verdict.

> "And then it stops. PatchAPI never merges, never deploys, never touches branch
> protection or CODEOWNERS. Your existing controls stay authoritative. It hands
> a human an evidence-backed review, and gets out of the way."

Branch: `patchapi/google-imagen4-retirement-2026-08`
Title: `Migrate Google image generation off retired Imagen 4 models`

---

## Reliability checklist

Before the take:

- [ ] `scripts/verify_demo_egaki.sh` PASS (steps 1–3)
- [ ] checkout HEAD is exactly `c09e1a4…` — `git rev-parse HEAD`
- [ ] `pnpm install` warm; `node_modules` present
- [ ] dashboard reachable; run trace renders
- [ ] `demo/egaki/artifacts/` cleared of stale images so nothing old is shown as new
- [ ] G-07 status known **before** recording, so 3:10 is narrated correctly
- [ ] no secret visible in any terminal, env dump, or dashboard panel

Hard rules on camera:

- Never show a result the run did not produce.
- Never narrate a PASS for a gate that was BLOCKED or SKIPPED.
- If something fails live, show it. Fail-closed behavior is the product.

---

## Open items before this is recordable

| Item | Status | Owner |
|---|---|---|
| Live Gemini image call from the Egaki CLI | ⚠️ BLOCKED — AI Studio credits exhausted; CLI won't accept ADC | needs AI Studio credits **or** a Vertex express API key |
| Hashed provider source snapshot | ⚠️ not captured — no network access in this worker | fixture records `NOT_CAPTURED`; must be filled before the demo |
| Manual migration performed end to end by a human | ⚠️ not done — roadmap Phase 0 exit criterion | blocked on the live call above |
| Dashboard run trace | ⚠️ not built | frontend |
| Sandbox execution | ⚠️ not built | sandbox |
| PR creation | ⚠️ deferred — GitHub App not configured | github-tools |
