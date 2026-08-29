"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { ActivitySpinner, WorklogView } from "@/components/console/worklog-view";
import { collapseWorklogEntries, pairActionResults } from "@/components/console/thread-worklog";
import { DiffBlock } from "@/components/chat/code-block/diff-block";
import { TerminalBlock } from "@/components/chat/code-block/terminal-block";
import type { WorklogEntry } from "@/components/console/thread-types";
import {
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FolderGit2,
  GitBranch,
  Github,
  GitPullRequest,
  Lock,
  Radio,
  Search,
  X,
} from "lucide-react";
import { AddSecretDialog, type SecretRepoOption, type SecretWorkspaceOption } from "@/components/interface/secret-managers";
import { GCPConnectMethodDialog } from "@/components/interface/ops/configure-tab/gcp-connect-method-dialog";
import { UNSCOPED_REPO, repoOf, repoTitle } from "./data";
import { DEMO_REPO, isDemoRun } from "./mock-log/demo-runs";
import { DemoLog } from "./mock-log/run-log";
import {
  HUMAN_REQUIRED_PAUSE,
  HUMAN_REQUIRED_SECRET_NAME,
  MACHINE_LABEL,
  failureCopy,
  proposedPending,
  treeAvailable,
  treeForMachine,
  visibleLog,
  type AgentLogLine,
  type DiffFile,
  type MockRun,
  type RunBucket,
  type TreeId,
} from "./run-scripts";

const GCP_ENV_OPTIONS = [
  { value: "development", label: "Development" },
  { value: "staging", label: "Staging" },
  { value: "production", label: "Production" },
];

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

function statusTone(bucket: RunBucket): string {
  if (bucket === "active") return "text-sky-400";
  if (bucket === "needs_attention") return "text-amber-500";
  if (bucket === "ready_for_review") return "text-emerald-500";
  if (bucket === "blocked") return "text-red-500";
  return "text-[var(--text-secondary)]";
}

function statusBar(bucket: RunBucket): string {
  if (bucket === "active") return "bg-sky-400";
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
    hint: "",
  },
};

