# AWS Multi-Environment UX Plan

## The Reality You're Designing For

Most users will land in one of three buckets:

| Bucket | Who | AWS accounts | What they know |
|---|---|---|---|
| **A. Solo dev / hackathon** | 80% of users at launch | 1 account | Doesn't know about Organizations. Has 1 IAM role. Wants to ship. |
| **B. Small startup** | 15% | 1 account, maybe thinking about splitting | Knows they "should" separate but hasn't yet |
| **C. Mature team** | 5% | 2–4 accounts via Organizations | Has a landing zone, separate dev/staging/prod accounts |

The current UX (`aws-connect-empty-state.tsx`) is built perfectly for Bucket A: one CloudFormation stack → one role ARN → done. That's the right first impression. The mistake would be forcing Bucket A users through a multi-environment setup wizard they don't need.

---

## The UX Model

### Phase 1 — Single connection, zero friction (what 80% of users see)

Exactly what exists now. User connects one AWS account. Internally stored as `(team_id, environment="default")`. The `"default"` fallback in `get_connection_for_env()` means this single connection serves dev, staging, and prod automatically.

- No environment picker in the connect dialog
- No confusion

### Phase 2 — Progressive disclosure (when they're ready)

On the existing `aws-connection-tab.tsx`, once connected, add a section below connection status:

```
┌──────────────────────────────────────────────┐
│  AWS Connection                  ● Connected │
│  Account: 123456789012                       │
│  Role: DeploymentRole               │
│  Region: us-east-1                           │
│  Serving: all environments                   │
│                                              │
│  ─────────────────────────────────────────── │
│  Environment Connections                     │
│                                              │
│  all (default)  123456789012  ● Active       │
│                                              │
│  Want to separate dev/staging/prod?          │
│  [+ Add environment connection]              │
└──────────────────────────────────────────────┘
```

When they click **+ Add environment connection**, a dialog asks:
1. **Environment** (dropdown: dev, staging, prod)
2. **Same account or different account?**
   - Same account → reuses the same role ARN, just tags resources differently
   - Different account → walks through CloudFormation again for the new account (same flow)
3. **Role ARN** (pre-filled if same account)

Result:
- Bucket A users never see complexity
- Bucket B users can split when ready without re-doing the whole setup
- Bucket C users can connect all their accounts upfront

---

## Migration Path (single → multi-account)

**User starts with 1 account serving everything:**
```
aws_connections:
  (team_id, "default") → account 111111111111, role DeploymentRole
```

**User later adds a prod account:**
```
aws_connections:
  (team_id, "default") → account 111111111111  ← still serves dev, staging
  (team_id, "prod")    → account 222222222222  ← new prod account
```

The lookup logic (`get_connection_for_env`) handles this automatically:
- Deploy to dev → tries `(team, "dev")` → miss → falls back to `(team, "default")` → uses 111111111111 ✅
- Deploy to prod → tries `(team, "prod")` → hit → uses 222222222222 ✅

**User later separates dev and staging too:**
```
aws_connections:
  (team_id, "default") → account 111111111111  ← now unused catch-all
  (team_id, "dev")     → account 111111111111  ← explicit dev
  (team_id, "staging") → account 333333333333  ← new staging account
  (team_id, "prod")    → account 222222222222  ← existing prod
```

No data migration. No downtime. The `"default"` connection just becomes dormant as explicit ones override it.

---

## Same Account, Different Environments (Bucket B)

One account, but logical separation. For AWS this means:
- Same role ARN for all environments
- Isolation via **resource tagging** (`Environment=dev`, `Environment=prod`) and **naming** (`myapp-dev-db`, `myapp-prod-db`)
- The agent already handles this — `environment` is passed to the pipeline and used in resource naming

UX for this case:
```
Add environment connection:
  Environment: [prod]
  AWS Account: [Same account (111111111111)]  ← pre-selected
  Role ARN: arn:aws:iam::111111111111:role/DeploymentRole  ← auto-filled
  [Connect]
```

The DB stores a separate row, but with the same `aws_account_id` and `role_arn`. The point is the system now *knows* this team has a deliberate prod environment, even if it's on the same account. This enables enforcing stricter rules for prod deploys (approval gates, restricted actions) even in a single-account setup.

---

## What NOT to Do

| ❌ Don't | Why |
|---|---|
| Ask about environment during first connect | Scary for 80% of users who don't need it. Default to `"default"` silently. |
| Require multi-account | A user on 1 account deploying to "prod" is valid. Show a gentle warning, not a gate. |
| Auto-detect Organizations | Needs `organizations:ListAccounts` — a massive trust escalation most users won't grant. Let them add manually. |
| Conflate "environment" with "account" | A user might use account 111111111111 for both dev and staging. Environment is logical; account is physical. Keep them separate in data model and UI. |

---

## CloudFormation Template Note

When a user adds a **second** account, the CloudFormation stack should use the **same external ID** (already tied to their team). This means:
- Trust policy is consistent across accounts
- User doesn't manage multiple external IDs
- Assume different roles in different accounts, but the trust relationship is always back to the same platform account

This already works with `generate_external_id_for_team()` — the external ID is per-team, not per-connection.

---

## Summary

| Concern | Answer |
|---|---|
| First-time UX | Unchanged. One account, zero friction. |
| When to show multi-env | After they connect. Progressive disclosure. |
| Migration path | Add rows, don't modify existing ones. `"default"` falls back automatically. |
| Same account, different envs | Fully supported. Same ARN, different logical envs. |
| Different accounts per env | Supported. Re-run CloudFormation in new account. Same external ID. |
| What if they never separate? | `"default"` serves everything forever. No penalty. |

---

## Backend Work Required (when implementing)

The backend schema change for GCP (`(team_id, environment)` unique, with `"default"` fallback) is the **exact same pattern** for AWS. Checklist:

- [ ] `AWSConnection` model: drop `unique=True` on `team_id`, add `environment` column, composite unique on `(team_id, environment)`
- [ ] `Team` model: change `aws_connection` (singular) → `aws_connections` (list)
- [ ] Add `get_aws_connection_for_env(team_id, environment, db)` helper with `"default"` fallback
- [ ] Update `POST /api/aws/connect` to upsert on `(team_id, environment)`
- [ ] Update `GET /api/aws/status` to accept `?environment=` param
- [ ] Update `DELETE /api/aws/disconnect` to scope to specific environment
- [ ] Update `POST /api/aws/revalidate` to scope to specific environment
- [ ] Add `GET /api/aws/connections` to list all environments for a team
- [ ] Update pipeline to call `get_aws_connection_for_env(team_id, request.environment)` instead of looking up by `team_id` alone

## Frontend Work Required (when implementing)

- [ ] `aws-connection-tab.tsx`: add "Environment Connections" table showing all rows + `"Serving: all environments"` badge when only `"default"` exists
- [ ] `aws-connection-tab.tsx`: add "+ Add environment connection" button with dialog (env picker, same/different account toggle, role ARN input)
- [ ] `aws-connect-empty-state.tsx`: no changes needed (keep zero-friction first connect)
- [ ] Show gentle warning when `"prod"` environment is on the same account as `"dev"` (not a gate, just info)
