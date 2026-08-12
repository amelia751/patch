# `packages.schemas`

Versioned Pydantic contracts for every object PatchAPI agents and services hand
to each other. Runtime code passes these models, never untyped dicts.

## Contracts

| Model | Produced by | Roadmap |
|---|---|---|
| `ChangeManifest` | Change Intelligence agent | §8.1 |
| `ImpactReport` | Impact agent | §8.2 |
| `PolicyDecision` | Policy & Risk agent | §8.3 |
| `PatchPlan` | Patch agent | §8.4 |
| `VerificationReport` | Verification agent | §8.5 |
| `RunState` + transition table | orchestrator | §9 |

Supporting types: `SourceSnapshot` and `EvidenceRef` (hashed evidence),
`ImpactFinding`, and the closed vocabularies in `enums.py`.

## Versioning

Every contract version is pinned in `config.py` under `CONTRACT_VERSIONS` and
nowhere else. Producers omit `schema_version` and receive the pinned value;
a document carrying a different version raises `ValidationError` rather than
being silently misread. Additive fields keep the version; anything a consumer
could trip over bumps it, and the agents on both sides change in the same batch.

## Constraints enforced by the types

These are product rules that must not depend on a prompt holding:

- `PolicyDecision.auto_merge` is typed `Literal[False]` — PatchAPI stops at the
  pull request.
- `VerificationReport` rejects a report whose verifier is also its patch author.
- `VerificationReport.verdict == PASS` is only constructible when every check
  passed, no unexpected file was touched, the retired identifiers are gone, and
  evidence exists. An unavailable live check is `INCONCLUSIVE`.
- `ChangeManifest` stays labelled untrusted provider input and cannot carry
  remediation instructions — unknown fields are rejected outright.
- Repository paths cannot be absolute or traverse upwards.

## Tests

```bash
./scripts/verify_packages_schemas.sh
```

Golden documents live in `tests/golden/`; `tests/golden/invalid/` holds the
manifests the schema must reject, indexed with their expected error location in
`tests/golden/invalid_manifests.json`.