export function RunsPanel({
  runs,
  selectedId,
  onSelect,
  onContinue,
  projectId,
  userId = "default",
  workspaces = [],
  repos = [],
  secretsPreviewMode = false,
}: {
  runs: MockRun[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onContinue: (id: string) => void;
  projectId?: string;
  userId?: string;
  workspaces?: SecretWorkspaceOption[];
  repos?: SecretRepoOption[];
  secretsPreviewMode?: boolean;
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
      <RunsList runs={runs} selected={selected} onSelect={onSelect} />
      {selected && (
        <RunDetail
          run={selected}
          onContinue={() => onContinue(selected.id)}
          projectId={projectId}
          userId={userId}
          workspaces={workspaces}
          repos={repos}
          secretsPreviewMode={secretsPreviewMode}
        />
      )}
    </div>
  );
}

function runMatches(run: MockRun, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay = [
    run.title,
    run.code,
    MACHINE_LABEL[run.machine],
    run.repo,
    run.baseSha,
    ...run.identifiers,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
}

function RunsList({
  runs,
  selected,
  onSelect,
}: {
  runs: MockRun[];
  selected: MockRun | null;
  onSelect: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const groups = useMemo(() => {
    const visible = query.trim() ? runs.filter((run) => runMatches(run, query)) : runs;
    return groupRuns(visible);
  }, [runs, query]);
  const [open, setOpen] = useState<Set<string>>(() => new Set(groupRuns(runs).map(([repo]) => repo)));

  useEffect(() => {
    if (!selected) return;
    const repo = repoOf(selected);
    setOpen((prev) => {
      if (prev.has(repo)) return prev;
      const next = new Set(prev);
      next.add(repo);
      return next;
    });
  }, [selected?.id]);

  useEffect(() => {
    if (!query.trim()) return;
    setOpen(new Set(groups.map(([repo]) => repo)));
  }, [query, groups]);

  const toggle = (repo: string) => {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(repo)) next.delete(repo);
      else next.add(repo);
      return next;
    });
  };

  return (
    <div className="w-72 flex-shrink-0 border-r border-[var(--border-color)] flex flex-col overflow-hidden bg-[var(--bg-primary)]">
      <div className="p-3 border-b border-[var(--border-color)] shrink-0">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-secondary)]" />
          <Input
            type="text"
            placeholder="Search runs..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-7 pl-7 pr-7 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {groups.length === 0 && (
          <p className="px-3 py-6 text-center text-[12px] text-[var(--text-secondary)]">
            No runs match
          </p>
        )}
        {groups.map(([repo, items]) => {
          const expanded = open.has(repo);
          const attention = items.filter((run) => run.bucket === "needs_attention" || run.bucket === "blocked").length;
          return (
            <div key={repo}>
              <button
                type="button"
                onClick={() => toggle(repo)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] font-medium uppercase [font-family:var(--font-space-grotesk)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] border-b border-[var(--border-color)] bg-[var(--bg-secondary)]/30 hover:bg-[var(--bg-secondary)]/50 transition-colors"
              >
                {expanded ? (
                  <ChevronDown className="h-3 w-3 shrink-0" />
                ) : (
                  <ChevronRight className="h-3 w-3 shrink-0" />
                )}
                {repo === UNSCOPED_REPO ? (
                  <Radio className="h-3.5 w-3.5 shrink-0" />
                ) : (
                  <Github className="h-3.5 w-3.5 shrink-0" />
                )}
                <span className="truncate">{repoTitle(repo)}</span>
                {repo === DEMO_REPO && (
                  <span className="rounded px-1 py-px text-[9px] font-medium normal-case tracking-normal text-[var(--text-tertiary)]">
                    demo
                  </span>
                )}
                <span className="ml-auto flex items-center gap-1.5 shrink-0">
                  {attention > 0 && <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />}
                  <span className="text-[9px] tabular-nums normal-case tracking-normal">{items.length}</span>
                </span>
              </button>
              {expanded && (
                <div className="py-1">
                  {items.map((run) => {
                    const active = selected?.id === run.id;
                    return (
                      <button
                        key={run.id}
                        type="button"
                        onClick={() => onSelect(run.id)}
                        className={cn(
                          "relative w-full text-left px-3 py-2 transition-colors",
                          active
                            ? "bg-[var(--bg-tertiary)]"
                            : "hover:bg-[var(--bg-secondary)]",
                        )}
                      >
                        {active && (
                          <span
                            className={cn(
                              "absolute left-0 top-2 bottom-2 w-px",
                              statusBar(run.bucket),
                            )}
                          />
                        )}
                        <div className="flex items-center gap-2">
                          <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", statusDot(run.bucket))} />
                          <span
                            className={cn(
                              "text-[10px] font-medium uppercase tracking-wide truncate",
                              statusTone(run.bucket),
                            )}
                          >
                            {MACHINE_LABEL[run.machine]}
                          </span>
                          <span className="ml-auto shrink-0 text-[10px] text-[var(--text-secondary)]">
                            {timeAgo(run.createdAt)}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[12px] leading-snug line-clamp-2 text-[var(--text-primary)]">
                          {run.title}
                        </p>
                        {run.baseSha && (
                          <p className="mt-0.5 text-[10px] font-mono text-[var(--text-secondary)]">
                            {shortSha(run.baseSha)}
                          </p>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RunDetail({
  run,
  onContinue,
  projectId,
  userId,
  workspaces,
  repos,
  secretsPreviewMode,
}: {
  run: MockRun;
  onContinue: () => void;
  projectId?: string;
  userId: string;
  workspaces: SecretWorkspaceOption[];
  repos: SecretRepoOption[];
  secretsPreviewMode: boolean;
}) {
  const current = treeForMachine(run);
  const [picked, setPicked] = useState<TreeId | null>(null);
  const [secretOpen, setSecretOpen] = useState(false);
  const [gcpOpen, setGcpOpen] = useState(false);
  const [gcpEnv, setGcpEnv] = useState("development");

  useEffect(() => {
    setPicked(null);
    setSecretOpen(false);
    setGcpOpen(false);
  }, [run.id, run.machine]);

  const tree = picked ?? current;

  return (
    <div className="flex-1 min-w-0 flex flex-col">
      {(run.machine === "WAITING_ON_OPERATOR" || run.machine === "HUMAN_REQUIRED") && (
        <div className="px-5 py-3 border-b border-amber-500/30 bg-amber-500/5 flex items-start justify-between gap-3">
          <p className="text-[12px] text-[var(--text-primary)] leading-relaxed">
            {run.pauseReason ?? HUMAN_REQUIRED_PAUSE}
          </p>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              size="sm"
              className="h-7 text-xs bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={() => setGcpOpen(true)}
            >
              Connect GCP
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={() => setSecretOpen(true)}
            >
              Add secret
            </Button>
          </div>
        </div>
      )}
      <AddSecretDialog
        open={secretOpen}
        onOpenChange={setSecretOpen}
        mode="add"
        projectId={projectId}
        workspaces={workspaces}
        repoFullName={run.repo ?? repos[0]?.fullName ?? null}
        repos={repos}
        secretsPreviewMode={secretsPreviewMode}
        initialSecretName={HUMAN_REQUIRED_SECRET_NAME}
        onSaved={() => {
          setSecretOpen(false);
          onContinue();
        }}
      />
      <GCPConnectMethodDialog
        open={gcpOpen}
        onOpenChange={setGcpOpen}
        userId={userId}
        environment={gcpEnv}
        onEnvironmentChange={setGcpEnv}
        environmentOptions={GCP_ENV_OPTIONS}
        projectId={projectId}
        workspaces={workspaces}
        repoFullName={run.repo ?? null}
        repos={repos}
        onConnectSuccess={() => {
          setGcpOpen(false);
          onContinue();
        }}
      />
      {(run.machine === "FAILED" || run.machine === "BLOCKED") && (
        <div className="px-5 py-3 border-b border-red-500/30 bg-red-500/5">
          <p className="text-[12px] text-[var(--text-primary)] leading-relaxed">
            {run.machine === "FAILED"
              ? failureCopy(run.pauseReason)
              : (run.pauseReason ?? "Policy blocked this path. No sandbox and no pull request.")}
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

      <TreeRail run={run} tree={tree} onPick={setPicked} />

      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-3 space-y-4">
        <AgentLog run={run} />
        <section>
          {TREE_COPY[tree].hint && (
            <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
              {TREE_COPY[tree].hint}
            </p>
          )}
          <div className={TREE_COPY[tree].hint ? "mt-2" : undefined}>
            {tree === "base" && <BaseTree run={run} />}
            {tree === "sandbox" && <SandboxTree run={run} />}
            {tree === "proposed" && <ProposedTree run={run} />}
          </div>
        </section>
      </div>
    </div>
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

function commandFence(commands: { argv: string; tail: string }[]): string {
  return commands
    .map((command) => [`$ ${command.argv}`, command.tail].filter(Boolean).join("\n"))
    .join("\n");
}

function SandboxTree({ run }: { run: MockRun }) {
  const baseline = run.commands.filter((command) => command.source === "baseline");
  const patched = run.commands.filter((command) => command.source !== "baseline");

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Meta label="Reset" value={`every attempt → ${shortSha(run.baseSha)}`} />
        <Meta label="Merge" value="never" />
      </div>
      {baseline.length > 0 && (
        <section>
          <h3 className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
            Before the patch
          </h3>
          <TerminalBlock className="!mt-1.5 !mb-0" code={commandFence(baseline)} />
        </section>
      )}
      {patched.length > 0 && (
        <section>
          <h3 className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
            After the patch
          </h3>
          <TerminalBlock className="!mt-1.5 !mb-0" code={commandFence(patched)} />
        </section>
      )}
      {run.commands.length === 0 && (
        <p className="text-[12px] text-[var(--text-secondary)]">
          No build or test log recorded for this attempt yet.
        </p>
      )}
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
          {(failed || !verified) && (
            <p className="text-[12px] text-[var(--text-primary)]">
              {failed
                ? run.pauseReason
                  ? failureCopy(run.pauseReason)
                  : "Nothing has graded this run. Fail closed. No pull request."
                : "Nothing has graded this run."}
            </p>
          )}
          <ul className={failed || !verified ? "mt-2 space-y-1" : "space-y-1"}>
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
          <div className="mt-1.5 space-y-1">
            {run.diffs.map((file) => (
              <DiffBlock key={file.path} code={unifiedFrom(file)} />
            ))}
          </div>
        </section>
      )}

      {run.machine === "PR_CREATED" && <PullRequestCard run={run} />}
    </div>
  );
}

function unifiedFrom(file: DiffFile): string {
  const lines = [`--- a/${file.path}`, `+++ b/${file.path}`];
  for (const line of file.lines) {
    if (line.text.startsWith("@@")) {
      lines.push(line.text);
      continue;
    }
    if (line.kind === "add") lines.push(`+${line.text}`);
    else if (line.kind === "del") lines.push(`-${line.text}`);
    else lines.push(line.text.startsWith(" ") ? line.text : ` ${line.text}`);
  }
  return lines.join("\n");
}

const VERB_TOOL: Record<string, string> = {
  Read: "Read",
  Apply: "Edit",
  Write: "Write",
  Run: "Bash",
  Normalize: "Normalize",
  Evaluate: "Evaluate",
  Verify: "Verify",
  List: "List",
  Request: "Request",
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

function AgentLog({ run }: { run: MockRun }) {
  if (isDemoRun(run)) return <DemoLog run={run} />;
  const lines = visibleLog(run);
  const entries = collapseWorklogEntries(pairActionResults(toWorklog(lines)));
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
  const repo = run.repo ? repoTitle(run.repo) : "imported repositories";
  const href =
    run.prUrl || (run.repo && run.prNumber ? `https://github.com/${run.repo}/pull/${run.prNumber}` : undefined);

  return (
    <div className="overflow-hidden rounded-lg border border-emerald-500/25 bg-[var(--bg-secondary)]">
      <div className="flex items-center justify-between gap-3 px-3.5 py-2.5 border-b border-[var(--border-color)]">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-emerald-500/10">
            <GitPullRequest className="h-3.5 w-3.5 text-emerald-500" />
          </span>
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-[var(--text-primary)]">
              {run.prNumber ? `Pull request #${run.prNumber}` : "Pull request opened"}
            </p>
            <p className="text-[11px] text-[var(--text-secondary)] truncate">
              {run.prTitle || repo}
            </p>
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
          <BranchChip name={run.prBase ?? "main"} muted />
        </div>
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

function TreeRail({
  run,
  tree,
  onPick,
}: {
  run: MockRun;
  tree: TreeId;
  onPick: (id: TreeId) => void;
}) {
  const steps: {
    id: TreeId;
    icon: typeof GitBranch;
    chip: { name: string; sha?: string } | { pending: string };
  }[] = [
    {
      id: "base",
      icon: GitBranch,
      chip: { name: "main", sha: shortSha(run.baseSha) },
    },
    {
      id: "sandbox",
      icon: FolderGit2,
      chip: treeAvailable(run, "sandbox")
        ? { name: "worktree", sha: shortSha(run.baseSha) }
        : { pending: "not allocated" },
    },
    {
      id: "proposed",
      icon: GitPullRequest,
      chip:
        treeAvailable(run, "proposed") && run.prBranch && run.machine !== "FAILED"
          ? { name: run.prBranch }
          : { pending: proposedPending(run) },
    },
  ];

  return (
    <div className="px-4 py-3 border-b border-[var(--border-color)]">
      <div className="flex items-stretch gap-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] p-1">
        {steps.map((step) => {
          const open = treeAvailable(run, step.id);
          const selected = tree === step.id;
          return (
            <button
              key={step.id}
              type="button"
              disabled={!open}
              onClick={() => onPick(step.id)}
              className={cn(
                "min-w-0 flex-1 rounded-md px-2.5 py-1.5 text-left transition-colors",
                selected
                  ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] shadow-sm ring-1 ring-primary/25"
                  : "text-[var(--text-secondary)]",
                open && !selected && "hover:bg-[var(--bg-tertiary)]/60 hover:text-[var(--text-primary)]",
                !open && "cursor-not-allowed opacity-45",
              )}
            >
                <div className="flex items-center gap-1.5 min-w-0">
                  <step.icon className="h-3.5 w-3.5 shrink-0" />
                  <span className="text-[11px] font-medium shrink-0">
                    {TREE_COPY[step.id].label}
                  </span>
                  {"pending" in step.chip ? (
                    <span className="min-w-0 truncate rounded-md border border-dashed border-[var(--border-color)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
                      {step.chip.pending}
                    </span>
                  ) : (
                    <BranchChip
                      name={step.chip.name}
                      sha={step.chip.sha}
                      active={selected}
                      muted={!selected}
                      showIcon={false}
                    />
                  )}
                </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function BranchChip({
  name,
  sha,
  active,
  muted,
  showIcon = true,
}: {
  name: string;
  sha?: string;
  active?: boolean;
  muted?: boolean;
  showIcon?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex min-w-0 items-center gap-1.5 px-2 py-0.5 rounded-md text-xs border",
        active
          ? "bg-primary/10 border-primary/30 text-primary"
          : "bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-secondary)]",
        muted && !active && "opacity-80",
      )}
    >
      {showIcon && <GitBranch className="h-3 w-3 shrink-0 opacity-70" />}
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
