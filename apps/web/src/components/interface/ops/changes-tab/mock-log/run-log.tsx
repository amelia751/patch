"use client";

/**
 * The run log, drawn as a run rather than as a transcript.
 *
 * Live runs pass `follow` so rows appear as the job writes them. The demo
 * fixtures omit `follow` and replay on the captured clock.
 *
 * What this replaces, for reference — six consecutive paragraphs, one weight,
 * source order, two of them nearly identical:
 *
 *   Dispatched to local-worker. Waiting for the remediator to claim this run.
 *   Remediator claimed patchapi-demo/storygen at e41d775ec28a. Fetching the pinned tree.
 *   Fetched patchapi-demo/storygen at e41d775ec28a.
 *   Allocating an isolated gke sandbox.
 *   Staged 20 files … This change has no local repository check; proof is a live resolve.
 *   This change has no local repository check; proof is the binding rewrite and a live provider resolve.
 *
 * The four things an IDE run view does that this did not:
 *
 * *Hierarchy.* A phase is a row you can collapse; its steps are indented under a
 * rail. Six setup sentences become one "Set up · 7.4s" line that opens.
 *
 * *Time.* Every row carries how long it took, right-aligned and tabular. The
 * trace always had the timestamps.
 *
 * *Density.* A step is a 22px row — icon, verb, one monospace detail, outcome —
 * not a paragraph. Prose is kept, but behind the row rather than as the row.
 *
 * *Repetition folded.* Six reads in a row is one "Read · 6 files" that opens,
 * which is the difference between skimming a run and scrolling one.
 */

