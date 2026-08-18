/**
 * Simulated run plans. These are UI fixtures — they do not claim a real
 * sandbox, test, or PR outcome. Each action type has a different ending.
 */

import type { ChangeActionId } from "./actions";
import type { ProjectChange } from "./data";

export type RunBucket =
  | "active"
  | "needs_attention"
  | "waiting"
  | "ready_for_review"
  | "idle"
  | "blocked";

export type TodoState = "pending" | "in_progress" | "completed" | "cancelled" | "deferred";

export interface RunTodo {
  id: string;
  label: string;
  detail: string;
  agent: string;
  state: TodoState;
  pause?: boolean;
  pausePrompt?: string;
}

export interface MockRun {
  id: string;
  code: string;
  changeId: string;
  title: string;
  prompt: string;
  repo?: string;
  baseSha?: string;
  fileHits?: number;
  fileCount?: number;
  action: ChangeActionId;
  bucket: RunBucket;
  createdAt: number;
  todos: RunTodo[];
  outcome?: string;
  prLabel?: string;
  traceId: string;
}

function todo(
  id: string,
  label: string,
  detail: string,
  agent: string,
  extra?: Pick<RunTodo, "pause" | "pausePrompt">,
): RunTodo {
  return { id, label, detail, agent, state: "pending", ...extra };
}

export function scriptFor(change: ProjectChange, action: ChangeActionId): RunTodo[] {
  const repo = change.repo ?? "imported repositories";
  const replacement = change.replacement ?? "unresolved";

  if (action === "prepare") {
    return [
      todo("n", "Normalize the note", "Untrusted provider text → ChangeManifest. No inventory write.", "Change Intelligence"),
      todo("m", "Match inventory", `Join known identifiers against ${repo}. Early — note is not in effect.`, "Impact"),
      todo("i", "Draft impact", "Record what would break if the note lands. Do not allocate a sandbox.", "Impact"),
      todo("p", "Hold the draft", "No pull request until the effective day. Watching continues.", "Policy"),
    ];
  }

  if (action === "start" && change.status === "docs_only") {
    return [
      todo("n", "Normalize the note", "Same ChangeManifest path as a runtime finding.", "Change Intelligence"),
      todo("m", "Classify inventory", "Hits are documentation and changelog only. No executable path.", "Impact"),
      todo("s", "Stop without a PR", "Report-only. Opening a patch would rewrite history or docs by accident.", "Policy"),
    ];
  }

  if (action === "review" || change.status === "human_required") {
    return [
      todo("n", "Normalize the note", `${change.title} → ChangeManifest. Identifiers kept as claims.`, "Change Intelligence"),
      todo("m", "Match inventory", `Find ${change.identifiers[0] ?? "identifiers"} in ${repo}.`, "Impact"),
      todo(
        "i",
        "Impact analysis",
        change.migration === "semantic"
          ? "Request surfaces differ. A string rewrite is incorrect."
          : "Replacement must be resolved against the installed SDK.",
        "Impact",
      ),
      todo("g", "Policy pause", `Named replacement is ${replacement}. Auto-patch is off.`, "Policy", {
        pause: true,
        pausePrompt: "Allow this replacement and continue to an isolated patch?",
      }),
      todo("s", "Allocate sandbox", "Isolated workspace at the pinned base SHA. Not the primary checkout.", "Patch"),
      todo("x", "Generate patch", "Write only what policy allowed. Forbidden paths stay untouched.", "Patch"),
      todo("b", "Build and tests", "Simulated checks in the sandbox. Failure would fail closed.", "Verification"),
      todo("v", "Independent verification", "A separate judge. The patch author does not grade itself.", "Verification"),
      todo("pr", "Open pull request", "Stop. PatchAPI does not merge.", "PR"),
    ];
  }

  if (change.migration === "semantic") {
    return [
      todo("n", "Normalize the note", "Imagen 4 retirement hashed and screened as untrusted input.", "Change Intelligence"),
      todo("m", "Match inventory", `${change.fileHits} refs across ${change.fileCount} files in ${repo}.`, "Impact"),
      todo("i", "Impact analysis", "Semantic migration: Imagen image surface ≠ Gemini native image generation.", "Impact"),
      todo("g", "Policy", "Risk MEDIUM. Auto-patch allowed only after option mapping is explicit.", "Policy", {
        pause: true,
        pausePrompt: "Continue? Seed / numberOfImages have no Gemini equivalent and will escalate, not drop.",
      }),
      todo("s", "Allocate sandbox", `Workspace from ${change.baseSha?.slice(0, 12) ?? "pinned SHA"}.`, "Patch"),
      todo("x", "Generate patch", "Rewrite catalog strategy, not only model ids. CHANGELOG.md is immutable.", "Patch"),
      todo("b", "Build and tests", "Simulated typescript build + vitest in isolation.", "Verification"),
      todo("v", "Independent verification", "Verification Agent vetoes a string-only rewrite.", "Verification"),
      todo("pr", "Open pull request", "Evidence-backed PR. Humans merge.", "PR"),
    ];
  }

  return [
    todo("n", "Normalize the note", `${change.title} → ChangeManifest.`, "Change Intelligence"),
    todo("m", "Match inventory", `${change.fileHits || 0} refs in ${repo}.`, "Impact"),
    todo("i", "Impact analysis", "Mechanical identifier rewrite on the same request surface.", "Impact"),
    todo("g", "Policy ALLOW", "Auto-patch and auto-PR on. Auto-merge stays false.", "Policy"),
    todo("s", "Allocate sandbox", "Isolated workspace. Generated code never runs on the console.", "Patch"),
    todo("x", "Generate patch", `Replace identifiers with ${replacement}.`, "Patch"),
    todo("b", "Build and tests", "Simulated sandbox checks.", "Verification"),
    todo("v", "Independent verification", "Second model grades the first.", "Verification"),
    todo("pr", "Open pull request", "Stop at the PR.", "PR"),
  ];
}

