-- Role follows the kind of change, not the fact of being named.
--
-- 0014 backfilled every identifier as 'retired', which is wrong for the notices
-- that retire nothing: a new-identifier announcement names the model it is
-- introducing, and a false-positive card names the string it exists to rule
-- out. Left as-is, "Gemini 3.5 Flash generally available" would join against
-- indexed usage as a retirement and open a finding telling somebody to migrate
-- off the model they just adopted.
--
-- A replacement pointing at itself is likewise an artefact of the flat
-- `replacements` array, where a new-identifier note recorded from/to as the
-- same string to say "already current". Per identifier that reads as a move to
-- nowhere, so it is dropped.

UPDATE change_event_identifiers i
SET role = 'mentioned'
FROM change_events e
WHERE e.id = i.change_event_id
  AND i.role = 'retired'
  AND (
      e.false_positive
      OR e.change_kind NOT IN ('deprecation', 'replacement', 'breaking_change')
  );

UPDATE change_event_identifiers
SET replacement = NULL
WHERE replacement = identifier;
