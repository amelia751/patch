/**
 * Simulated run plans. These are UI fixtures — they do not claim a real
 * sandbox, test, or PR outcome.
 *
 * A run is not a chat. It is a pinned base SHA, an isolated worktree the
 * Patch agent may edit, and — only after independent verification — a
 * proposed branch. The publisher stops at the pull request.
 */

import type { ChangeActionId, RunProgress } from "./actions";
import {
  HARDCODED_PROJECT_CHANGES,
  isDocsOnly,
  runKey,
  type FileHit,
  type ProjectChange,
} from "./data";

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

/** Dual-CTA Need-you pause: connect GCP or add the verifier key. */
export const HUMAN_REQUIRED_PAUSE =
  "This run is waiting on you. Connect GCP or add GEMINI_API_KEY so the agent can continue.";

export const HUMAN_REQUIRED_SECRET_NAME = "GEMINI_API_KEY";

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

export function needFor(change: ProjectChange): "secret" | "gcp" | undefined {
  if (!change.replacement) return "secret";
  if (change.migration === "semantic") return "gcp";
  return "secret";
}

function pauseFor(change: ProjectChange, action: ChangeActionId): string | undefined {
  if (action === "prepare" || (action === "start" && isDocsOnly(change))) return undefined;
  if (needFor(change) === "gcp") {
    return "This project has no GCP connection. The agent will open a sandbox after you connect one.";
  }
  return "GEMINI_API_KEY is not on this project. The verifier will call the replacement and will not invent a key.";
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

function terminalFence(dir: string, commands: { cmd: string; out: string }[]): string {
  const lines = ["```terminal", `# ${dir}`];
  for (const item of commands) {
    lines.push(`$ ${item.cmd}`);
    if (item.out) {
      for (const line of item.out.replace(/\r\n/g, "\n").split("\n")) {
        lines.push(line);
      }
    }
  }
  lines.push("```");
  return lines.join("\n");
}

function unwrapCommand(text: string): string {
  return text
    .trim()
    .replace(/^Bash\(/, "")
    .replace(/\)$/, "")
    .replace(/^`|`$/g, "")
    .replace(/^read_file\s+/, "")
    .trim();
}

/** Cursor-style captured stdout. Policy copy never belongs here. */
export function cursorStdout(command: string, file = "cli/src/cli/model-catalog.ts"): string {
  const cmd = unwrapCommand(command);
  if (cmd === "apply_patch" || cmd.startsWith("apply_patch ")) {
    const target = cmd.slice("apply_patch".length).trim() || file;
    return [
      `Checking patch ${target}...`,
      `Hunk #1 succeeded at 48 (offset 2 lines).`,
      `Applied patch ${target} cleanly.`,
      "",
      "exited 0",
    ].join("\n");
  }
  if (cmd.includes("generate.test.ts")) {
    return [
      "> cli@0.4.2 test /tmp/patchapi-sandbox/cli",
      "> vitest run generate.test.ts",
      "",
      " RUN  v3.0.5 /tmp/patchapi-sandbox/cli",
      "",
      " ✓ src/cli/generate.test.ts (3 tests) 84ms",
      "   ✓ maps identifiers as the manifest specifies",
      "   ✓ drops seed and numberOfImages on gemini-native",
      "   ✓ keeps docs-only hits out of the patch",
      "",
      " Test Files  1 passed (1)",
      "      Tests  3 passed (3)",
      "   Start at  14:26:12",
      "   Duration  412ms (transform 38ms, setup 0ms, collect 61ms, tests 84ms)",
      "",
      "exited 0",
    ].join("\n");
  }
  if (/pnpm --dir cli build\b/.test(cmd) || /\btsc\b/.test(cmd)) {
    return [
      "> cli@0.4.2 build /tmp/patchapi-sandbox/cli",
      "> tsc -p tsconfig.json",
      "",
      "exited 0",
    ].join("\n");
  }
  if (/pnpm --dir cli test\b/.test(cmd)) {
    return [
      "> cli@0.4.2 test /tmp/patchapi-sandbox/cli",
      "> vitest run",
      "",
      " RUN  v3.0.5 /tmp/patchapi-sandbox/cli",
      "",
      " ✓ src/cli/generate.test.ts (3 tests) 84ms",
      " ✓ src/cli/model-catalog.test.ts (5 tests) 31ms",
      " ✓ src/cli/cli.test.ts (4 tests) 19ms",
      "",
      " Test Files  3 passed (3)",
      "      Tests  12 passed (12)",
      "   Start at  14:27:01",
      "   Duration  1.21s (transform 112ms, setup 0ms, collect 204ms, tests 134ms)",
      "",
      "exited 0",
    ].join("\n");
  }
  return "";
}

function logsFor(change: ProjectChange, path: MachineState[]): AgentLogLine[] {
  const repo = change.repo ?? "imported repositories";
  const sha = change.baseSha?.slice(0, 12) ?? "unpinned";
  const runtime = change.files.filter((file) => file.kind === "runtime");
  const sample = runtime[0]?.path ?? change.files[0]?.path ?? ".";
  const fromId = change.identifiers[0] ?? "identifier";
  const lines: AgentLogLine[] = [];
  let n = 0;
  let lastUseId = "";
  const add = (
    at: MachineState,
    kind: LogKind,
    text: string,
    extras?: Pick<AgentLogLine, "verb" | "toolType" | "toolUseId" | "filePath">,
  ) => {
    if (!path.includes(at)) return;
    n += 1;
    const id = `${at}-${n}`;
    if (kind === "action") lastUseId = extras?.toolUseId ?? id;
    lines.push({
      id,
      at,
      kind,
      text,
      verb: extras?.verb,
      toolType: extras?.toolType,
      toolUseId: extras?.toolUseId ?? (kind === "result" ? lastUseId : kind === "action" ? id : undefined),
      filePath: extras?.filePath,
    });
  };

  add("NORMALIZED", "thought", "Provider text is untrusted. Screen it before anything joins inventory.");
  add("NORMALIZED", "action", "Normalize(`ChangeManifest`)", { verb: "Normalize", toolType: "Normalize" });
  add("NORMALIZED", "result", "Identifiers kept as claims.");

  add("IMPACT_SCANNING", "thought", `Join \`${fromId}\` against ${repo} @ ${sha}, not HEAD.`);
  for (const file of runtime.slice(0, 3)) {
    add("IMPACT_SCANNING", "action", `Read(\`${file.path}\`)`, {
      verb: "Read",
      toolType: "Read",
      filePath: file.path,
    });
  }
  if (runtime.length === 0 && change.files.length > 0) {
    add("IMPACT_SCANNING", "action", `Read(\`${change.files[0].path}\`)`, {
      verb: "Read",
      toolType: "Read",
      filePath: change.files[0].path,
    });
  }
  add(
    "IMPACT_SCANNING",
    "result",
    runtime.length > 0
      ? `${change.fileHits ?? 0} hits · ${runtime.length} runtime paths.`
      : "No runtime path. Do not allocate a sandbox from docs or changelog.",
  );

  add("POLICY_EVALUATION", "narration", "Auto-merge stays false. Forbidden paths stay forbidden.");
  add("POLICY_EVALUATION", "action", "Evaluate(`impact report`)", { verb: "Evaluate", toolType: "Evaluate" });
  add(
    "POLICY_EVALUATION",
    "result",
    path.includes("HUMAN_REQUIRED")
      ? needFor(change) === "gcp"
        ? "HUMAN_REQUIRED — GCP is not connected. The agent allocates the sandbox after you connect."
        : "HUMAN_REQUIRED — GEMINI_API_KEY is missing. The agent allocates the sandbox after you add it."
      : "ALLOW patch and PR. Merge remains off.",
  );

  add("PATCHING", "thought", "Inspect the installed SDK in the worktree before rewriting.");
  add("PATCHING", "action", `Read(\`${sample}\`)`, { verb: "Read", toolType: "Read", filePath: sample });
  add("PATCHING", "action", `Edit(\`${sample}\`)`, { verb: "Apply", toolType: "Edit", filePath: sample });
  add(
    "PATCHING",
    "block",
    terminalFence("/tmp/patchapi-sandbox", [
      { cmd: "apply_patch", out: cursorStdout("apply_patch", sample) },
    ]),
  );
  add(
    "PATCHING",
    "block",
    terminalFence("/tmp/patchapi-sandbox", [
      {
        cmd: "pnpm --dir cli test -- generate.test.ts",
        out: cursorStdout("pnpm --dir cli test -- generate.test.ts"),
      },
    ]),
  );

  add(
    "BUILDING",
    "block",
    terminalFence("/tmp/patchapi-sandbox", [
      { cmd: "pnpm --dir cli build", out: cursorStdout("pnpm --dir cli build") },
    ]),
  );

  add(
    "TESTING",
    "block",
    terminalFence("/tmp/patchapi-sandbox", [
      { cmd: "pnpm --dir cli test", out: cursorStdout("pnpm --dir cli test") },
    ]),
  );

  add("VERIFYING", "thought", "Grade the diff and the clean logs. Do not read the patch author’s plan.");
  add("VERIFYING", "action", "Verify(`proposed tree`)", { verb: "Verify", toolType: "Verify" });
  add("VERIFYING", "result", "Verifier ≠ patch author. Proposed tree may be opened.");

  add("PR_CREATED", "narration", "Pull request opened. PatchAPI stopped.");

  add("UNAFFECTED", "narration", "Report-only. No runtime path, so no worktree and no pull request.");
  add("HELD", "narration", "Draft held. No pull request until the note takes effect.");
  add("FAILED", "narration", "Verification disagreed. Fail closed. No pull request.");
  add("BLOCKED", "narration", "Policy blocked this path. No sandbox and no pull request.");

  return lines;
}

function branchName(changeId: string): string {
  const slug = changeId.replace(/[^a-z0-9]+/gi, "-").replace(/-+$/g, "");
  const withoutDay = slug.replace(/-\d{4}-\d{2}-\d{2}$/, "");
  return `patchapi/${withoutDay}`;
}

function checksFor(change: ProjectChange, failed = false): VerifyCheck[] {
  return [
    { name: "Identifiers mapped as the manifest specifies", passed: Boolean(change.replacement) && !failed },
    { name: "CHANGELOG.md and other history files untouched", passed: !failed },
    { name: "Forbidden paths untouched", passed: true },
    { name: "Clean build and tests from the diff alone", passed: !failed },
    { name: "Verifier did not see the patch author’s plan", passed: true },
  ];
}

function pathThrough(change: ProjectChange, action: ChangeActionId, at?: MachineState): MachineState[] {
  const path = pathFor(change, action);
  if (!at || path.includes(at)) return path;
  if (at === "FAILED") {
    return path.filter((state) => state !== "PR_CREATED" && state !== "HELD" && state !== "UNAFFECTED").concat("FAILED");
  }
  if (at === "BLOCKED") {
    return ["NORMALIZED", "IMPACT_SCANNING", "POLICY_EVALUATION", "BLOCKED"];
  }
  return path;
}

function revealedThrough(log: AgentLogLine[], path: MachineState[], machine: MachineState): number {
  const stop = path.indexOf(machine);
  if (stop === -1) return log.length;
  let revealed = 0;
  for (let i = 0; i < log.length; i += 1) {
    const at = path.indexOf(log[i].at);
    if (at !== -1 && at <= stop) revealed = i + 1;
  }
  return Math.max(revealed, 1);
}

export interface CreateRunOpts {
  at?: MachineState;
  createdAt?: number;
  attempt?: number;
  id?: string;
  pauseReason?: string;
  need?: "secret" | "gcp";
}

export function createRun(
  change: ProjectChange,
  action: ChangeActionId,
  seq: number,
  opts?: CreateRunOpts,
): MockRun {
  const path = pathThrough(change, action, opts?.at);
  const machine = opts?.at ?? path[0] ?? "NORMALIZED";
  const log = logsFor(change, path);
  const createdAt = opts?.createdAt ?? Date.now();
  const settled = Boolean(opts?.at);
  return {
    id: opts?.id ?? `run-${change.id.slice(0, 18)}-${Date.now().toString(36)}`,
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
    createdAt,
    attempt: opts?.attempt ?? 1,
    attemptBudget: 3,
    pauseReason: opts?.pauseReason ?? pauseFor(change, action),
    need: opts?.need ?? (path.includes("HUMAN_REQUIRED") ? needFor(change) : undefined),
    commands: commandsFor(change),
    diffs: diffsFor(change),
    checks: checksFor(change, machine === "FAILED"),
    log,
    revealed: settled ? revealedThrough(log, path, machine) : Math.min(1, log.length),
    lineStartedAt: createdAt,
    prBranch: branchName(change.id),
    traceId: `trc-${change.id.slice(0, 8)}`,
  };
}

function changeById(id: string): ProjectChange | undefined {
  return HARDCODED_PROJECT_CHANGES.find((change) => change.id === id);
}

/**
 * Prior runs already on the workspace. These are UI fixtures — they do not
 * claim a real sandbox, test, or pull-request outcome.
 */
export function seedRuns(): MockRun[] {
  const ago = (ms: number) => Date.now() - ms;
  const runs: MockRun[] = [];
  let seq = 0;
  const add = (
    id: string,
    action: ChangeActionId,
    at: MachineState,
    createdAt: number,
    extra?: Pick<CreateRunOpts, "attempt" | "pauseReason" | "need"> & { repo?: string },
  ) => {
    const change = changeById(id);
    if (!change) return;
    seq += 1;
    runs.push(
      createRun(
        extra?.repo ? { ...change, repo: extra.repo } : change,
        action,
        seq,
        {
          at,
          createdAt,
          attempt: extra?.attempt,
          pauseReason: extra?.pauseReason,
          need: extra?.need,
          id: `run-seed-${id}-${extra?.repo ?? change.repo ?? "unscoped"}`,
        },
      ),
    );
  };

  add("chg_flash_image_preview", "start", "PR_CREATED", ago(4 * 60 * 1000));
  add("imagen4-retirement-2026-08-17", "start", "HUMAN_REQUIRED", ago(2 * 60 * 60 * 1000), {
    pauseReason: HUMAN_REQUIRED_PAUSE,
  });
  add("ui-issue-long-title", "start", "HUMAN_REQUIRED", ago(50 * 60 * 1000), {
    repo: "amelia751/egaki",
    pauseReason: HUMAN_REQUIRED_PAUSE,
  });
  add("ui-changelog-immutable", "start", "UNAFFECTED", ago(6 * 60 * 60 * 1000));
  add("ui-scheduled-window", "prepare", "HELD", ago(18 * 60 * 60 * 1000));
  add("ui-vertex-prefix-leftover", "start", "FAILED", ago(26 * 60 * 60 * 1000), {
    attempt: 2,
    pauseReason: "No replacement is named. The verifier refused to invent one.",
  });
  add("adv-fal-ai-not-covered", "start", "BLOCKED", ago(3 * 24 * 60 * 60 * 1000), {
    pauseReason: "fal-ai/imagen4/preview is not this retirement. Editing it is an unnecessary change.",
  });

  return runs.sort((a, b) => b.createdAt - a.createdAt);
}

export function findRunFor(runs: MockRun[], change: ProjectChange): MockRun | undefined {
  const key = runKey(change);
  return runs.find((run) => runKey({ id: run.changeId, repo: run.repo }) === key);
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

export function inboxProgressFor(bucket: RunBucket): RunProgress {
  if (bucket === "ready_for_review") return "pr_opened";
  if (bucket === "active" || bucket === "needs_attention" || bucket === "waiting") return "running";
  if (bucket === "idle" || bucket === "blocked") return "pr_opened";
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
      machine === "FAILED" ||
      machine === "PR_CREATED"
    );
  }
  return machine === "VERIFYING" || machine === "PR_CREATED" || machine === "FAILED";
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

export const BUCKET_LABEL: Record<RunBucket, string> = {
  active: "Active",
  needs_attention: "Needs attention",
  waiting: "Waiting",
  ready_for_review: "Ready for review",
  idle: "Idle",
  blocked: "Blocked",
};
