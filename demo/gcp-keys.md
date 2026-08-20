# Local GCP keys

These files live under `demo/` for local use. They are gitignored. Do not
commit them, paste them, or put them in a pull request.

Project **`artful-journey-486915-a8`** (number `1005432364863`).

| File | Service account | Role |
|---|---|---|
| `artful-journey-486915-a8-c0699c9e2545.json` | `jetrun-viewer@…` | Viewer. `roles/run.viewer` can list Cloud Run services and see env **names** / Secret Manager **refs** on `storygen` (`GEMINI_API_KEY` → `storygen-gemini-api-key`). Cannot list secrets (`secretmanager.secrets.list` denied). Cannot create services or list service-account keys. |
| `artful-journey-486915-a8-fc72d9d68c0b.json` | `development@…` | Development. Use this to deploy Storygen (`./demo/storygen/deploy.sh`). |

Point `GOOGLE_APPLICATION_CREDENTIALS` at the development file unless you
explicitly need the viewer key.

Live Storygen URL (service name is the URL):

https://storygen-1005432364863.us-central1.run.app
