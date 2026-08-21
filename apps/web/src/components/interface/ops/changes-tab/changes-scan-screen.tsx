"use client";

import { ScanSearch } from "lucide-react";
import { cn } from "@/lib/utils";

const PATHS = [
  "lib/gemini.ts",
  "app/api/story/route.ts",
  "generate.py",
  "src/services/image.ts",
  "src/clients/vertex.ts",
];

function phaseCopy(progress: number): string {
  if (progress < 28) return "Walking the repository tree";
  if (progress < 72) return "Looking for relevant Google Cloud usage";
  return "Matching identifiers to call sites";
}

export function ChangesScanScreen({ progress }: { progress: number }) {
  const pct = Math.min(100, Math.max(0, progress));
  const active = Math.min(PATHS.length - 1, Math.floor((pct / 100) * PATHS.length));
  const phase = phaseCopy(pct);

  return (
    <div className="relative h-full overflow-hidden bg-[var(--bg-primary)]">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 70% 50% at 50% 38%, hsl(var(--primary) / 0.14), transparent 62%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.35] dark:opacity-20"
        style={{
          backgroundImage:
            "linear-gradient(var(--border-color) 1px, transparent 1px), linear-gradient(90deg, var(--border-color) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          maskImage: "radial-gradient(ellipse 55% 45% at 50% 40%, black, transparent)",
        }}
      />

      <div className="relative flex h-full flex-col items-center justify-center px-6">
        <div className="relative mb-8 h-40 w-40">
          <div className="absolute inset-0 rounded-full bg-primary/10 blur-2xl" />
          <div className="absolute inset-0 rounded-full border border-primary/25" />
          <div className="absolute inset-4 rounded-full border border-primary/15" />
          <div className="absolute inset-8 rounded-full border border-primary/10" />
          <div
            aria-hidden
            className="absolute left-1/2 top-2 bottom-2 w-px -translate-x-1/2 bg-primary/10"
          />
          <div
            aria-hidden
            className="absolute top-1/2 left-2 right-2 h-px -translate-y-1/2 bg-primary/10"
          />
          <div
            aria-hidden
            className="absolute inset-0 rounded-full animate-[spin_3.4s_linear_infinite]"
            style={{
              background:
                "conic-gradient(from 0deg, transparent 0deg, hsl(var(--primary) / 0.38) 42deg, transparent 78deg)",
            }}
          />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full border border-primary/30 bg-[var(--bg-primary)]/80 shadow-[0_0_24px_hsl(var(--primary)/0.22)] backdrop-blur-sm">
              <ScanSearch className="h-5 w-5 text-primary" strokeWidth={1.75} />
            </div>
          </div>
        </div>

        <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-primary/80">
          Inventory
        </p>
        <h2 className="mt-2 text-xl font-semibold tracking-tight text-[var(--text-primary)]">
          Scanning your codebase
        </h2>
        <p className="mt-1.5 text-xs text-[var(--text-secondary)]">{phase}</p>

        <ul className="mt-7 w-full max-w-[20rem] font-mono text-[11px] leading-6">
          {PATHS.map((path, index) => {
            const state =
              index < active ? "done" : index === active ? "live" : "wait";
            return (
              <li
                key={path}
                className={cn(
                  "flex items-center gap-2.5 truncate transition-colors duration-300",
                  state === "live" && "text-[var(--text-primary)]",
                  state === "done" && "text-[var(--text-secondary)]",
                  state === "wait" && "text-[var(--text-tertiary)]/70",
                )}
              >
                <span
                  className={cn(
                    "h-1 w-1 shrink-0 rounded-full",
                    state === "live" && "bg-primary shadow-[0_0_8px_hsl(var(--primary)/0.8)]",
                    state === "done" && "bg-primary/40",
                    state === "wait" && "bg-[var(--border-color)]",
                  )}
                />
                {path}
              </li>
            );
          })}
        </ul>

        <div className="mt-8 w-full max-w-[20rem]">
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-[28px] font-light tabular-nums leading-none tracking-tight text-[var(--text-primary)]">
              {Math.round(pct)}
              <span className="ml-0.5 text-sm text-[var(--text-secondary)]">%</span>
            </span>
            <span className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              {pct >= 100 ? "Done" : "In progress"}
            </span>
          </div>
          <div className="h-[2px] overflow-hidden rounded-full bg-[var(--border-color)]">
            <div
              className="h-full rounded-full bg-primary shadow-[0_0_10px_hsl(var(--primary)/0.55)] transition-[width] duration-150 ease-linear"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