import { useMemo, useState } from "react";
import {
  BadgeCheck,
  BookOpen,
  Boxes,
  Brain,
  ChevronRight,
  Compass,
  Eye,
  FileEdit,
  FolderSearch,
  GitBranch,
  GitPullRequest,
  KeyRound,
  Layers,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  ScanSearch,
  Send,
  ShieldCheck,
  SkipForward,
  Terminal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { DiffBlock } from "@/components/chat/code-block/diff-block";
import { TerminalBlock } from "@/components/chat/code-block/terminal-block";
import { buildTimeline, humanMs, type IconName, type Phase, type RunFixture, type Step, type StepTone } from "./timeline";
import { fixtureFor } from "./demo-runs";
import type { MockRun } from "../run-scripts";
import { useReplay, type Replay } from "./use-replay";

const ICONS: Record<IconName, React.ComponentType<{ className?: string }>> = {
  dispatch: Send,
  repo: GitBranch,
  sandbox: Boxes,
  normalize: Layers,
  scan: ScanSearch,
  policy: ShieldCheck,
  read: Eye,
  find: FolderSearch,
  edit: FileEdit,
  shell: Terminal,
  web: Compass,
  key: KeyRound,
  verify: BadgeCheck,
  pr: GitPullRequest,
  think: Brain,
  skill: BookOpen,
  eye: Eye,
};

/** Color for the icon itself. Outcome tones still win when a step failed or passed. */
const ICON: Record<IconName, string> = {
  dispatch: "text-sky-500",
  repo: "text-violet-500",
  sandbox: "text-orange-500",
  normalize: "text-cyan-500",
  scan: "text-sky-600",
  policy: "text-emerald-500",
  read: "text-blue-500",
  find: "text-indigo-500",
  edit: "text-violet-500",
  shell: "text-teal-500",
  web: "text-blue-500",
  key: "text-amber-500",
  verify: "text-emerald-500",
  pr: "text-emerald-600",
  think: "text-fuchsia-400",
  skill: "text-cyan-600",
  eye: "text-slate-500",
};

const TONE: Record<StepTone, string> = {
  neutral: "text-[var(--text-secondary)]",
  good: "text-emerald-500",
  warn: "text-amber-500",
  bad: "text-red-500",
  think: "text-[var(--text-tertiary)]",
};

const DOT: Record<StepTone, string> = {
  neutral: "bg-[var(--text-tertiary)]",
  good: "bg-emerald-500",
  warn: "bg-amber-500",
  bad: "bg-red-500",
  think: "bg-[var(--text-tertiary)]",
};

function Duration({ ms, className }: { ms: number; className?: string }) {
  return (
    <span
      className={cn(
        "shrink-0 tabular-nums text-[10.5px] text-[var(--text-tertiary)]/70",
        className,
      )}
    >
      {humanMs(ms)}
    </span>
  );
}

/** One step: icon, verb, detail, outcome, duration. Opens if it has more. */
function StepRow({ step, running }: { step: Step; running: boolean }) {
  const [open, setOpen] = useState(false);
  const Icon = ICONS[step.icon];
  const expandable = Boolean(step.folded || step.body);

  return (
    <div className="min-w-0">
      <div
        className={cn(
          "group flex items-center gap-2 rounded-[5px] py-[3px] pl-1 pr-1.5 -mx-1",
          expandable && "cursor-pointer hover:bg-[var(--bg-secondary)]",
        )}
        onClick={expandable ? () => setOpen(!open) : undefined}
      >
        {running ? (
          <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary" />
        ) : (
          <Icon
            className={cn(
              "h-3 w-3 shrink-0",
              step.tone === "neutral" || step.tone === "think" ? ICON[step.icon] : TONE[step.tone],
            )}
          />
        )}

        <span className="shrink-0 text-[12.5px] font-medium text-[var(--text-primary)]">
          {step.label}
        </span>

        {step.detail &&
          (step.icon === "think" || step.icon === "web" || step.icon === "key" || step.icon === "policy" || step.icon === "scan" || step.icon === "normalize" || step.icon === "skill" ? (
            <span className="min-w-0 truncate text-[11.5px] text-[var(--text-secondary)]">
              {step.detail}
            </span>
          ) : (
            <code className="min-w-0 truncate font-mono text-[11.5px] text-[var(--text-secondary)]">
              {step.detail}
            </code>
          ))}

        {step.outcome && (
          <span className={cn("shrink-0 text-[11px]", TONE[step.tone])}>{step.outcome}</span>
        )}

        {expandable && (
          <ChevronRight
            className={cn(
              "h-2.5 w-2.5 shrink-0 text-[var(--text-tertiary)] opacity-0 transition-all group-hover:opacity-100",
              open && "rotate-90 opacity-100",
            )}
          />
        )}

        <span className="ml-auto flex shrink-0 items-center">
          <Duration ms={step.durationMs} />
        </span>
      </div>

      {open && step.folded && (
        <div className="ml-[18px] mt-0.5 mb-1 flex flex-col gap-px border-l border-[var(--border-color)] pl-2.5">
          {step.folded.map((item, index) => (
            <span
              key={index}
              className="truncate text-[11.5px] text-[var(--text-secondary)]"
            >
              {item.detail}
            </span>
          ))}
        </div>
      )}

      {open && step.body && (
        <p className="ml-[18px] mt-1 mb-1.5 whitespace-pre-wrap border-l border-[var(--border-color)] pl-2.5 text-[11.5px] leading-relaxed text-[var(--text-tertiary)]">
          {step.body.length > 1200 ? `${step.body.slice(0, 1200)}…` : step.body}
        </p>
      )}

      {step.terminal && (
        <div className="ml-[18px] my-1.5">
          <TerminalBlock
            className="!my-0"
            code={step.terminal.replace(/^```terminal\n/, "").replace(/\n```$/, "")}
            onCopy={(code) => void navigator.clipboard.writeText(code)}
          />
        </div>
      )}

      {step.diff && (
        <div className="ml-[18px] my-1.5">
          <DiffBlock className="!my-0" code={step.diff.replace(/^```diff\n/, "").replace(/\n```$/, "")} />
        </div>
      )}
    </div>
  );
}

/** A phase: a collapsible header with its steps under a rail. */
function PhaseBlock({
  phase,
  elapsed,
  isLast,
  live = false,
}: {
  phase: Phase;
  elapsed: number;
  isLast: boolean;
  live?: boolean;
}) {
  const visible = phase.steps.filter((step) => step.at <= elapsed);
  const reached = elapsed >= phase.at;
  const finished = elapsed >= phase.at + phase.durationMs;
  const active = live || (reached && !finished);

  // Open while it is happening, then fall back to whatever the phase asked for.
  // Watching a run means watching the current phase; reviewing one means seeing
  // the shape, not every read.
  const [override, setOverride] = useState<boolean | null>(null);
  const open = override ?? (active ? true : !phase.collapsed);

  if (!reached) return null;

  const running = live || (active && isLast);

  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={() => setOverride(!open)}
        className="group flex w-full min-w-0 items-center gap-2 rounded-[5px] py-1 pl-0.5 pr-1.5 -mx-0.5 text-left hover:bg-[var(--bg-secondary)]"
      >
        <span className="relative flex h-3 w-3 shrink-0 items-center justify-center">
          {running ? (
            <Loader2 className="h-3 w-3 animate-spin text-primary" />
          ) : (
            <span className={cn("h-[7px] w-[7px] rounded-full", DOT[phase.tone])} />
          )}
        </span>

        <span className="shrink-0 text-[12.5px] font-semibold text-[var(--text-primary)]">
          {phase.title}
        </span>

        {phase.summary && (
          <span className="min-w-0 truncate text-[11.5px] text-[var(--text-tertiary)]">
            {phase.summary}
          </span>
        )}

        <ChevronRight
          className={cn(
            "h-2.5 w-2.5 shrink-0 text-[var(--text-tertiary)] transition-transform",
            open && "rotate-90",
          )}
        />

        <span className="ml-auto flex shrink-0 items-center gap-2">
          {!open && (
            <span className="tabular-nums text-[10.5px] text-[var(--text-tertiary)]/60">
              {phase.steps.length} step{phase.steps.length === 1 ? "" : "s"}
            </span>
          )}
          <Duration ms={finished ? phase.durationMs : Math.max(0, elapsed - phase.at)} />
        </span>
      </button>

      {open && (
        <div
          className={cn(
            "ml-[5.5px] flex flex-col gap-px pl-[11px]",
            !isLast && "border-l border-[var(--border-color)]",
            isLast && "border-l border-transparent",
          )}
        >
          {visible.map((step, index) => (
            <StepRow
              key={step.id}
              step={step}
              running={running && index === visible.length - 1}
            />
          ))}
        </div>
      )}

    </div>
  );
}

