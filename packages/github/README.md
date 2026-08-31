# `packages/github`

The narrow GitHub capability vocabulary, plus the
reference types those capabilities operate on.

This package holds no credentials and makes no network calls. It exists so the
allowlist is a checked enum rather than a string compared at a call site, and so
a forbidden operation (`merge_pull_request`, `change_branch_protection`,
`modify_actions_secrets`, …) is refused with a distinct, auditable error.

```python
from packages.github import resolve_capability, ForbiddenCapabilityError

resolve_capability("open_pull_request")   # -> Capability.OPEN_PULL_REQUEST
resolve_capability("merge_pull_request")  # -> ForbiddenCapabilityError
```

Verified by `./scripts/verify_packages_remaining.sh`.
