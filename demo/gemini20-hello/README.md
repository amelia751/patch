# gemini20-hello — vertical-slice migration target

A standalone Python 3.12 tree (no dependencies, no network) that pins a real
Google shutdown: `gemini-2.0-flash` and `gemini-2.0-flash-001` — along with the
two `-lite` variants — stopped serving on 2026-06-01, and the June 1, 2026
changelog directs callers to `gemini-3.5-flash` (or `gemini-3.1-flash-lite` for
the lite variants). `generate.py` declares one model identifier and exits
non-zero while that identifier is one of the four retired ids, so the Patch
agent and the sandbox loop can be exercised end to end — find the usage, rewrite
the identifier, run the gate in isolation, watch it flip — without waiting on
the Egaki checkout, an installed SDK, or provider credentials. Egaki remains the
flagship demo; this tree is the loop's unit test, and unlike Egaki this change
genuinely is a model-ID rewrite.

Official sources:

- <https://ai.google.dev/gemini-api/docs/deprecations>
- <https://ai.google.dev/gemini-api/docs/changelog>

Both are quoted, hashed, and pinned in
`demo/fixtures/google-gemini20-deprecation.json`.

## Running it

```bash
python3 demo/gemini20-hello/generate.py            # exit 1 before the patch
python3 -m unittest demo/gemini20-hello/test_generate.py   # fails before the patch
```

After a correct migration — `MODEL = "gemini-3.5-flash"` — `generate.py` prints
`ok:gemini-3.5-flash` and both commands exit 0.

`RETIRED_MODELS` and `test_generate.py` are the grading apparatus, not usages.
Editing either reaches green without migrating anything;
`expected-findings.yaml` records that as an automatic fail.
