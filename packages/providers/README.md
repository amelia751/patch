# packages/providers

Adapters that turn **untrusted** provider evidence into typed PatchAPI
contracts. Google is the first (and, for the hackathon demo, only) provider.

Two rules govern everything in this tree:

1. **Providers produce evidence, not decisions.** An adapter may say what a
   provider published — which identifiers retire, when, what the provider
   recommends instead, which capability notes it printed. It never says what a
   customer repository should do. Impact, Policy and Patch own that.
2. **Fail closed.** Provider text that does not parse, a fixture version this
   build does not know, or a snapshot that was never captured and hashed all
   raise rather than degrade into a partially-trusted manifest.

## Layout

| Module | Responsibility |
|---|---|
| `dotenv.py` | Parse `.env` / `.env.example` pins without overriding real environment values |
| `google/config.py` | Pinned model IDs, Vertex endpoint pins, model-generation guard |
| `google/deprecation_feed.py` | Strict model for the untrusted Google deprecation feed |
| `google/normalize.py` | Feed notice → `ChangeManifest` |
| `google/snapshot.py` | Hash captured provider pages into `SourceSnapshot` evidence |
| `google/vertex.py` | Live Vertex `generateContent` client (reasoning model) |
| `google/smoke.py` | `python -m packages.providers.google.smoke` — live model proof |

## Verify

```bash
./scripts/verify_packages_providers_google.sh
```

Runs the offline fixture→manifest tests and then the live Vertex smoke. The
live half is `SKIP` only when credentials are genuinely absent; it never
fabricates a model response.
