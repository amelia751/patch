# Storygen

A one-page Next.js writer: type a prompt, get a title, cover, and short story.
Words are not tokenized.

`lib/gemini.ts` pins two retired Google identifiers. Story text uses
`gemini-2.0-flash`, shut down 2026-06-01. The cover uses
`imagen-4.0-generate-001`, shut down 2026-08-17.

## Hosted (stable Cloud Run)

Service name is the URL. Do not rename or delete it.

| | |
|---|---|
| Project | `artful-journey-486915-a8` (number `1005432364863`) |
| Region | `us-central1` |
| Service | `storygen` |
| URL | https://storygen-1005432364863.us-central1.run.app |
| Deploy key | `demo/artful-journey-486915-a8-fc72d9d68c0b.json` (`development@…`) |
| Secret name | `storygen-gemini-api-key` |

Same shape as PatchAPI (`https://<service>-<project-number>.us-central1.run.app`).
The `*.a.run.app` alias also answers; prefer the stable link.

Pushes to `main` on [`amelia751/storygen`](https://github.com/amelia751/storygen)
deploy through GitHub Actions as the **development** key (repo secret
`GCP_SA_KEY` = `demo/artful-journey-486915-a8-fc72d9d68c0b.json`). Manual
redeploy uses the same key, not the viewer key:

```bash
./demo/storygen/deploy.sh
```

The Gemini key is Secret Manager `storygen-gemini-api-key`, not a literal
on the service. `jetrun-viewer@` has `roles/run.viewer`, so it can see that
**name** on the Cloud Run service (not a secret list — it has no
`secretmanager.secrets.list`):

```bash
export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE=demo/artful-journey-486915-a8-c0699c9e2545.json
gcloud run services describe storygen \
  --project=artful-journey-486915-a8 \
  --region=us-central1 \
  --format='yaml(spec.template.spec.containers[0].env)'
```

That prints `name: GEMINI_API_KEY` and
`secretKeyRef.name: storygen-gemini-api-key`. It does not print the payload.

A live `POST /api/story` returns 502 with both retired-model errors until
those identifiers are migrated.

## Local

```bash
cp .env.example .env.local   # set GEMINI_API_KEY
npm install
npm run dev
```

## Model check

`generate.py` does not call the network. It reads `MODEL` from `lib/gemini.ts`
and exits non-zero while that identifier is one of the four retired Gemini 2.0
Flash ids.

```bash
python3 generate.py
python3 -m unittest test_generate.py
```

After a correct migration — `MODEL = "gemini-3.5-flash"` in `lib/gemini.ts` —
`generate.py` prints `ok:gemini-3.5-flash` and both commands exit 0.
