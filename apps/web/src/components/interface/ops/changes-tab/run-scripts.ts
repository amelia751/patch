/**
 * Simulated run plans. These are UI fixtures — they do not claim a real
 * sandbox, test, or PR outcome.
 *
 * A run is not a chat. It is a pinned base SHA, an isolated worktree the
 * Patch agent may edit, and — only after independent verification — a
 * proposed branch. The publisher stops at the pull request.
 */

import type { ChangeActionId } from "./actions";
import { isDocsOnly, type FileHit, type ProjectChange } from "./data";

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
  | "PATCHING"
  | "BUILDING"
  | "TESTING"
  | "VERIFYING"
  | "PR_CREATED"
  | "UNAFFECTED"
  | "HELD"
  | "FAILED"
  | "BLOCKED";

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
}

export interface VerifyCheck {
  name: string;
  passed: boolean;
}

export type LogKind = "thought" | "action" | "result" | "narration";

export interface AgentLogLine {
  id: string;
  at: MachineState;
  kind: LogKind;
  verb?: string;
  text: string;
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
  commands: SandboxCommand[];
  diffs: DiffFile[];
  checks: VerifyCheck[];
  log: AgentLogLine[];
  revealed: number;
  lineStartedAt: number;
  prBranch?: string;
  traceId: string;
}

