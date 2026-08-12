# fixture: a repository that still calls Imagen 4

Fixture checkout for `scripts/verify_services_repo_indexer.sh`. It is not a real
project and is never built; it exists so the Layer A indexer can be exercised
against a tree whose expected findings are known exactly.

Image generation currently runs on `imagen-4.0-generate-001`. This mention is
documentation, so the indexer must classify it as `documentation_example` and
not as a runtime usage.
