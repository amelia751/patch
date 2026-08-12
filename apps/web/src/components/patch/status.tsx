import { cn } from "@/lib/utils";
import {
  TONE_CLASSES,
  TONE_DOT_CLASSES,
  type Tone,
  humanizeState,
  isActive,
  runStateTone,
} from "@/lib/run-state";
import type { RunState } from "@/lib/api/types";

/** A small labelled pill. The tone carries the meaning; the label carries the fact. */
export function StatusPill({
  tone,
  label,
  className,
}: {
  tone: Tone;
  label: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        TONE_CLASSES[tone],
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", TONE_DOT_CLASSES[tone])} />
      {label}
    </span>
  );
}

/**
 * A run's current state. Live runs pulse; ended runs do not — so a stalled run
 * is visibly different from one that is still moving.
 */
export function RunStateBadge({ state, className }: { state: RunState; className?: string }) {
  const tone = runStateTone(state);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        TONE_CLASSES[tone],
        className,
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          TONE_DOT_CLASSES[tone],
          isActive(state) && "animate-pulse-ring",
        )}
      />
      {humanizeState(state)}
    </span>
  );
}

/** A labelled figure. `hint` explains what the number is evidence of. */
export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: Tone;
}) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 text-2xl font-semibold tnum",
          tone === "fail" && "text-state-fail",
          tone === "pass" && "text-state-pass",
          tone === "human" && "text-state-human",
        )}
      >
        {value}
      </div>
      {hint ? <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

/** Monospace value with a label above it — SHAs, trace ids, model names. */
export function Field({
  label,
  value,
  mono = false,
  className,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className={cn("mt-1 truncate text-sm", mono && "font-mono tnum text-[13px]")}>
        {value}
      </div>
    </div>
  );
}
