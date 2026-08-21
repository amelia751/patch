"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Preview switch: forces the sign on regardless of indexer state so the design
 * can be reviewed without a running indexer. Live state now drives the banner,
 * so this stays off.
 */
export const FORCE_SHOW_CODEBASE_INDEXING = false;

/** Rollup returned by `GET /api/projects/{id}/indexing` (schema.md §13). */
export type IndexingStatus = "indexing" | "ready" | "idle" | "error";

export interface IndexingRepository {
  full_name: string;
  branch: string;
  status: IndexingStatus;
  progress_percent: number;
}

export interface ProjectIndexingState {
  status: IndexingStatus;
  progress_percent: number;
  repositories: IndexingRepository[];
}

function indexingLabel(repositories: IndexingRepository[] | undefined): string {
  const inFlight = (repositories ?? []).filter(
    (repo) => repo.full_name && (repo.status === "indexing" || repo.status === "idle"),
  );
  const names = inFlight.map((repo) => repo.full_name).filter(Boolean);
  if (names.length === 0) return "Indexing codebase";
  if (names.length === 1) return `Indexing ${names[0]} codebase`;
  if (names.length === 2) return `Indexing ${names[0]}, ${names[1]} codebase`;
  return `Indexing ${names[0]} +${names.length - 1} codebase`;
}

/** The bar is for a real pass or a queued first index — not a tree fetch. */
export function indexingSignVisible(
  indexing?: ProjectIndexingState | null,
  force = false,
): boolean {
  if (force || FORCE_SHOW_CODEBASE_INDEXING) return true;
  if (!indexing) return false;
  if (indexing.status === "indexing") return true;
  if (indexing.status !== "idle") return false;
  return indexing.repositories.some((repo) => repo.status === "idle");
}

export function CodebaseIndexingSign({
  className,
  progress,
  label,
}: {
  className?: string;
  /** 0–100. Omit for the preview loop. */
  progress?: number;
  label?: string;
}) {
  const [previewProgress, setPreviewProgress] = useState(18);
  const value = progress ?? previewProgress;
  const text = label?.trim() || "Indexing codebase";

  useEffect(() => {
    if (progress != null) return;
    const id = window.setInterval(() => {
      setPreviewProgress((current) => (current >= 97 ? 8 : current + 1));
    }, 120);
    return () => window.clearInterval(id);
  }, [progress]);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`${text}, ${value}%`}
      className={cn(
        "shrink-0 border-b border-primary/20 bg-primary/[0.06]",
        className
      )}
    >
      <div className="flex items-center gap-2 px-4 py-1.5">
        <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary" aria-hidden />
        <p className="min-w-0 flex-1 truncate text-[11px] font-medium text-[var(--text-primary)]">
          {text}
        </p>
        <span className="text-[11px] tabular-nums text-primary/80">{value}%</span>
      </div>
      <div className="h-[2px] bg-primary/15">
        <div
          className="h-full bg-primary transition-[width] duration-150 ease-linear"
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Wraps a Codebase tab body with the indexing sign.
 *
 * Show it only for an in-flight pass, or for imported targets that are still
 * `idle` (queued, worker has not flipped the row). A ready project, an error,
 * a missing read (`null`), and a GitHub tree fetch must not draw the bar —
 * those used to flash 0% over a codebase that was already indexed.
 */
export function withCodebaseIndexingSign(
  body: ReactNode,
  indexing?: ProjectIndexingState | null,
  force = false
) {
  if (!indexingSignVisible(indexing, force)) {
    return body;
  }
  const progress =
    indexing?.status === "indexing" ? indexing.progress_percent : 0;
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[var(--bg-primary)]">
      <CodebaseIndexingSign
        progress={progress}
        label={indexingLabel(indexing?.repositories)}
      />
      <div className="min-h-0 flex-1 overflow-hidden">{body}</div>
    </div>
  );
}
