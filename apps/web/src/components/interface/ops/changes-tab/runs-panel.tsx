"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ActivitySpinner, WorklogView } from "@/components/console/worklog-view";
import { collapseWorklogEntries, pairActionResults } from "@/components/console/thread-worklog";
import type { WorklogEntry } from "@/components/console/thread-types";
import {
  ArrowRight,
  Check,
  ExternalLink,
  GitBranch,
  GitPullRequest,
  Lock,
  Radio,
  X,
} from "lucide-react";
import { UNSCOPED_REPO, repoOf, repoTitle } from "./data";
import {
  MACHINE_LABEL,
  RAIL,
  railIndex,
  treeAvailable,
  treeForMachine,
  visibleLog,
  cursorStdout,
  type AgentLogLine,
  type DiffFile,
  type DiffLine,
  type MachineState,
  type MockRun,
  type RunBucket,
  type TreeId,
} from "./run-scripts";

function timeAgo(ts: number): string {
  const seconds = Math.max(1, Math.round((Date.now() - ts) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

function statusDot(bucket: RunBucket): string {
  if (bucket === "active") return "bg-sky-400 animate-pulse";
  if (bucket === "needs_attention") return "bg-amber-500";
  if (bucket === "ready_for_review") return "bg-emerald-500";
  if (bucket === "blocked") return "bg-red-500";
  return "bg-[var(--text-secondary)]";
}

function shortSha(sha?: string): string {
  return sha ? sha.slice(0, 7) : "unpinned";
}

function groupRuns(runs: MockRun[]): [string, MockRun[]][] {
  const groups = new Map<string, MockRun[]>();
  for (const run of runs) {
    const key = repoOf(run);
    const list = groups.get(key) ?? [];
    list.push(run);
    groups.set(key, list);
  }
  return [...groups.entries()].sort(([a], [b]) => {
    if (a === UNSCOPED_REPO) return 1;
    if (b === UNSCOPED_REPO) return -1;
    return a.localeCompare(b);
  });
}

const TREE_COPY: Record<TreeId, { label: string; hint: string }> = {
  base: {
    label: "Base",
    hint: "Imported repository at the pinned SHA. Inventory is joined here. PatchAPI does not write this tree.",
  },
  sandbox: {
    label: "Sandbox",
    hint: "Isolated worktree cloned from the same SHA. The Patch agent may edit here. This is not your checkout, and it is not evidence.",
  },
  proposed: {
    label: "Proposed",
    hint: "Verified diff replayed onto a clean tree. This is the branch the publisher opens. PatchAPI does not merge.",
  },
};

export function RunsPanel({
  runs,
  selectedId,
  onSelect,
  onContinue,
}: {
  runs: MockRun[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onContinue: (id: string) => void;
}) {
  const selected = runs.find((run) => run.id === selectedId) ?? runs[0] ?? null;

  if (runs.length === 0) {
    return (
      <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
        <div className="text-center max-w-sm px-4">
          <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
            <Radio className="h-5 w-5 text-[var(--text-secondary)]" />
          </div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">No runs yet</h2>
          <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">
            Start a remediation from Releases
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex min-w-0 bg-[var(--bg-primary)]">
      <div className="w-[260px] flex-shrink-0 border-r border-[var(--border-color)] overflow-y-auto">
        <div className="px-4 pt-4 pb-2">
          <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
            {runs.length} {runs.length === 1 ? "run" : "runs"}
          </p>
        </div>
        <div className="px-2 pb-3 space-y-3">
          {groupRuns(runs).map(([repo, items]) => (
            <div key={repo}>
              <p className="px-2.5 pt-1 pb-1.5 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
                <GitBranch className="h-3 w-3 shrink-0" />
                <span className="font-mono normal-case tracking-normal truncate">{repoTitle(repo)}</span>
              </p>
              <div className="space-y-0.5">
                {items.map((run) => {
                  const active = selected?.id === run.id;
                  return (
                    <button
                      key={run.id}
                      type="button"
                      onClick={() => onSelect(run.id)}
                      className={cn(
                        "w-full text-left rounded-lg px-2.5 py-2.5 transition-colors",
                        active ? "bg-[var(--bg-tertiary)]" : "hover:bg-[var(--bg-secondary)]",
                      )}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", statusDot(run.bucket))} />
                        <span className="text-[10px] font-medium uppercase tracking-wide text-[var(--text-secondary)] truncate">
                          {MACHINE_LABEL[run.machine]}
                        </span>
                      </div>
                      <p className="text-[13px] text-[var(--text-primary)] leading-snug line-clamp-2">
                        {run.title}
                      </p>
                      <p className="text-[11px] font-mono text-[var(--text-secondary)] mt-1 truncate">
                        {shortSha(run.baseSha)}
                        <span className="mx-1.5 font-sans text-[var(--border-color)]">·</span>
                        <span className="font-sans">{timeAgo(run.createdAt)}</span>
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {selected && <RunDetail run={selected} onContinue={() => onContinue(selected.id)} />}
    </div>
  );
}

function RunDetail({ run, onContinue }: { run: MockRun; onContinue: () => void }) {
  const current = treeForMachine(run.machine);
  const [picked, setPicked] = useState<TreeId | null>(null);

  useEffect(() => {
    setPicked(null);
  }, [run.id, run.machine]);

  const tree = picked ?? current;
  const repo = run.repo ?? "imported repositories";

  return (
    <div className="flex-1 min-w-0 flex flex-col">
      <div className="px-5 pt-4 pb-3 border-b border-[var(--border-color)]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] text-[var(--text-secondary)] font-mono">{run.code}</p>
            <h2 className="text-[15px] font-semibold text-[var(--text-primary)] mt-1 tracking-tight">
              {run.title}
            </h2>
            <p className="text-[12px] font-mono text-[var(--text-secondary)] mt-1.5 truncate">
              {repo}
              <span className="mx-1">@</span>
              {shortSha(run.baseSha)}
              <span className="mx-1.5 font-sans">·</span>
              <span className="font-sans">
                attempt {run.attempt} of {run.attemptBudget}
              </span>
              <span className="mx-1.5 font-sans">·</span>
              <span className="font-sans">simulated</span>
            </p>
          </div>
        </div>
        <StateRail machine={run.machine} />
      </div>

      {run.machine === "HUMAN_REQUIRED" && (
        <div className="px-5 py-3 border-b border-amber-500/30 bg-amber-500/5 flex items-start justify-between gap-3">
          <p className="text-[12px] text-[var(--text-primary)] leading-relaxed">
            {run.pauseReason ?? "A human has to confirm before a sandbox is allocated."}
          </p>
          <Button
            size="sm"
            className="h-7 shrink-0 text-xs bg-primary text-primary-foreground hover:bg-primary/90"
            onClick={onContinue}
          >
            Allocate sandbox
          </Button>
        </div>
      )}
      {(run.machine === "FAILED" || run.machine === "BLOCKED") && (
        <div className="px-5 py-3 border-b border-red-500/30 bg-red-500/5">
          <p className="text-[12px] text-[var(--text-primary)] leading-relaxed">
            {run.pauseReason ??
              (run.machine === "FAILED"
                ? "Verification disagreed. Fail closed. No pull request."
                : "Policy blocked this path. No sandbox and no pull request.")}
          </p>
        </div>
      )}
      {run.machine === "UNAFFECTED" && (
        <div className="px-5 py-3 border-b border-[var(--border-color)] bg-[var(--bg-secondary)]">
          <p className="text-[12px] text-[var(--text-primary)] leading-relaxed">
            Report-only. No runtime path, so no worktree and no pull request.
          </p>
        </div>
      )}
      {run.machine === "HELD" && (
        <div className="px-5 py-3 border-b border-[var(--border-color)] bg-[var(--bg-secondary)]">
          <p className="text-[12px] text-[var(--text-primary)] leading-relaxed">
            Draft held. No pull request until the note takes effect.
          </p>
        </div>
      )}

      <div className="flex items-stretch w-full border-b border-[var(--border-color)]">
        {(["base", "sandbox", "proposed"] as TreeId[]).map((id) => {
          const open = treeAvailable(run.machine, id);
          const selected = tree === id;
          return (
            <button
              key={id}
              type="button"
              disabled={!open}
              onClick={() => setPicked(id)}
              className={cn(
                "flex-1 min-w-0 px-4 pt-2.5 pb-2 text-left border-b-2 -mb-px transition-colors",
                selected
                  ? "border-[var(--text-primary)] text-[var(--text-primary)]"
                  : "border-transparent text-[var(--text-secondary)]",
                open ? "hover:text-[var(--text-primary)]" : "opacity-40 cursor-not-allowed",
              )}
            >
              <p className="text-[11px] font-medium">{TREE_COPY[id].label}</p>
              <div className="mt-1">
                {id === "base" && (
                  <BranchChip name="main" sha={shortSha(run.baseSha)} muted={!selected} />
                )}
                {id === "sandbox" &&
                  (open ? (
                    <p className="text-[10px] font-mono text-[var(--text-secondary)] truncate">
                      worktree · {shortSha(run.baseSha)}
                    </p>
                  ) : (
                    <p className="text-[10px] text-[var(--text-secondary)]">not allocated</p>
                  ))}
                {id === "proposed" &&
                  (open && run.prBranch && run.machine !== "FAILED" ? (
                    <BranchChip name={run.prBranch} active={selected} />
                  ) : (
                    <p className="text-[10px] text-[var(--text-secondary)]">
                      {run.machine === "FAILED" ? "not opened" : "not verified"}
                    </p>
                  ))}
              </div>
            </button>
          );
        })}
      </div>

      <p className="px-5 pt-3 text-[11px] text-[var(--text-secondary)] leading-relaxed">
        {TREE_COPY[tree].hint}
      </p>

      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-3 space-y-4">
        {tree === "base" && <BaseTree run={run} />}
        {tree === "sandbox" && <SandboxTree run={run} />}
        {tree === "proposed" && <ProposedTree run={run} />}
        <AgentLog run={run} />
      </div>
    </div>
  );
}

function StateRail({ machine }: { machine: MachineState }) {
  const current = railIndex(machine);
  const stoppedEarly = machine === "UNAFFECTED" || machine === "HELD";
  const halted = machine === "FAILED" || machine === "BLOCKED";

  return (
    <ol className="mt-3 flex items-center gap-0 min-w-0">
      {RAIL.map((step, index) => {
        const done = index < current || (stoppedEarly && step.at.includes(machine));
        const here = step.at.includes(machine);
        const future = index > current && !here;
        return (
          <li key={step.label} className="flex items-center min-w-0 flex-1 last:flex-none">
            <div className="flex items-center gap-1.5 min-w-0">
              <span
                className={cn(
                  "flex h-3.5 w-3.5 items-center justify-center rounded-full border shrink-0",
                  here && machine === "HUMAN_REQUIRED" && "border-amber-500/50 bg-amber-500/15",
                  here && halted && "border-red-500/50 bg-red-500/15",
                  here && machine !== "HUMAN_REQUIRED" && !halted && "border-sky-400/50 bg-sky-400/15",
                  done && !here && "border-emerald-500/40 bg-emerald-500/10",
                  future && "border-[var(--border-color)]",
                )}
              >
                {done && !here ? (
                  <Check className="h-2 w-2 text-emerald-500" />
                ) : (
                  <span
                    className={cn(
                      "h-1 w-1 rounded-full",
                      here && machine === "HUMAN_REQUIRED" && "bg-amber-500",
                      here && halted && "bg-red-500",
                      here && machine !== "HUMAN_REQUIRED" && !halted && "bg-sky-400",
                      future && "bg-[var(--border-color)]",
                    )}
                  />
                )}
              </span>
              <span
                className={cn(
                  "text-[10px] uppercase tracking-wide truncate",
                  here ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]",
                )}
              >
                {step.label}
              </span>
            </div>
            {index < RAIL.length - 1 && (
              <span
                className={cn(
                  "mx-2 h-px flex-1 min-w-[8px]",
                  index < current ? "bg-emerald-500/40" : "bg-[var(--border-color)]",
                )}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

function BaseTree({ run }: { run: MockRun }) {
  const runtime = run.files.filter((file) => file.kind === "runtime");
  const other = run.files.filter((file) => file.kind !== "runtime");

  if (run.files.length === 0 && run.identifiers.length === 0) {
    return (
      <p className="text-[12px] text-[var(--text-secondary)]">
        No usages at this SHA. A sandbox will not be allocated from an empty join.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {run.identifiers.length > 0 && (
        <p className="text-[11px] font-mono text-[var(--text-secondary)] leading-relaxed">
          {run.identifiers.join("  ·  ")}
        </p>
      )}

      {runtime.length > 0 && (
        <ul className="space-y-1">
          {runtime.map((file) => (
            <li
              key={file.path}
              className="flex items-baseline justify-between gap-4 text-[12px]"
            >
              <span className="font-mono text-[var(--text-primary)] truncate">{file.path}</span>
              <span className="font-mono text-[11px] tabular-nums text-[var(--text-secondary)] shrink-0">
                {file.hits}
              </span>
            </li>
          ))}
        </ul>
      )}

      {other.length > 0 && (
        <p className="text-[11px] text-[var(--text-secondary)]">
          {other.length} documentation and changelog
          {other.length === 1 ? " file" : " files"} — not in the patch
        </p>
      )}

      {runtime.length === 0 && other.length > 0 && (
        <p className="text-[12px] text-[var(--text-secondary)]">
          No runtime path at this SHA.
        </p>
      )}
    </div>
  );
}

function SandboxTree({ run }: { run: MockRun }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Meta label="Reset" value={`every attempt → ${shortSha(run.baseSha)}`} />
      <Meta label="Merge" value="never" />
    </div>
  );
}

function ProposedTree({ run }: { run: MockRun }) {
  const verified = run.machine === "PR_CREATED" || run.machine === "VERIFYING";
  const failed = run.machine === "FAILED";

  return (
    <div className="space-y-4">
      <section>
        <h3 className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
          Independent verification
        </h3>
        <div className="mt-1.5 border border-[var(--border-color)] rounded-md px-3 py-2.5">
          <p className="text-[12px] text-[var(--text-primary)]">
            {failed
              ? "Verifier disagreed with the sandbox. Fail closed. No pull request."
              : verified
                ? "Verifier is not the patch author and was not given the patch plan."
                : "Nothing has graded this run."}
          </p>
          <ul className="mt-2 space-y-1">
            {run.checks.map((check) => (
              <li key={check.name} className="flex items-start gap-2 text-[11px]">
                {check.passed && (verified || failed) ? (
                  <Check className="h-3 w-3 mt-0.5 text-emerald-500 shrink-0" />
                ) : failed && !check.passed ? (
                  <X className="h-3 w-3 mt-0.5 text-red-500 shrink-0" />
                ) : (
                  <Lock className="h-3 w-3 mt-0.5 text-[var(--text-secondary)] shrink-0" />
                )}
                <span className="text-[var(--text-secondary)]">{check.name}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {run.diffs.length > 0 && (
        <section>
          <h3 className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
            Unified diff against {shortSha(run.baseSha)}
          </h3>
          <div className="mt-1.5 space-y-2">
            {run.diffs.map((file) => (
              <DiffCard key={file.path} file={file} />
            ))}
          </div>
        </section>
      )}

      {run.machine === "PR_CREATED" && <PullRequestCard run={run} />}
    </div>
  );
}

function DiffCard({ file }: { file: DiffFile }) {
  return (
    <div className="border border-[var(--border-color)] rounded-md overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-3 py-1.5 bg-[var(--bg-secondary)]">
        <span className="text-[11px] font-mono text-[var(--text-primary)] truncate">{file.path}</span>
        <span className="text-[10px] font-mono shrink-0">
          <span className="text-emerald-500">+{file.additions}</span>
          <span className="mx-1 text-[var(--text-secondary)]">/</span>
          <span className="text-red-400">−{file.deletions}</span>
        </span>
      </div>
      <pre className="px-3 py-2 text-[11px] font-mono leading-relaxed overflow-x-auto">
        {file.lines.map((line, index) => (
          <DiffLineRow key={`${file.path}-${index}`} line={line} />
        ))}
      </pre>
    </div>
  );
}

function DiffLineRow({ line }: { line: DiffLine }) {
  const mark = line.kind === "add" ? "+" : line.kind === "del" ? "−" : " ";
  return (
    <div
      className={cn(
        "px-1 -mx-1 rounded-sm",
        line.kind === "add" && "bg-emerald-500/10 text-emerald-400",
        line.kind === "del" && "bg-red-500/10 text-red-400",
        line.kind === "ctx" && "text-[var(--text-secondary)]",
      )}
    >
      <span className="inline-block w-3 select-none">{mark}</span>
      {line.text}
    </div>
  );
}

const VERB_TOOL: Record<string, string> = {
  Read: "Read",
  Apply: "Bash",
  Run: "Bash",
  Normalize: "Normalize",
  Evaluate: "Evaluate",
  Verify: "Verify",
};

function toWorklog(lines: AgentLogLine[]): WorklogEntry[] {
  return lines.map((line) => {
    const toolType = line.toolType ?? (line.verb ? VERB_TOOL[line.verb] : undefined);
    if (line.kind === "thought") {
      return { kind: "thinking", text: line.text };
    }
    if (line.kind === "action") {
      return {
        kind: "action",
        text: line.text,
        toolType,
        toolUseId: line.toolUseId,
        filePath: line.filePath,
      };
    }
    if (line.kind === "result") {
      return {
        kind: "result",
        text: line.text,
        toolType,
        toolUseId: line.toolUseId,
      };
    }
    if (line.kind === "block") {
      return { kind: "block", text: line.text };
    }
    return { kind: "narration", text: line.text };
  });
}

function rewriteTerminalFence(text: string, file?: string): string {
  const fence = text.trim().match(/^```(?:terminal|bash|sh)\n([\s\S]*?)\n```$/);
  if (!fence) return text;
  const body = fence[1];
  const command = body.split("\n").find((line) => line.startsWith("$ "))?.slice(2);
  if (!command) return text;
  const out = cursorStdout(command, file);
  if (!out) return text;
  const dir = body.split("\n").find((line) => line.startsWith("# ")) ?? "# /tmp/patchapi-sandbox";
  return ["```terminal", dir, `$ ${command}`, ...out.split("\n"), "```"].join("\n");
}

function withCursorStdout(entries: WorklogEntry[], file?: string): WorklogEntry[] {
  return entries.map((entry) => {
    if (entry.kind === "block") {
      return { ...entry, text: rewriteTerminalFence(entry.text, file) };
    }
    if (entry.kind !== "action") return entry;
    const out = cursorStdout(entry.text, file);
    return out ? { ...entry, result: out } : entry;
  });
}

function AgentLog({ run }: { run: MockRun }) {
  const lines = visibleLog(run);
  const sample = run.files.find((file) => file.kind === "runtime")?.path ?? run.files[0]?.path;
  const entries = collapseWorklogEntries(
    withCursorStdout(pairActionResults(toWorklog(lines)), sample),
  );
  const endRef = useRef<HTMLDivElement>(null);
  const live = run.bucket === "active";
  const last = lines[lines.length - 1];

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [run.revealed, run.machine]);

  return (
    <section>
      <h3 className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
        Log
      </h3>
      <div className="mt-2">
        <WorklogView entries={entries} idPrefix={run.id} />
        {live && last && (
          <ActivitySpinner
            activeTool={{
              verb:
                last.kind === "thought"
                  ? "Thinking"
                  : last.kind === "action"
                    ? (last.verb ?? "Running")
                    : "Working",
              detail: last.kind === "action" ? last.text : undefined,
              startedAt: run.lineStartedAt,
            }}
          />
        )}
        <div ref={endRef} />
      </div>
    </section>
  );
}

function PullRequestCard({ run }: { run: MockRun }) {
  const repo = run.repo ?? "imported repositories";
  const href = run.repo ? `https://github.com/${run.repo}` : undefined;

  return (
    <div className="overflow-hidden rounded-lg border border-emerald-500/25 bg-[var(--bg-secondary)]">
      <div className="flex items-center justify-between gap-3 px-3.5 py-2.5 border-b border-[var(--border-color)]">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-emerald-500/10">
            <GitPullRequest className="h-3.5 w-3.5 text-emerald-500" />
          </span>
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-[var(--text-primary)]">Pull request opened</p>
            <p className="text-[11px] text-[var(--text-secondary)] truncate">{repo}</p>
          </div>
        </div>
        <span className="shrink-0 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-500">
          Ready for review
        </span>
      </div>

      <div className="px-3.5 py-3 space-y-3">
        <div className="flex items-center gap-2 min-w-0">
          <BranchChip name={run.prBranch ?? "proposed"} active />
          <ArrowRight className="h-3.5 w-3.5 shrink-0 text-[var(--text-secondary)]" />
          <BranchChip name="main" muted />
        </div>
        <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
          PatchAPI stops here. It does not merge.
        </p>
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-[12px] font-medium text-primary hover:underline underline-offset-2"
          >
            Review on GitHub
            <ExternalLink className="h-3 w-3" />
          </a>
        ) : (
          <p className="text-[12px] font-medium text-[var(--text-secondary)]">Review on GitHub</p>
        )}
      </div>
    </div>
  );
}

function BranchChip({
  name,
  sha,
  active,
  muted,
}: {
  name: string;
  sha?: string;
  active?: boolean;
  muted?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs border max-w-full",
        active
          ? "bg-primary/10 border-primary/30 text-primary"
          : "bg-[var(--bg-tertiary)] border-[var(--border-color)] text-[var(--text-secondary)]",
        muted && !active && "opacity-70",
      )}
    >
      <GitBranch className="h-3 w-3 shrink-0 opacity-70" />
      <span className="font-mono text-[11px] truncate">{name}</span>
      {sha && (
        <span className="font-mono text-[10px] opacity-70 shrink-0">{sha}</span>
      )}
    </span>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
        {label}
      </p>
      <p className="mt-0.5 text-[12px] font-mono text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

export function bucketNeedsYou(bucket: RunBucket): boolean {
  return bucket === "needs_attention" || bucket === "ready_for_review";
}
