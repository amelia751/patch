# Imagen 4 retirement — migration guidance

Effective 2026-08-17, `imagen-4.0-generate-001` is retired. Callers should
migrate to `gemini-3.1-flash-image`.

## Request shape

The replacement model takes `contents` rather than `prompt`, and returns inline
image parts instead of a `predictions` array. Existing safety settings carry
over unchanged.

## Timeline

Requests to the retired model begin returning HTTP 404 after the effective
date. There is no automatic redirect.
