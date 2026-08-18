"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Check,
  Circle,
  GitPullRequest,
  Loader2,
  Minus,
  Play,
  Radio,
} from "lucide-react";
import {
  BUCKET_LABEL,
  BUCKET_TONE,
  type MockRun,
  type RunBucket,
  type TodoState,
} from "./run-scripts";

function todoIcon(state: TodoState) {
  if (state === "completed") {
    return <Check className="h-3 w-3 text-emerald-500" />;
  }
  if (state === "in_progress") {
    return <Loader2 className="h-3 w-3 text-sky-400 animate-spin" />;
  }
  if (state === "cancelled" || state === "deferred") {
    return <Minus className="h-3 w-3 text-[var(--text-secondary)]" />;
  }
  return <Circle className="h-3 w-3 text-[var(--text-secondary)]" />;
}

function timeAgo(ts: number): string {
  const seconds = Math.max(1, Math.round((Date.now() - ts) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.round(seconds / 60)}m ago`;
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
        <div className="text-center max-w-md px-4">
          <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
            <Radio className="h-5 w-5 text-[var(--text-secondary)]" />
          </div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">No runs yet</h2>
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
            Start a remediation from Releases. The fleet works here — normalize, impact, patch in
            isolation, verify, then stop at a pull request.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex min-w-0 bg-[var(--bg-primary)]">
      <div className="w-64 flex-shrink-0 border-r border-[var(--border-color)] overflow-y-auto">
        <div className="px-3 pt-3 pb-2">
          <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
            Runs
          </p>
        </div>
        <div className="px-2 pb-3 space-y-1">
          {runs.map((run) => {
            const active = selected?.id === run.id;
            const done = run.todos.filter((t) => t.state === "completed").length;
            return (
              <button
                key={run.id}
                type="button"
                onClick={() => onSelect(run.id)}
                className={cn(
                  "w-full text-left rounded-lg px-2.5 py-2 transition-colors",
                  active
                    ? "bg-[var(--bg-tertiary)]"
                    : "hover:bg-[var(--bg-secondary)]",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-[var(--text-primary)] truncate">
                    {run.title}
                  </span>
                  <Badge variant="outline" className={cn("text-[9px] shrink-0", BUCKET_TONE[run.bucket])}>
                    {BUCKET_LABEL[run.bucket]}
                  </Badge>
                </div>
                <p className="text-[10px] text-[var(--text-secondary)] mt-1">
                  {done}/{run.todos.length} · {timeAgo(run.createdAt)}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {selected && (
        <RunDetail run={selected} onContinue={() => onContinue(selected.id)} />
      )}
    </div>
  );
}

function RunDetail({ run, onContinue }: { run: MockRun; onContinue: () => void }) {
  const current = run.todos.find((t) => t.state === "in_progress");
  const done = run.todos.filter((t) => t.state === "completed").length;

  return (
    <div className="flex-1 min-w-0 overflow-y-auto">
      <div className="border-b border-[var(--border-color)] px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">{run.title}</h2>
              <Badge variant="outline" className={cn("text-[9px]", BUCKET_TONE[run.bucket])}>
                {BUCKET_LABEL[run.bucket]}
              </Badge>
              <Badge
                variant="outline"
                className="text-[9px] text-[var(--text-secondary)] border-[var(--border-color)]"
              >
                simulated
              </Badge>
            </div>
            <p className="text-[11px] text-[var(--text-secondary)] mt-1.5 font-mono">
              {run.repo ?? "this project"}
              {run.baseSha ? ` @ ${run.baseSha.slice(0, 12)}` : ""}
              {` · ${run.traceId}`}
            </p>
          </div>
          {run.bucket === "ready_for_review" && (
            <Button
              size="sm"
              className="h-7 text-xs bg-primary text-primary-foreground hover:bg-primary/90"
              disabled
            >
              <GitPullRequest className="h-3 w-3 mr-1" />
              {run.prLabel ?? "View pull request"}
            </Button>
          )}
        </div>
      </div>

      <div className="px-5 py-4 space-y-4 max-w-2xl">
        <div className="flex items-center justify-between">
          <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
            Plan
          </p>
          <p className="text-[10px] text-[var(--text-secondary)] tabular-nums">
            {done} of {run.todos.length}
          </p>
        </div>

        <ol className="space-y-0">
          {run.todos.map((todo, index) => {
            const last = index === run.todos.length - 1;
            const live = todo.state === "in_progress";
            return (
              <li key={todo.id} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div
                    className={cn(
                      "h-5 w-5 rounded-full flex items-center justify-center shrink-0",
                      live && "bg-sky-400/10",
                      todo.state === "completed" && "bg-emerald-500/10",
                    )}
                  >
                    {todoIcon(todo.state)}
                  </div>
                  {!last && (
                    <span
                      className={cn(
                        "w-px flex-1 my-1",
                        todo.state === "completed" ? "bg-emerald-500/30" : "bg-[var(--border-color)]",
                      )}
                    />
                  )}
                </div>
                <div className={cn("min-w-0 flex-1", last ? "pb-0" : "pb-4")}>
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span
                      className={cn(
                        "text-xs font-medium",
                        live ? "text-[var(--text-primary)]" : "text-[var(--text-primary)]",
                        todo.state === "pending" && "text-[var(--text-secondary)]",
                      )}
                    >
                      {todo.label}
                    </span>
                    <span className="text-[10px] text-[var(--text-secondary)]">{todo.agent}</span>
                  </div>
                  <p className="text-[11px] text-[var(--text-secondary)] mt-0.5 leading-relaxed">
                    {todo.detail}
                  </p>
                  {live && todo.pause && run.bucket === "needs_attention" && (
                    <div className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5">
                      <p className="text-[11px] text-[var(--text-primary)] leading-relaxed">
                        {todo.pausePrompt}
                      </p>
                      <Button
                        size="sm"
                        className="h-7 text-xs mt-2 bg-primary text-primary-foreground hover:bg-primary/90"
                        onClick={onContinue}
                      >
                        <Play className="h-3 w-3 mr-1" />
                        Continue
                      </Button>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>

        {run.outcome && (
          <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] px-3 py-2.5">
            <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
              Outcome
            </p>
            <p className="text-xs text-[var(--text-primary)] mt-1">{run.outcome}</p>
            <p className="text-[10px] text-[var(--text-secondary)] mt-1">
              Auto-merge is false. Existing branch protection stays in charge.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export function bucketNeedsYou(bucket: RunBucket): boolean {
  return bucket === "needs_attention" || bucket === "ready_for_review";
}
