/**
 * The run shape the panel draws, and helpers that answer from that run's
 * own evidence. Nothing here invents a diff, a command, or a check.
 */

import type { ChangeActionId, RunProgress } from "./actions";
import type { FileHit } from "./data";
import type { RunFixture } from "./run-timeline";

export type RunBucket =
  | "active"
  | "needs_attention"
  | "waiting"
  | "ready_for_review"
  | "idle"
  | "blocked";

export type MachineState =
  | "NORMALIZED"
  | "IMPACT_SCANNING"
  | "POLICY_EVALUATION"
  | "HUMAN_REQUIRED"
  | "WAITING_ON_OPERATOR"
  | "PATCHING"
  | "BUILDING"
  | "TESTING"
  | "VERIFYING"
  | "PR_CREATED"
  | "UNAFFECTED"
  | "HELD"
  | "FAILED"
  | "BLOCKED";

/** Dual-CTA Need-you pause: connect GCP or add the verifier key. */
export const HUMAN_REQUIRED_PAUSE =
  "This run is waiting on you. Connect GCP or add GEMINI_API_KEY so the agent can continue.";

export const HUMAN_REQUIRED_SECRET_NAME = "GEMINI_API_KEY";

/** What a FAILED run actually said. Verification-disagreed is only the default
 * when the job never recorded a reason — dispatch never starting is not that. */
export function failureCopy(reason: string | null | undefined): string {
  const trimmed = (reason ?? "").trim();
  return trimmed || "Verification disagreed. Fail closed. No pull request.";
}

export type TreeId = "base" | "sandbox" | "proposed";

export type CommandPhase = "patch" | "build" | "test";

export interface DiffLine {
  kind: "ctx" | "add" | "del";
  text: string;
}

export interface DiffFile {
  path: string;
  additions: number;
  deletions: number;
  lines: DiffLine[];
}

export interface SandboxCommand {
  phase: CommandPhase;
  argv: string;
  exit: number | null;
  tail: string;
  /** Baseline is the repository before any patch; omitted means after. */
  source?: "baseline" | "patched";
}

export interface VerifyCheck {
  name: string;
  passed: boolean;
}

export type LogKind = "thought" | "action" | "result" | "narration" | "block";

export interface AgentLogLine {
  id: string;
  at: MachineState;
  kind: LogKind;
  verb?: string;
  text: string;
  toolType?: string;
  toolUseId?: string;
  filePath?: string;
}

export interface MockRun {
  id: string;
  code: string;
  changeId: string;
  title: string;
  repo?: string;
  baseSha?: string;
  fileHits?: number;
  fileCount?: number;
  identifiers: string[];
  replacement?: string;
  files: FileHit[];
  action: ChangeActionId;
  machine: MachineState;
  path: MachineState[];
  bucket: RunBucket;
  createdAt: number;
  attempt: number;
  attemptBudget: number;
  pauseReason?: string;
  /** Setup actions on the Need-you banner. Both buttons live on the same pause. */
  need?: "secret" | "gcp";
  commands: SandboxCommand[];
  diffs: DiffFile[];
  checks: VerifyCheck[];
  log: AgentLogLine[];
  revealed: number;
  lineStartedAt: number;
  prBranch?: string;
  prBase?: string;
  prUrl?: string;
  prNumber?: number;
  prTitle?: string;
  traceId: string;
  /** Raw job trace for the phase log. */
  logSource?: RunFixture;
}

export const MACHINE_LABEL: Record<MachineState, string> = {
  NORMALIZED: "Normalizing",
  IMPACT_SCANNING: "Scanning inventory",
  POLICY_EVALUATION: "Policy",
  HUMAN_REQUIRED: "Needs you",
  WAITING_ON_OPERATOR: "Needs you",
  PATCHING: "Patching in sandbox",
  BUILDING: "Clean build",
  TESTING: "Clean tests",
  VERIFYING: "Independent verify",
  PR_CREATED: "PR opened",
  UNAFFECTED: "No runtime path",
  HELD: "Held",
  FAILED: "Failed",
  BLOCKED: "Blocked",
};

export function inboxProgressFor(bucket: RunBucket): RunProgress {
  if (bucket === "ready_for_review") return "pr_opened";
  if (bucket === "active" || bucket === "needs_attention" || bucket === "waiting") return "running";
  if (bucket === "idle" || bucket === "blocked") return "pr_opened";
  return "idle";
}

/** States a run can only be in once it has a sandbox to work in. */
const PAST_SANDBOX: ReadonlySet<MachineState> = new Set<MachineState>([
  "PATCHING",
  "BUILDING",
  "TESTING",
  "VERIFYING",
  "PR_CREATED",
]);

/**
 * Whether this run actually has the tree in question.
 *
 * Answered from the run's own evidence, not from its state alone. `HUMAN_REQUIRED`
 * and `WAITING_ON_OPERATOR` can be reached before a sandbox exists or long after
 * the patch is verified, and a whitelist of states that omitted both told the
 * operator an allocated sandbox was "not allocated" and a passed verification was
 * "not verified".
 */
export function treeAvailable(run: MockRun, tree: TreeId): boolean {
  if (tree === "base") return true;
  if (tree === "sandbox") {
    return PAST_SANDBOX.has(run.machine) || run.commands.length > 0 || run.diffs.length > 0;
  }
  return run.diffs.length > 0 || run.machine === "PR_CREATED";
}

/** Why there is no proposed tree to show, in the operator's terms. */
export function proposedPending(run: MockRun): string {
  if (run.diffs.length === 0) return run.machine === "FAILED" ? "no patch" : "not patched yet";
  if (run.checks.length === 0) return "not verified";
  return "no pull request";
}

export function treeForMachine(run: MockRun): TreeId {
  if (treeAvailable(run, "proposed")) return "proposed";
  if (treeAvailable(run, "sandbox")) return "sandbox";
  return "base";
}
