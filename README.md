# PatchAPI

**Dependabot for APIs.** When an external API changes, PatchAPI finds the
affected code, generates and verifies a migration in an isolated environment,
and opens an evidence-backed pull request for normal human review.

Built for the [All Things Agentic Hackathon](https://allthingsagentichackathon.devpost.com/)
— Fortified Enterprise Fleet track.

## Status

Early scaffold. Authoritative plan: [`roadmap.md`](./roadmap.md).

Flagship demo target: pinned fork of [`remorses/egaki`](https://github.com/remorses/egaki),
migrating Google Imagen 4 → Gemini 3.1 Flash Image.

## Hosted console (stable Cloud Run)

These names are the URL. Do not rename or delete the services.

| | URL |
|---|---|
| Frontend | https://patchapi-web-913371146929.us-central1.run.app |
| Backend | https://patchapi-api-913371146929.us-central1.run.app |

Same services also answer at the classic `*.a.run.app` aliases. Prefer the
links above. Region is `us-central1`. Push to `main` deploys into these names
(`.github/workflows/deploy-cloud-run.yml`).

Local remains `http://localhost:3000` (dashboard) and `http://localhost:8080`
(control API).

## GitHub: OAuth login + import App

Create **one** GitHub App (not a separate OAuth App). The App’s user-to-server
OAuth is Continue with GitHub; its installation id is repo import
(`github_connections`). Tokens never go in Postgres.

[Register a new GitHub App](https://github.com/settings/apps/new) on the
`amelia751` account:

| Field | Value |
|---|---|
| GitHub App name | `PatchAPI` (or `PatchAPI Demo` if taken) |
| Homepage URL | `https://patchapi-web-913371146929.us-central1.run.app` |
| Callback URL | `https://patchapi-api-913371146929.us-central1.run.app/api/auth/github/callback` |
| Callback URL (local) | `http://localhost:8080/api/auth/github/callback` |
| Setup URL | `https://patchapi-api-913371146929.us-central1.run.app/api/auth/github/setup` |
| Redirect on update | checked |
| Webhook URL | `https://patchapi-api-913371146929.us-central1.run.app/v1/github/webhooks` |
| Webhook active | **off** until the receiver exists |
| Expire user authorization tokens | checked |
| Request user authorization (OAuth) during installation | checked |
| Where can this GitHub App be installed? | Any account |

Also add `http://127.0.0.1:8080/api/auth/github/callback` as a callback if the
form allows a third URL.

**Account permissions:** Email addresses → Read-only (login).

**Repository permissions** ([`roadmap.md`](./roadmap.md) §14):

| Permission | Access |
|---|---|
| Metadata | Read-only |
| Contents | Read and write |
| Pull requests | Read and write |
| Checks | Read-only |
| Administration, Secrets, Workflows, Deployments | No access |

**Subscribe to events** (harmless while the webhook is inactive): `push`,
`pull_request`, `installation`, `installation_repositories`.

After create:

1. Generate a private key. Move the PEM to `.secrets/github-app.pem` (`chmod 600`).
2. Copy App ID, Client ID, and Client secret into `.secrets/github-app.json`:

```json
{
  "app_id": 0,
  "client_id": "Iv1...",
  "client_secret": "...",
  "app_slug": "patchapi"
}
```

3. Generate a webhook secret (even with the webhook off) and put it in
   `.secrets/github-webhook-secret.txt`.
4. Do **not** install the App on every repo yet. Install it on
   `amelia751/egaki` (and later whatever the console imports).

Env the control plane will read (see `.env.example`):

```text
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY_PATH=.secrets/github-app.pem
PATCHAPI_GITHUB_OAUTH_CLIENT_ID=
PATCHAPI_GITHUB_OAUTH_CLIENT_SECRET=
PATCHAPI_GITHUB_OAUTH_REDIRECT_URI=http://localhost:8080/api/auth/github/callback
```

On Cloud Run the redirect URI is
`https://patchapi-api-913371146929.us-central1.run.app/api/auth/github/callback`.

### Google OAuth (already created)

Add the hosted origins to the existing Web client (APIs & Services →
Credentials). A service account cannot edit that client on this project:

| Field | Value |
|---|---|
| JavaScript origin | `https://patchapi-web-913371146929.us-central1.run.app` |
| Redirect URI | `https://patchapi-api-913371146929.us-central1.run.app/api/auth/google/callback` |

## Hard product boundary

PatchAPI **stops at the pull request**. It does not merge, deploy, edit branch
protection, or bypass CODEOWNERS / CI.

## Local agent fleet

Claude Code workforce tooling lives in `.fleet/` (gitignored). After cloning:

```bash
.fleet/bin/bootstrap.sh     # sync roles → .claude/agents, create ./fleet
./fleet doctor
./fleet roles
./fleet run smoke --dry-run
```

Project conventions for agents: [`CLAUDE.md`](./CLAUDE.md).
