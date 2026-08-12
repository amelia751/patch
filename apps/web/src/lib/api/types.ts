/**
 * Wire types for the PatchAPI control plane.
 *
 * These mirror the Pydantic response models in
 * `services/control_api/src/patchapi_control_api/`. The contracts are strict on
 * the server — an unexpected key is a rejection, not something dropped — so
 * these declarations are the same shape rather than a loose superset.
 *
 * `null` is used where the server sends null, and it is meaningful in every
 * case: a missing source hash means no provider evidence was captured, a
 * missing exit code means the step never ran. Nothing here may be defaulted to
 * a passing value when it is absent.
 */

/** The deterministic run state machine (roadmap §9). */
export type RunState =
  | "RECEIVED"
  | "SANITIZED"
  | "NORMALIZED"
  | "IMPACT_SCANNING"
  | "UNAFFECTED"
  | "POLICY_EVALUATION"
  | "HUMAN_REQUIRED"
  | "BLOCKED"
  | "PATCHING"
  | "BUILDING"
  | "RETRY_PATCH"
  | "TESTING"
  | "VERIFYING"
  | "FAILED"
  | "PR_CREATING"
  | "PR_CREATED";

export interface ChangeRecord {
  change_id: string;
  provider: string;
  change_kind: string;
  title: string;
  source_urls: string[];
  /** Null when no provider snapshot was captured. Never render as evidence. */
  source_sha256: string | null;
  affected_identifiers: string[];
  recommended_replacement: string | null;
  effective_at: string | null;
  detected_at: string;
  affected_repositories: number;
  open_runs: number;
  total_runs: number;
}

/** Detection layers from roadmap §11.3. */
export type DetectionLayer = "A_DETERMINISTIC" | "B_SYNTAX_AWARE" | "C_SEMANTIC";

export interface UsageRecord {
  identifier: string;
  surface: string | null;
  file_path: string;
  line_start: number;
  line_end: number | null;
  detection_layer: DetectionLayer;
  confidence: number;
  observed_sha: string;
}

export interface RepositoryImpactRecord {
  repository: string;
  owner_team: string | null;
  criticality: string;
  affected: boolean;
  indexed_sha: string | null;
  indexed_at: string | null;
  usage_count: number;
  file_count: number;
  identifiers: string[];
  usages: UsageRecord[];
  latest_run_id: string | null;
  latest_run_state: RunState | null;
}

export interface RunSummaryRecord {
  run_id: string;
  state: RunState;
  repository: string;
  change_id: string;
  base_sha: string;
  trace_id: string | null;
  attempts_used: number;
  attempt_budget: number;
  started_at: string;
  updated_at: string;
  ended_at: string | null;
  failure_reason: string | null;
}

export interface TransitionRecord {
  sequence: number;
  from_state: RunState | null;
  to_state: RunState;
  actor: string;
  reason: string | null;
  occurred_at: string;
}

export interface PolicyDecisionRecord {
  decision: string;
  risk: string;
  auto_patch: boolean;
  auto_pr: boolean;
  /** Always false. Constraint 3 — PatchAPI stops at the pull request. */
  auto_merge: boolean;
  forbidden_globs: string[];
  required_checks: string[];
  reason: string;
  policy_version: string;
  evaluated_at: string;
}

export interface PatchAttemptRecord {
  attempt_number: number;
  status: string;
  patch_agent: string;
  patch_model: string;
  prompt_version: string | null;
  sandbox_ref: string | null;
  /** Null means the step never ran in isolation. It is not a pass. */
  build_exit_code: number | null;
  test_exit_code: number | null;
  diff_sha256: string | null;
  files_changed: number | null;
  failure_summary: string | null;
  started_at: string;
  ended_at: string | null;
}

export interface VerificationCheckRecord {
  name: string;
  passed: boolean;
}

export interface VerificationRecord {
  verdict: string;
  verifier_agent: string;
  verifier_model: string;
  patch_agent: string;
  patch_model: string;
  checks: VerificationCheckRecord[];
  evidence_summary: string | null;
  evaluated_at: string;
  attempt_number: number;
}

export interface ArtifactRecord {
  kind: string;
  uri: string;
  content_sha256: string;
  size_bytes: number;
  media_type: string;
  attempt_number: number | null;
  created_at: string;
}

export interface PullRequestRecord {
  number: number;
  url: string;
  title: string;
  head_branch: string;
  base_branch: string;
  head_sha: string;
  state: string;
  /** Always false, and shown as such. */
  merged_by_patchapi: boolean;
  opened_at: string;
  observed_at: string;
}

export interface RunDetailRecord {
  summary: RunSummaryRecord;
  change: ChangeRecord;
  transitions: TransitionRecord[];
  policy: PolicyDecisionRecord | null;
  attempts: PatchAttemptRecord[];
  verification: VerificationRecord | null;
  artifacts: ArtifactRecord[];
  pull_request: PullRequestRecord | null;
  usages: UsageRecord[];
}

export interface AuditEventRecord {
  actor: string;
  action: string;
  target: string | null;
  outcome: string;
  reason: string | null;
  trace_id: string | null;
  repository: string | null;
  run_id: string | null;
  occurred_at: string;
}

export interface FleetActorRecord {
  actor: string;
  actions: string[];
  succeeded: number;
  denied: number;
  failed: number;
  models: string[];
  last_seen_at: string;
}

export interface ReadinessCheck {
  name: string;
  ready: boolean;
  detail: string | null;
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  service: string;
  version: string;
  environment: string;
  checks: ReadinessCheck[];
}

export interface ChangeListResponse {
  changes: ChangeRecord[];
}

export interface RepositoryImpactResponse {
  change_id: string | null;
  repositories: RepositoryImpactRecord[];
}

export interface RunListResponse {
  runs: RunSummaryRecord[];
}

export interface RunDetailResponse {
  detail: RunDetailRecord;
  terminal: boolean;
  allowed_next: RunState[];
}

export interface FleetResponse {
  observed_actors: FleetActorRecord[];
  denials: AuditEventRecord[];
  policy_versions: string[];
}
