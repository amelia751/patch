-- Repair jsonb columns that hold a JSON *string* instead of the value.
--
-- `packages/state/pool.py` registers a jsonb codec whose encoder is json.dumps.
-- Several call sites also called json.dumps before binding the parameter, so the
-- text `[]` was encoded a second time and landed as the scalar "[]". Postgres
-- accepts that happily: a bare string is valid jsonb. Nothing raised, and the
-- rows read back as text, so `identifier_counts` lost its keys and `files` lost
-- its elements. Half the findings in the dashboard rendered with no file hits.
--
-- `#>> '{}'` extracts the text a jsonb scalar wraps, which is the original JSON
-- document, so casting it back to jsonb undoes exactly one layer. The filter on
-- jsonb_typeof keeps this idempotent and leaves correctly stored rows untouched.

UPDATE change_events
SET replacements = (replacements #>> '{}')::jsonb
WHERE jsonb_typeof(replacements) = 'string';

UPDATE project_change_findings
SET identifier_counts = (identifier_counts #>> '{}')::jsonb
WHERE jsonb_typeof(identifier_counts) = 'string';

UPDATE project_change_findings
SET files = (files #>> '{}')::jsonb
WHERE jsonb_typeof(files) = 'string';

UPDATE provider_connections
SET parsed = (parsed #>> '{}')::jsonb
WHERE jsonb_typeof(parsed) = 'string';

UPDATE users
SET settings = (settings #>> '{}')::jsonb
WHERE jsonb_typeof(settings) = 'string';
