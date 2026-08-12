<!--
ADVERSARIAL FIXTURE — ADV-04 (roadmap §23 case 4): a repository that merely
contains the word "imagen" in prose. Pure false-positive probe. The correct
result is NO FINDING and NO RUN.

Nothing in this file is a Google Imagen 4 dependency.
-->

# Fixture — "imagen" without Imagen

Simulated repository: `example-org/localization-site`

## Occurrences a naive scanner would flag

### 1. Spanish prose — `content/es/galeria.md`

```markdown
Cada imagen de la galería se carga de forma diferida.
La imagen principal usa un formato moderno.
```

`imagen` is simply the Spanish word for "image". This is the single most likely
source of false positives for any substring matcher, and it will be common in
any repository with Spanish localization.

### 2. An unrelated product name — `README.md`

```markdown
Thumbnails are produced by Imagenator, our internal resizing service.
```

### 3. A different vendor's model — `config/models.json`

```json
{ "fallback": "fal-ai/imagen4/preview" }
```

A fal.ai–hosted model whose id contains `imagen4`. It is not a Google
first-party endpoint and is not covered by the Google retirement notice. The
same trap exists inside the flagship repo at
`cli/src/cli/model-catalog.ts:1332` (`expected-findings.yaml` F-10).

### 4. A CSS class — `styles/gallery.css`

```css
.imagen-grid { display: grid; }
```

---

## Expected outcome

```text
NO_FINDING
Repository not added to the API Usage Inventory for change
imagen4-retirement-2026-08-17.
```

## Why this case matters

Detection must key on the **exact affected identifiers** from the change fixture
(`imagen-4.0-generate-001`, `-ultra-`, `-fast-`) reached through a Google
provider path — not on the substring `imagen`. Deterministic Layer A matching
(roadmap §11.3) already excludes every occurrence above; case 3 is the only one
requiring provider-level reasoning, since it is a real model id from a different
vendor.

A false positive here is expensive in a way a miss is not: it opens a PR against
a team that has no exposure, and the second time that happens PatchAPI's output
gets filtered to spam.

## Pass criteria

- Zero `ImpactReport` entries.
- No run opened, no branch created, no PR.
- If a scanner surfaces any of these as candidates, they must be rejected before
  the Impact Report — appearing as suppressed candidates in the trace is
  acceptable and useful; appearing as findings is a failure.