function Controls({ replay }: { replay: Replay }) {
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={replay.playing ? replay.pause : replay.done ? replay.restart : replay.play}
        title={replay.playing ? "Pause" : replay.done ? "Replay" : "Play"}
        className="flex h-6 w-6 items-center justify-center rounded-[5px] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
      >
        {replay.done ? (
          <RotateCcw className="h-3 w-3" />
        ) : replay.playing ? (
          <Pause className="h-3 w-3" />
        ) : (
          <Play className="h-3 w-3" />
        )}
      </button>
      <button
        type="button"
        onClick={replay.skip}
        title="Skip to the end"
        disabled={replay.done}
        className="flex h-6 w-6 items-center justify-center rounded-[5px] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] disabled:opacity-30"
      >
        <SkipForward className="h-3 w-3" />
      </button>
      <div className="ml-1 flex items-center rounded-[5px] bg-[var(--bg-tertiary)] p-0.5">
        {[4, 12, 40].map((rate) => (
          <button
            key={rate}
            type="button"
            onClick={() => replay.setSpeed(rate)}
            className={cn(
              "rounded-[3px] px-1.5 py-[1px] text-[10px] tabular-nums transition-colors",
              replay.speed === rate
                ? "bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm"
                : "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]",
            )}
          >
            {rate}×
          </button>
        ))}
      </div>
    </div>
  );
}

export function RunLog({
  fixture,
  follow = false,
  live = false,
}: {
  fixture: RunFixture;
  /** Show every row that exists so far. A live run grows; it is not replayed. */
  follow?: boolean;
  live?: boolean;
}) {
  const timeline = useMemo(() => buildTimeline(fixture), [fixture]);
  const beats = useMemo(
    () => timeline.phases.flatMap((phase) => phase.steps.map((step) => step.at)),
    [timeline],
  );
  const replay = useReplay(follow ? 0 : timeline.totalMs, follow ? [] : beats);
  const elapsed = follow ? timeline.totalMs : replay.elapsed;
  const done = follow ? !live : replay.done;

  const shown = timeline.phases.filter((phase) => phase.at <= elapsed);
  const stepsShown = shown.reduce(
    (sum, phase) => sum + phase.steps.filter((step) => step.at <= elapsed).length,
    0,
  );

  return (
    <section>
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <h3 className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
          Log
        </h3>
        <span className="tabular-nums text-[11px] text-[var(--text-tertiary)]">
          {follow ? `${timeline.steps} steps` : `${stepsShown}/${timeline.steps}`}
        </span>
        <span className="tabular-nums text-[11px] text-[var(--text-secondary)]">
          {humanMs(elapsed)}
          {!follow && (
            <span className="text-[var(--text-tertiary)]/60"> / {humanMs(timeline.totalMs)}</span>
          )}
        </span>
        {!follow && (
          <div className="ml-auto">
            <Controls replay={replay} />
          </div>
        )}
        {!follow && (
          <div className="h-[2px] w-full overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-100 ease-linear"
              style={{ width: `${replay.progress * 100}%` }}
            />
          </div>
        )}
      </header>

      <div className="mt-2 flex min-w-0 flex-col gap-1">
        {shown.map((phase, index) => (
          <PhaseBlock
            key={phase.id}
            phase={phase}
            elapsed={elapsed}
            isLast={index === shown.length - 1}
            live={live && index === shown.length - 1}
          />
        ))}
      </div>

      {done && timeline.prNumber != null && (
        <footer className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-[var(--border-color)] pt-2 text-[11px]">
          <span className="flex items-center gap-1.5 text-emerald-500">
            <GitPullRequest className="h-3 w-3" />
            #{timeline.prNumber} opened
          </span>
          {timeline.verdict && (
            <span className="text-[var(--text-secondary)]">
              verification <span className="text-emerald-500">{timeline.verdict}</span>
            </span>
          )}
          <span className="ml-auto tabular-nums text-[var(--text-tertiary)]/70">
            {humanMs(timeline.totalMs)} · {timeline.steps} steps
          </span>
        </footer>
      )}
    </section>
  );
}

export function DemoLog({ run }: { run: MockRun }) {
  const fixture = fixtureFor(run);
  if (!fixture) return null;
  return <RunLog fixture={fixture} />;
}
