# ast-grep rules — Layer B

Layer A finds a provider identifier as a string. These rules decide whether the
line is a call site or a configured value rather than prose, so a reviewer sees
runtime breakage before documentation.

A rule may only sharpen the answer. If ast-grep is not installed, or a rule
fails to parse, Layer A's findings stand unchanged — losing precision is
acceptable, losing a finding is not.

## One directory per provider

Rules live under `<provider>/`, named by that provider's `rule_namespace` in
`packages/providers/descriptors/`. Only the subscribed provider's directory runs
against its own candidates: a Google rule that confirmed a Stripe finding would
record a `surface` naming a call shape the finding is not, and rank it as
confirmed on evidence from the wrong provider.

A provider that ships no directory yet skips Layer B rather than failing. Its
Layer A findings stand, unconfirmed.

## Adding a provider rule

1. Put the file in `<provider>/` and name it `<provider>-<surface>.yml`. The
   stem is what the inventory records as the finding's `surface`, so it appears
   in the audit trail.
2. Declare exactly one `language`. ast-grep binds a rule to one grammar; a
   second surface (YAML, dotenv, Python) is a second file.
3. Constrain the metavariable that carries the identifier with a `regex` that
   agrees with `zoekt/patterns.py`. A rule that matches more than the Layer A
   pattern confirms lines Layer A never found, which no consumer reads.
4. Keep `severity: info`. These rules report; they never fail a build. `error`
   severity changes ast-grep's exit code and would be read as a broken rule.

## Testing

`services/repo_indexer/tests/test_astgrep_rules.py` covers every file in this
directory:

- the shape and required keys parse without the binary installed, so a
  malformed rule is caught in CI whether or not ast-grep is on the runner;
- with `ast-grep` on PATH, each rule matches a real call site in the fixture
  tree, does **not** match prose that merely mentions "imagen", and does not
  match another provider's call sites.

```bash
uv run pytest services/repo_indexer/tests/test_astgrep_rules.py
```

The prose case is the one that matters. A rule that also fires on a README turns
a docs mention into a migration PR.
