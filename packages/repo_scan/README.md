# `packages/repo_scan`

Deterministic Layer A of impact analysis (`roadmap.md` §7.4, §11.3): find the
literal provider identifiers a change manifest names, classify each hit by path,
and return them in an order that depends on the commit rather than on the
filesystem.

No model runs here. The same checkout always produces the same inventory.

```python
from packages.repo_scan import scan_tree

result = scan_tree("demo/storygen/checkout", ["imagen-4.0-generate-001"])
result.matched_identifiers  # ('imagen-4.0-generate-001',)
result.runtime_hits         # docs-only hits excluded
```

Verified by `./scripts/verify_packages_remaining.sh`.
