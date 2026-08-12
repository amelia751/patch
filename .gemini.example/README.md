# Gemini CLI project config (example)

Copy into a local `.gemini/` directory (gitignored):

```bash
mkdir -p .gemini
cp .gemini.example/settings.json .gemini/settings.json
cp .gemini.example/env.example .gemini/.env
# edit .gemini/.env — set absolute path to .secrets/gcp-service-account.json
```

Install CLI: `npm install -g @google/gemini-cli`

Auth for this repo: **Vertex AI** via service account (`security.auth.selectedType: vertex-ai`).

Smoke:

```bash
gemini -p "Reply with exactly: OK" -m gemini-3.5-flash --skip-trust --approval-mode plan
```

Docs: https://geminicli.com/docs/get-started/authentication/
