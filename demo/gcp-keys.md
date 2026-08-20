# Local GCP keys

These files live under `demo/` for local use. They are gitignored. Do not
commit them, paste them, or put them in a pull request.

| File | Role |
|---|---|
| `artful-journey-486915-a8-c0699c9e2545.json` | Viewer. Read-only access for looking at the project. |
| `artful-journey-486915-a8-fc72d9d68c0b.json` | Development. Use this for local PatchAPI work. |

Point `GOOGLE_APPLICATION_CREDENTIALS` at the development file unless you
explicitly need the viewer key.
