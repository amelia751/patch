# `apps/web` — the PatchAPI dashboard

The operational view of PatchAPI: which provider changes have been ingested,
which repositories they touch, what each remediation run did, and what the
governance boundary refused.

Deliberately not a chat surface. PatchAPI is watched, not conversed with.

## Pages

| Route | Purpose |
|---|---|
| `/` | **Changes** — normalized provider changes, their deadlines, and whether a hashed source snapshot backs them |
| `/impact` | **Organization impact** — per-repository exposure from the API usage inventory, down to file and line |
| `/runs`, `/runs/[runId]` | **Runs** — deterministic state, transition timeline, policy verdict, patch attempts, independent verification, evidence, PR |
| `/fleet` | **Fleet & governance** — observed actors and, above all, refused actions |

## Running it

The dashboard reads the control plane server-side, so the control plane has to
be up and connected to Postgres first.

```bash
# 1. authoritative state
docker compose -f db/docker-compose.yml up -d
PYTHONPATH=db/src uv run python -m patchapi_db migrate
PYTHONPATH=db/src uv run python -m patchapi_db seed      # demo rows, clearly labelled

# 2. control plane, wired to Postgres
DATABASE_URL='postgresql://patchapi:patchapi_local_dev@127.0.0.1:55432/patchapi' \
HOST=127.0.0.1 PORT=8080 \
uv run --package patchapi-state patchapi-serve

# 3. dashboard
cd apps/web
echo 'PATCHAPI_API_URL=http://127.0.0.1:8080' > .env.local
npm install
npm run dev
```

`npm`, not pnpm — `scripts/verify_apps_web.sh` enforces it, and a stray
`pnpm-lock.yaml` fails that verifier.

### Configuration

| Variable | Meaning |
|---|---|
| `PATCHAPI_API_URL` | Control plane base URL. Defaults to `http://127.0.0.1:8080`. |

Read on the server only. The browser never learns the API's address and there
is no public API route.

## How this UI treats missing data

The rule the whole dashboard is built around:

> An unreachable store and an empty store must never look the same.

`lib/api/client.ts` returns a result union rather than throwing, and every page
renders the four cases distinctly:

| Case | Rendered as |
|---|---|
| `ok` | the data |
| `unwired` | "This view has no data source", naming the unconfigured dependency |
| `unreachable` | "The control plane did not answer", stating that nothing could be read |
| `not-found` | "No such run/change" |

A genuinely empty answer gets its own `EmptyState`, worded as *the store
answered and holds nothing* — a different claim from any of the above.

Related conventions that follow from the same principle:

- A `null` exit code on a patch attempt renders as **did not run**, never as a
  pass (constraint 5).
- A change with no `source_sha256` says **no source snapshot captured**, so an
  unevidenced change cannot be mistaken for an evidenced one.
- `auto_merge: false` is displayed rather than omitted, so constraint 3 is shown
  being kept instead of assumed.
- The verification panel shows the verifier and the patch author side by side,
  so the independence in constraint 6 is visible, not merely enforced in the
  database.
- The Fleet page says **observed actors**, not *registered agents*: it aggregates
  the audit trail and is not an Agent Registry capability listing.

## Design system

Tailwind v4 plus a subset of shadcn/ui primitives in `src/components/ui/`.

Theme variables live in `src/app/globals.css`. The brand is three values:

```css
--brand-h: 10;
--brand-s: 67%;
--brand-l: 55%;
```

Change those to retheme the whole app. Run-state and verdict colours
(`--state-pass`, `--state-fail`, `--state-human`, …) are deliberately *not*
derived from the brand hue — a verdict must not change meaning when the brand
does.

Every custom property holds a bare HSL triplet, so `@theme inline` wraps each
one in `hsl()`. Passing a triplet through unwrapped yields an invalid colour
that browsers drop silently, which shows up as unstyled white surfaces rather
than as a build error.

Light and dark are driven by a `dark` class on `<html>`, set before first paint
by an inline script in `app/layout.tsx`. `ThemeToggle` flips that class and
writes `localStorage`; there is no React state mirroring it, which is what keeps
both the flash-of-wrong-theme and the hydration mismatch away.

## Checks

```bash
npm run lint
npm run build
../../scripts/verify_apps_web.sh    # clean install, lint, build, HTTP probe
```
