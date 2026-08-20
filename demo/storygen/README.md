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

Same shape as PatchAPI (`https://<service>-<project-number>.us-central1.run.app`).

Billing is currently off on this project, so a new Cloud Run service cannot be
created. After billing is enabled:

```bash
./demo/storygen/deploy.sh
```

That script authenticates as the **development** key, not the viewer key.

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