export const MACHINE_LABEL: Record<MachineState, string> = {
  NORMALIZED: "Normalizing",
  IMPACT_SCANNING: "Scanning inventory",
  POLICY_EVALUATION: "Policy",
  HUMAN_REQUIRED: "Needs you",
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

export const RAIL: { at: MachineState[]; label: string }[] = [
  { at: ["NORMALIZED"], label: "Normalize" },
  { at: ["IMPACT_SCANNING", "UNAFFECTED"], label: "Impact" },
  { at: ["POLICY_EVALUATION", "HUMAN_REQUIRED", "HELD"], label: "Policy" },
  { at: ["PATCHING", "BUILDING", "TESTING"], label: "Sandbox" },
  { at: ["VERIFYING"], label: "Verify" },
  { at: ["PR_CREATED"], label: "PR" },
];

function bucketOf(machine: MachineState): RunBucket {
  if (machine === "HUMAN_REQUIRED") return "needs_attention";
  if (machine === "PR_CREATED") return "ready_for_review";
  if (machine === "UNAFFECTED" || machine === "HELD") return "idle";
  if (machine === "FAILED" || machine === "BLOCKED") return "blocked";
  return "active";
}

function pathFor(change: ProjectChange, action: ChangeActionId): MachineState[] {
  if (action === "prepare") {
    return ["NORMALIZED", "IMPACT_SCANNING", "HELD"];
  }
  if (action === "start" && isDocsOnly(change)) {
    return ["NORMALIZED", "IMPACT_SCANNING", "UNAFFECTED"];
  }
  const pause =
    action === "review" || !change.replacement || change.migration === "semantic";
  if (pause) {
    return [
      "NORMALIZED",
      "IMPACT_SCANNING",
      "POLICY_EVALUATION",
      "HUMAN_REQUIRED",
      "PATCHING",
      "BUILDING",
      "TESTING",
      "VERIFYING",
      "PR_CREATED",
    ];
  }
  return [
    "NORMALIZED",
    "IMPACT_SCANNING",
    "POLICY_EVALUATION",
    "PATCHING",
    "BUILDING",
    "TESTING",
    "VERIFYING",
    "PR_CREATED",
  ];
}

function pauseFor(change: ProjectChange, action: ChangeActionId): string | undefined {
  if (action === "prepare" || (action === "start" && isDocsOnly(change))) return undefined;
  if (!change.replacement) {
    return "No replacement is named. Continuing still stops at a pull request — it will not invent an identifier.";
  }
  if (change.migration === "semantic") {
    return "Seed / numberOfImages have no Gemini equivalent. Continue only if those options escalate, not drop.";
  }
  if (action === "review") {
    return `Named replacement is ${change.replacement}. Allow it and continue to an isolated patch?`;
  }
  return undefined;
}

function diffsFor(change: ProjectChange): DiffFile[] {
  const runtime = change.files.filter((file) => file.kind === "runtime").slice(0, 2);
  const fromId = change.identifiers[0];
  const toId = change.replacement;
  if (!fromId || !toId || runtime.length === 0) return [];

  return runtime.map((file, index) => {
    const lines: DiffLine[] =
      change.migration === "semantic" && index === 0
        ? [
            { kind: "ctx", text: "  models: [" },
            { kind: "del", text: `    { id: "${fromId}", surface: "imagen.generate" },` },
            { kind: "add", text: `    { id: "${toId}", surface: "generateContent" },` },
            { kind: "ctx", text: "  ]" },
          ]
        : [
            { kind: "ctx", text: "  id:" },
            { kind: "del", text: `    "${fromId}"` },
            { kind: "add", text: `    "${toId}"` },
          ];
    return {
      path: file.path,
      additions: lines.filter((line) => line.kind === "add").length,
      deletions: lines.filter((line) => line.kind === "del").length,
      lines,
    };
  });
}

function commandsFor(change: ProjectChange): SandboxCommand[] {
  const sample = change.files.find((file) => file.kind === "runtime")?.path ?? ".";
  const sha = change.baseSha?.slice(0, 12) ?? "unpinned";
  return [
    {
      phase: "patch",
      argv: `read_file ${sample}`,
      exit: 0,
      tail: `Workspace root only. Base ${sha}.`,
    },
    {
      phase: "patch",
      argv: "apply_patch",
      exit: 0,
      tail: "Forbidden paths untouched. CHANGELOG.md is not in the diff.",
    },
    {
      phase: "patch",
      argv: "pnpm --dir cli test -- generate.test.ts",
      exit: 0,
      tail: "Agent loop — diagnostic, not evidence.",
    },
    {
      phase: "build",
      argv: "pnpm --dir cli build",
      exit: 0,
      tail: "Orchestrator clean run from the diff. Not the agent’s own build.",
    },
    {
      phase: "test",
      argv: "pnpm --dir cli test",
      exit: 0,
      tail: "Orchestrator clean run. This is what verification sees.",
    },
  ];
}

function logsFor(change: ProjectChange, path: MachineState[]): AgentLogLine[] {
  const repo = change.repo ?? "imported repositories";
  const sha = change.baseSha?.slice(0, 12) ?? "unpinned";
  const runtime = change.files.filter((file) => file.kind === "runtime");
  const sample = runtime[0]?.path ?? change.files[0]?.path ?? ".";
  const fromId = change.identifiers[0] ?? "identifier";
  const lines: AgentLogLine[] = [];
  let n = 0;
  const add = (at: MachineState, kind: LogKind, text: string, verb?: string) => {
    if (!path.includes(at)) return;
    n += 1;
    lines.push({ id: `${at}-${n}`, at, kind, text, verb });
  };

  add("NORMALIZED", "thought", "Provider text is untrusted. Screen it before anything joins inventory.");
  add("NORMALIZED", "action", change.title, "Normalize");
  add("NORMALIZED", "result", "ChangeManifest accepted. Identifiers kept as claims.");

  add("IMPACT_SCANNING", "thought", `Join ${fromId} against ${repo} @ ${sha}, not HEAD.`);
  for (const file of runtime.slice(0, 3)) {
    add("IMPACT_SCANNING", "action", file.path, "Read");
  }
  if (runtime.length === 0 && change.files.length > 0) {
    add("IMPACT_SCANNING", "action", change.files[0].path, "Read");
  }
  add(
    "IMPACT_SCANNING",
    "result",
    runtime.length > 0
      ? `${change.fileHits ?? 0} hits · ${runtime.length} runtime paths.`
      : "No runtime path. Do not allocate a sandbox from docs or changelog.",
  );

  add("POLICY_EVALUATION", "narration", "Auto-merge stays false. Forbidden paths stay forbidden.");
  add("POLICY_EVALUATION", "action", "Deterministic policy on the impact report", "Evaluate");
  add(
    "POLICY_EVALUATION",
    "result",
    path.includes("HUMAN_REQUIRED")
      ? "HUMAN_REQUIRED — a sandbox is not opened until a human continues."
      : "ALLOW patch and PR. Merge remains off.",
  );

  add("PATCHING", "thought", "Inspect the installed SDK in the worktree before rewriting.");
  add("PATCHING", "action", `read_file ${sample}`, "Read");
  add("PATCHING", "action", "apply_patch", "Apply");
  add("PATCHING", "result", "Forbidden paths untouched. CHANGELOG.md is not in the diff.");
  add("PATCHING", "action", "pnpm --dir cli test -- generate.test.ts", "Run");
  add("PATCHING", "result", "Agent loop — diagnostic, not evidence.");

  add("BUILDING", "action", "pnpm --dir cli build", "Run");
  add("BUILDING", "result", "Orchestrator clean run from the diff. Not the agent’s own build.");

  add("TESTING", "action", "pnpm --dir cli test", "Run");
  add("TESTING", "result", "Orchestrator clean run. This is what verification sees.");

  add("VERIFYING", "thought", "Grade the diff and the clean logs. Do not read the patch author’s plan.");
  add("VERIFYING", "action", "Independent verification", "Verify");
  add("VERIFYING", "result", "Verifier ≠ patch author. Proposed tree may be opened.");

  add("PR_CREATED", "narration", "Pull request opened. PatchAPI stopped.");

  add("UNAFFECTED", "narration", "Report-only. No runtime path, so no worktree and no pull request.");
  add("HELD", "narration", "Draft held. No pull request until the note takes effect.");

  return lines;
}

function checksFor(change: ProjectChange): VerifyCheck[] {
  return [
    { name: "Identifiers mapped as the manifest specifies", passed: Boolean(change.replacement) },
    { name: "CHANGELOG.md and other history files untouched", passed: true },
    { name: "Forbidden paths untouched", passed: true },
    { name: "Clean build and tests from the diff alone", passed: true },
    { name: "Verifier did not see the patch author’s plan", passed: true },
  ];
}

export function createRun(change: ProjectChange, action: ChangeActionId, seq: number): MockRun {
  const path = pathFor(change, action);
  const machine = path[0] ?? "NORMALIZED";
  const log = logsFor(change, path);
  return {
    id: `run-${change.id.slice(0, 18)}-${Date.now().toString(36)}`,
    code: `RUN-${String(seq).padStart(3, "0")}`,
    changeId: change.id,
    title: change.title,
    repo: change.repo,
    baseSha: change.baseSha,
    fileHits: change.fileHits,
    fileCount: change.fileCount,
    identifiers: change.identifiers,
    replacement: change.replacement,
    files: change.files,
    action,
    machine,
    path,
    bucket: bucketOf(machine),
    createdAt: Date.now(),
    attempt: 1,
    attemptBudget: 3,
    pauseReason: pauseFor(change, action),
    commands: commandsFor(change),
    diffs: diffsFor(change),
    checks: checksFor(change),
    log,
    revealed: Math.min(1, log.length),
    lineStartedAt: Date.now(),
    prBranch: `patchapi/${change.id.replace(/[^a-z0-9]+/gi, "-").slice(0, 28)}`,
    traceId: `trc-${Math.random().toString(16).slice(2, 10)}`,
  };
}

export function advanceRun(run: MockRun): MockRun {
  if (run.bucket !== "active") return run;
  const nextLine = run.log[run.revealed];
  if (nextLine && nextLine.at === run.machine) {
    return { ...run, revealed: run.revealed + 1, lineStartedAt: Date.now() };
  }
  const index = run.path.indexOf(run.machine);
  const next = run.path[index + 1];
  if (!next) return { ...run, bucket: bucketOf(run.machine) };
  return { ...run, machine: next, bucket: bucketOf(next), lineStartedAt: Date.now() };
}

export function continueRun(run: MockRun): MockRun {
  const index = run.path.indexOf(run.machine);
  const next = run.path[index + 1];
  if (!next) return { ...run, bucket: bucketOf(run.machine) };
  return { ...run, machine: next, bucket: bucketOf(next), lineStartedAt: Date.now() };
}

export function visibleLog(run: MockRun): AgentLogLine[] {
  return run.log.slice(0, run.revealed);
}

export function inboxProgressFor(bucket: RunBucket): "idle" | "running" | "pr_opened" {
  if (bucket === "ready_for_review") return "pr_opened";
  if (bucket === "active" || bucket === "needs_attention" || bucket === "waiting") return "running";
  return "idle";
}

export function treeAvailable(machine: MachineState, tree: TreeId): boolean {
  if (tree === "base") return true;
  if (tree === "sandbox") {
    return (
      machine === "PATCHING" ||
      machine === "BUILDING" ||
      machine === "TESTING" ||
      machine === "VERIFYING" ||
      machine === "PR_CREATED"
    );
  }
  return machine === "VERIFYING" || machine === "PR_CREATED";
}

export function treeForMachine(machine: MachineState): TreeId {
  if (treeAvailable(machine, "proposed")) return "proposed";
  if (treeAvailable(machine, "sandbox")) return "sandbox";
  return "base";
}

export function visibleCommands(run: MockRun): SandboxCommand[] {
  if (!treeAvailable(run.machine, "sandbox")) return [];
  if (run.machine === "PATCHING") return run.commands.filter((item) => item.phase === "patch");
  if (run.machine === "BUILDING") {
    return run.commands.filter((item) => item.phase === "patch" || item.phase === "build");
  }
  return run.commands;
}

export function railIndex(machine: MachineState): number {
  const index = RAIL.findIndex((step) => step.at.includes(machine));
  return index === -1 ? 0 : index;
}

export const BUCKET_LABEL: Record<RunBucket, string> = {
  active: "Active",
  needs_attention: "Needs attention",
  waiting: "Waiting",
  ready_for_review: "Ready for review",
  idle: "Idle",
  blocked: "Blocked",
};
