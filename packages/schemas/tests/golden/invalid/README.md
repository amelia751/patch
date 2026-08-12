# Manifests the schema must reject

Each file is a `ChangeManifest` document that differs from
`../change_manifest.imagen4.json` in exactly one way, and every one of them must
raise `ValidationError`. The filename states the defect; the test that loads
them asserts the error is reported against the field named in
`expected_error_locations` inside `../invalid_manifests.json`.

These are not run records. They exist so a schema change that quietly relaxes a
fail-closed rule breaks a test instead of reaching an agent.
