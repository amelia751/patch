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

export function CodebaseIndexingSign({
  className,
  progress,
}: {
  className?: string;
  /** 0–100. Omit for the preview loop. */
  progress?: number;
}) {
  const [previewProgress, setPreviewProgress] = useState(18);
  const value = progress ?? previewProgress;

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
      aria-label={`Indexing codebase, ${value}%`}
      className={cn(
        "shrink-0 border-b border-primary/20 bg-primary/[0.06]",
        className
      )}
    >
      <div className="flex items-center gap-2 px-4 py-1.5">
        <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary" aria-hidden />
        <p className="min-w-0 flex-1 text-[11px] font-medium text-[var(--text-primary)]">
          Indexing codebase
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
 * Wraps a Codebase tab body with the indexing sign. `indexing` is the live
 * rollup; anything other than an in-flight index (including a missing or
 * unavailable endpoint, which arrives here as `null`) renders the body alone.
 */
export function withCodebaseIndexingSign(
  body: ReactNode,
  indexing?: ProjectIndexingState | null
) {
  const isIndexing = indexing?.status === "indexing";
  if (!isIndexing && !FORCE_SHOW_CODEBASE_INDEXING) {
    return body;
  }
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[var(--bg-primary)]">
      <CodebaseIndexingSign progress={isIndexing ? indexing!.progress_percent : undefined} />
      <div className="min-h-0 flex-1 overflow-hidden">{body}</div>
    </div>
  );
}