function promptFor(change: ProjectChange, action: ChangeActionId): string {
  const repo = change.repo ?? "this project's imported repositories";
  if (action === "prepare") {
    return `Prepare ${change.title} early against ${repo}. Draft impact only. Do not open a pull request until the note takes effect.`;
  }
  if (action === "start" && change.status === "docs_only") {
    return `Check ${change.title} anyway. Hits look documentation-only — confirm and stop if there is no runtime path.`;
  }
  if (action === "review") {
    return `Continue ${change.title} on ${repo}. Do not auto-patch. Confirm the replacement, then open a pull request. Do not merge.`;
  }
  return `Start a remediation for ${change.title} against ${repo}. Analyze, patch in isolation, verify, and open a pull request. Do not merge.`;
}

export function createRun(change: ProjectChange, action: ChangeActionId, seq: number): MockRun {
  const todos = scriptFor(change, action);
  if (todos[0]) todos[0].state = "in_progress";
  return {
    id: `run-${change.id.slice(0, 18)}-${Date.now().toString(36)}`,
    code: `RUN-${String(seq).padStart(3, "0")}`,
    changeId: change.id,
    title: change.title,
    prompt: promptFor(change, action),
    repo: change.repo,
    baseSha: change.baseSha,
    fileHits: change.fileHits,
    fileCount: change.fileCount,
    action,
    bucket: "active",
    createdAt: Date.now(),
    todos,
    traceId: `trc-${Math.random().toString(16).slice(2, 10)}`,
  };
}

export function advanceRun(run: MockRun): MockRun {
  if (run.bucket !== "active") return run;
  const todos = run.todos.map((t) => ({ ...t }));
  const current = todos.find((t) => t.state === "in_progress");
  if (!current) return finishIfDone({ ...run, todos });

  current.state = "completed";
  const next = todos.find((t) => t.state === "pending");
  if (!next) return finishIfDone({ ...run, todos });

  next.state = "in_progress";
  if (next.pause) {
    return { ...run, todos, bucket: "needs_attention" };
  }
  return { ...run, todos };
}

export function continueRun(run: MockRun): MockRun {
  const todos = run.todos.map((t) => ({ ...t }));
  const paused = todos.find((t) => t.state === "in_progress" && t.pause);
  if (paused) paused.state = "completed";
  const next = todos.find((t) => t.state === "pending");
  if (!next) return finishIfDone({ ...run, todos });
  next.state = "in_progress";
  return { ...run, todos, bucket: next.pause ? "needs_attention" : "active" };
}

function finishIfDone(run: MockRun): MockRun {
  const remaining = run.todos.some((t) => t.state === "pending" || t.state === "in_progress");
  if (remaining) return run;

  const last = run.todos[run.todos.length - 1];
  if (last?.id === "pr") {
    return {
      ...run,
      bucket: "ready_for_review",
      outcome: "Pull request opened. PatchAPI stopped.",
      prLabel: `${run.repo ?? "repo"}#—`,
    };
  }
  if (run.action === "prepare") {
    return {
      ...run,
      bucket: "idle",
      outcome: "Draft held. No pull request until the note takes effect.",
    };
  }
  return {
    ...run,
    bucket: "idle",
    outcome: "Report-only. No runtime path, so no pull request.",
  };
}

export function inboxProgressFor(bucket: RunBucket): "idle" | "running" | "pr_opened" {
  if (bucket === "ready_for_review") return "pr_opened";
  if (bucket === "active" || bucket === "needs_attention" || bucket === "waiting") return "running";
  return "idle";
}

export const BUCKET_LABEL: Record<RunBucket, string> = {
  active: "Active",
  needs_attention: "Needs attention",
  waiting: "Waiting",
  ready_for_review: "Ready for review",
  idle: "Idle",
  blocked: "Blocked",
};

export const BUCKET_TONE: Record<RunBucket, string> = {
  active: "text-sky-400 bg-sky-400/10 border-sky-400/30",
  needs_attention: "text-amber-500 bg-amber-500/10 border-amber-500/30",
  waiting: "text-[var(--text-secondary)] bg-[var(--bg-tertiary)] border-[var(--border-color)]",
  ready_for_review: "text-emerald-500 bg-emerald-500/10 border-emerald-500/30",
  idle: "text-[var(--text-secondary)] bg-[var(--bg-tertiary)] border-[var(--border-color)]",
  blocked: "text-red-500 bg-red-500/10 border-red-500/30",
};
