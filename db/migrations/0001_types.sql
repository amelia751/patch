-- Enumerated domains for the console (auth, GitHub import, projects).
--
-- PatchAPI workflow types (run_state, policy_decision_kind, …) are not here.
-- Those tables come back in a later migration when the remediation product
-- is wired onto this tenancy model.

CREATE TYPE user_type AS ENUM (
    'personal',
    'team'
);

CREATE TYPE identity_provider AS ENUM (
    'github',
    'google',
    'password'
);

CREATE TYPE project_status AS ENUM (
    'draft',
    'idle',
    'pending',
    'analyzing',
    'ready',
    'error'
);

CREATE TYPE cloud_provider AS ENUM (
    'aws',
    'gcp'
);

CREATE TYPE repository_kind AS ENUM (
    'backend',
    'frontend'
);

CREATE TYPE secret_row_status AS ENUM (
    'configured',
    'pending'
);
