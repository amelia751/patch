# `packages/events`

The envelope every PatchAPI Pub/Sub message travels in, and
the idempotency keys that keep a resumed run from repeating an external action
(§9).

Two rules are enforced at construction, not by convention:

- **References, not content.** Payload values are bounded scalars or flat lists
  of scalars, so a diff or a source file cannot ride along in an event. Store it
  and send the URI.
- **Provenance is carried.** Every envelope states whether the material it
  refers to is `untrusted_provider_input` or `internal_analysis`.

```python
from packages.events import ActionType, EventEnvelope, EventType, TrustLevel, idempotency_key

envelope = EventEnvelope(
    event_type=EventType.PROVIDER_CHANGE_DETECTED,
    event_id="evt-1",
    run_id="run-storygen-001",
    occurred_at="2026-08-11T23:00:00Z",
    trust=TrustLevel.UNTRUSTED_PROVIDER_INPUT,
    payload={"change_id": "google-imagen4-retirement", "source_uri": "https://…"},
).with_idempotency_key(idempotency_key("run-storygen-001", ActionType.OPEN_PULL_REQUEST, sha))
```

`occurred_at` is passed in rather than read from the clock, so an envelope is a
pure function of its inputs and a replayed run rebuilds the same message.

Verified by `./scripts/verify_packages_remaining.sh`.
