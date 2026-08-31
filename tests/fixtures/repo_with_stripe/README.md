# fixture: a repository that still calls removed Stripe.js methods

Fixture checkout for the provider-agnostic indexer tests. It is not a real
project and is never built; it exists so the indexer can be exercised against a
second provider's tree whose expected findings are known exactly.

Card confirmation currently runs through `stripe.handleCardPayment`. This
mention is documentation, so the indexer must classify it as
`documentation_example` and not as a runtime usage — the same rule that governs
the Google fixture, applied to a provider with no Python of its own.
