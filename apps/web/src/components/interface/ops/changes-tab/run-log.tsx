"use client";

/**
 * The run log: phases, not a transcript of every sentence the job wrote.
 */

import { useMemo, useState, type ComponentType } from "react";
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
  ScanSearch,
  Send,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { DiffBlock } from "@/components/chat/code-block/diff-block";
import { TerminalBlock } from "@/components/chat/code-block/terminal-block";
import {
  buildTimeline,
  type IconName,
  type Phase,
  type RunFixture,
  type Step,
  type StepTone,
} from "./run-timeline";

const ICONS: Record<IconName, ComponentType<{ className?: string }>> = {
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

const PROSE_ICONS = new Set<IconName>([
  "think",
  "web",
  "key",
  "policy",
  "scan",
  "normalize",
  "skill",
]);

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
          (PROSE_ICONS.has(step.icon) ? (
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
      </div>

      {open && step.folded && (
        <div className="ml-[18px] mt-0.5 mb-1 flex flex-col gap-px border-l border-[var(--border-color)] pl-2.5">
          {step.folded.map((item, index) => (
            <span key={index} className="truncate text-[11.5px] text-[var(--text-secondary)]">
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

function PhaseBlock({
  phase,
  isLast,
  live = false,
}: {
  phase: Phase;
  isLast: boolean;
  live?: boolean;
}) {
  const [override, setOverride] = useState<boolean | null>(null);
  const open = override ?? (live ? true : !phase.collapsed);

  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={() => setOverride(!open)}
        className="group flex w-full min-w-0 items-center gap-2 rounded-[5px] py-1 pl-0.5 pr-1.5 -mx-0.5 text-left hover:bg-[var(--bg-secondary)]"
      >
        <span className="relative flex h-3 w-3 shrink-0 items-center justify-center">
          {live ? (
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
      </button>

      {open && (
        <div
          className={cn(
            "ml-[5.5px] flex flex-col gap-px pl-[11px]",
            isLast ? "border-l border-transparent" : "border-l border-[var(--border-color)]",
          )}
        >
          {phase.steps.map((step, index) => (
            <StepRow
              key={step.id}
              step={step}
              running={live && index === phase.steps.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function RunLog({ source, live = false }: { source: RunFixture; live?: boolean }) {
  const timeline = useMemo(() => buildTimeline(source), [source]);

  return (
    <section>
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <h3 className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
          Log
        </h3>
      </header>

      <div className="mt-2 flex min-w-0 flex-col gap-1">
        {timeline.phases.map((phase, index) => (
          <PhaseBlock
            key={phase.id}
            phase={phase}
            isLast={index === timeline.phases.length - 1}
            live={live && index === timeline.phases.length - 1}
          />
        ))}
      </div>

      {timeline.prNumber != null && !live && (
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
        </footer>
      )}
    </section>
  );
}
