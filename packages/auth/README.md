# `packages/auth`

Email/password identity for the control plane, backed by **Google Cloud Identity
Platform** (GCIP).

`IdentityPlatformService` is a method-for-method replacement for the AWS Cognito
client this codebase's sign-in flow was originally written against, so the auth
routes calling it did not change. Two differences in the underlying product are
absorbed inside this package rather than pushed up into routing:

| | Cognito | Identity Platform |
|---|---|---|
| Bearer credentials | separate access token and ID token | one ID token that is both |
| Email verification | six-digit code the user retypes | emailed link carrying an opaque `oobCode` |
| Unverified sign-in | blocked until confirmed | always permitted |

So `AuthTokens.access_token` and `.id_token` carry the same string, every `code`
argument is an `oobCode` supplied by a redirect rather than a keyboard, and
`admin_confirm_sign_up` is a truthful no-op — there is no confirmation gate left
to satisfy.

## Configuration

The Web API key resolves from the first of these that yields a value:

1. `PATCHAPI_IDENTITY_API_KEY`
2. `.secrets/identity_platform_api_key.txt` — the key alone
3. `.secrets/identity-platform.json` — the Firebase web-config blob

Unlike a service-account key, this one is not confidential: Firebase embeds it
in shipped client bundles and the browser needs it. It still lives in
`.secrets/` so that one file is the single place it is rotated for both the
browser and the control plane. The admin credential *is* confidential and is
resolved separately, from `GOOGLE_APPLICATION_CREDENTIALS`; only
`create_oauth_user` and `sign_out` need it.

`PATCHAPI_IDENTITY_ACTION_URL` is where Google's emails send the browser back
to. Its host must also appear in the project's authorized domains, or Identity
Platform refuses to mint the link.

## Project prerequisites

Against `patch-505223` these are already in place:

- `identitytoolkit.googleapis.com` and `securetoken.googleapis.com` enabled
- the email/password provider enabled (`signIn.email.enabled`)
- `localhost` and the Cloud Run dashboard hosts among the authorized domains

## Tests

```bash
uv run pytest packages/auth
```

Every provider call is stubbed at the transport boundary, so the suite runs
offline and never touches the project. It covers the two things a swap away
from Cognito can silently get wrong: that provider error tokens still reach the
browser as sentences the sign-in form expects, and that the methods whose
semantics changed still honour the contract their callers assume.
