"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Check, GitPullRequest, Loader2, Radio } from "lucide-react";
import {
  BUCKET_LABEL,
  BUCKET_TONE,
  type MockRun,
  type RunBucket,
  type RunTodo,
} from "./run-scripts";

function timeAgo(ts: number): string {
  const seconds = Math.max(1, Math.round((Date.now() - ts) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

function statusDot(bucket: RunBucket): string {
  if (bucket === "active") return "bg-sky-400 animate-pulse";
  if (bucket === "needs_attention") return "bg-amber-500";
  if (bucket === "ready_for_review") return "bg-emerald-500";
  if (bucket === "blocked") return "bg-red-500";
  return "bg-[var(--text-secondary)]";
}

function repoShort(repo?: string): string | undefined {
  if (!repo) return undefined;
  return repo.split("/")[1] ?? repo;
}

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
            Start a remediation from Releases. Each run is one piece of work — it stops at a pull
            request.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex min-w-0 bg-[var(--bg-primary)]">
      <div className="w-[280px] flex-shrink-0 border-r border-[var(--border-color)] overflow-y-auto">
        <div className="px-4 pt-4 pb-2">
          <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
            {runs.length} {runs.length === 1 ? "run" : "runs"}
          </p>
        </div>
        <div className="px-2 pb-3 space-y-0.5">
          {runs.map((run) => {
            const active = selected?.id === run.id;
            const done = run.todos.filter((t) => t.state === "completed").length;
            return (
              <button
                key={run.id}
                type="button"
                onClick={() => onSelect(run.id)}
                className={cn(
                  "w-full text-left rounded-lg px-2.5 py-2.5 transition-colors",
                  active
                    ? "bg-[var(--bg-tertiary)]"
                    : "hover:bg-[var(--bg-secondary)]",
                )}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", statusDot(run.bucket))} />
                  <span className="text-[10px] font-medium uppercase tracking-wide text-[var(--text-secondary)] truncate">
                    {BUCKET_LABEL[run.bucket]}
                  </span>
                  <span className="ml-auto text-[10px] tabular-nums text-[var(--text-secondary)]">
                    {done}/{run.todos.length}
                  </span>
                </div>
                <p className="text-[13px] text-[var(--text-primary)] leading-snug line-clamp-2">
                  {run.title}
                </p>
                <p className="text-[11px] text-[var(--text-secondary)] mt-1 truncate">
                  {run.code}
                  {repoShort(run.repo) ? (
                    <>
                      <span className="mx-1.5 text-[var(--border-color)]">·</span>
                      {repoShort(run.repo)}
                    </>
                  ) : null}
                  <span className="mx-1.5 text-[var(--border-color)]">·</span>
                  {timeAgo(run.createdAt)}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {selected && <RunDetail run={selected} onContinue={() => onContinue(selected.id)} />}
    </div>
  );
}

function RunDetail({ run, onContinue }: { run: MockRun; onContinue: () => void }) {
  const done = run.todos.filter((t) => t.state === "completed").length;
  const progress = run.todos.length === 0 ? 0 : Math.round((done / run.todos.length) * 100);

  return (
    <div className="flex-1 min-w-0 flex flex-col">
      <div className="px-6 pt-5 pb-0 border-b border-[var(--border-color)]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] text-[var(--text-secondary)] font-mono">{run.code}</p>
            <h2 className="text-[15px] font-semibold text-[var(--text-primary)] mt-1 tracking-tight">
              {run.title}
            </h2>
            <p className="text-[12px] text-[var(--text-secondary)] mt-1.5 truncate">
              {[run.repo ?? "this project", run.baseSha ? run.baseSha.slice(0, 7) : null]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
          <span
            className={cn(
              "shrink-0 inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
              BUCKET_TONE[run.bucket],
            )}
          >
            {BUCKET_LABEL[run.bucket]}
          </span>
        </div>

        <p className="mt-3 mb-4 text-[12px] text-[var(--text-secondary)] leading-relaxed max-w-2xl">
          {run.prompt}
        </p>

        <div className="h-0.5 w-full rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-300",
              run.bucket === "blocked"
                ? "bg-red-500"
                : run.bucket === "needs_attention"
                  ? "bg-amber-500"
                  : run.bucket === "ready_for_review" || run.bucket === "idle"
                    ? "bg-emerald-500"
                    : "bg-sky-400",
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="mt-1.5 mb-3 text-[10px] tabular-nums text-[var(--text-secondary)]">
          {done} of {run.todos.length} steps
        </p>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="max-w-[680px] mx-auto px-6 py-6">
          <ol className="relative">
            {run.todos.map((todo, index) => (
              <TimelineStep
                key={todo.id}
                todo={todo}
                last={index === run.todos.length - 1}
                onContinue={onContinue}
              />
            ))}
          </ol>

          {run.outcome && (
            <div
              className={cn(
                "mt-2 rounded-lg border px-4 py-3",
                run.bucket === "ready_for_review"
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : "border-[var(--border-color)] bg-[var(--bg-secondary)]",
              )}
            >
              <p className="text-[13px] text-[var(--text-primary)] leading-relaxed">{run.outcome}</p>
              {run.bucket === "ready_for_review" && (
                <div className="mt-3 flex items-center justify-between gap-3 rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)] px-3 py-2.5">
                  <div className="min-w-0">
                    <p className="text-[12px] font-medium text-[var(--text-primary)] truncate">
                      {run.prLabel ?? `${run.repo ?? "repo"} · pull request`}
                    </p>
                    <p className="text-[11px] text-[var(--text-secondary)] mt-0.5">
                      {run.fileCount
                        ? `${run.fileCount} files · review on GitHub · PatchAPI does not merge`
                        : "Review on GitHub · PatchAPI does not merge"}
                    </p>
                  </div>
                  <GitPullRequest className="h-4 w-4 text-emerald-500 shrink-0" />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TimelineStep({
  todo,
  last,
  onContinue,
}: {
  todo: RunTodo;
  last: boolean;
  onContinue: () => void;
}) {
  const waiting = todo.state === "in_progress" && Boolean(todo.pause);
  const working = todo.state === "in_progress" && !todo.pause;
  const done = todo.state === "completed";
  const pending = todo.state === "pending" || todo.state === "deferred" || todo.state === "cancelled";

  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center w-5 shrink-0">
        <span
          className={cn(
            "mt-0.5 flex h-5 w-5 items-center justify-center rounded-full border",
            done && "border-emerald-500/40 bg-emerald-500/10",
            working && "border-sky-400/40 bg-sky-400/10",
            waiting && "border-amber-500/40 bg-amber-500/10",
            pending && "border-[var(--border-color)] bg-[var(--bg-primary)]",
          )}
        >
          {done ? (
            <Check className="h-3 w-3 text-emerald-500" />
          ) : working ? (
            <Loader2 className="h-3 w-3 text-sky-400 animate-spin" />
          ) : waiting ? (
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
          ) : (
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--border-color)]" />
          )}
        </span>
        {!last && <span className="mt-1 w-px flex-1 min-h-[12px] bg-[var(--border-color)]" />}
      </div>

      <div className={cn("min-w-0 flex-1", last ? "pb-0" : "pb-5")}>
        <div className="flex items-baseline justify-between gap-3">
          <p
            className={cn(
              "text-[13px] font-medium leading-snug",
              pending ? "text-[var(--text-secondary)]" : "text-[var(--text-primary)]",
            )}
          >
            {todo.label}
          </p>
          <span className="shrink-0 text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">
            {todo.agent}
          </span>
        </div>

        {pending ? null : waiting ? (
          <div className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2.5">
            <p className="text-[12px] text-[var(--text-primary)] leading-relaxed">
              {todo.pausePrompt ?? todo.detail}
            </p>
            <Button
              size="sm"
              className="mt-2.5 h-8 text-xs bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={onContinue}
            >
              Continue
            </Button>
          </div>
        ) : (
          <p
            className={cn(
              "mt-1 text-[12px] leading-relaxed",
              working ? "text-[var(--text-secondary)] italic" : "text-[var(--text-secondary)]",
            )}
          >
            {todo.detail}
          </p>
        )}
      </div>
    </li>
  );
}

export function bucketNeedsYou(bucket: RunBucket): boolean {
  return bucket === "needs_attention" || bucket === "ready_for_review";
}
