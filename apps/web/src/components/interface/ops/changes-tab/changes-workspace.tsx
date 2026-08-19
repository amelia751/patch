"use client";

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Bell, Radio } from "lucide-react";
import type { ChangeActionId, RunProgress } from "./actions";
import { ChangesInbox } from "./changes-tab";
import type { ProjectChange } from "./data";
import { RunsPanel, bucketNeedsYou } from "./runs-panel";
import {
  advanceRun,
  createRun,
  continueRun,
  inboxProgressFor,
  type MockRun,
} from "./run-scripts";

type Section = "releases" | "runs";

export function ChangesTab({
  hasProject = true,
  projectId,
  onBrowseSubscriptions,
}: {
  hasProject?: boolean;
  projectId?: string;
  onBrowseSubscriptions?: () => void;
}) {
  const [section, setSection] = useState<Section>("releases");
  const [runs, setRuns] = useState<MockRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [progress, setProgress] = useState<Record<string, RunProgress>>({});

  const attention = useMemo(
    () => runs.filter((run) => bucketNeedsYou(run.bucket)).length,
    [runs],
  );
  const activeCount = useMemo(
    () => runs.filter((run) => run.bucket === "active" || run.bucket === "needs_attention").length,
    [runs],
  );

  const hasActive = runs.some((run) => run.bucket === "active");

  useEffect(() => {
    if (!hasActive) return;
    const timer = window.setInterval(() => {
      setRuns((prev) => {
        const next = prev.map((run) => (run.bucket === "active" ? advanceRun(run) : run));
        syncProgress(next);
        return next;
      });
    }, 480);
    return () => window.clearInterval(timer);
  }, [hasActive]);

  const syncProgress = (list: MockRun[]) => {
    setProgress((prev) => {
      const next = { ...prev };
      for (const run of list) {
        next[run.changeId] = inboxProgressFor(run.bucket);
      }
      return next;
    });
  };

  const onCommitted = (change: ProjectChange, action: ChangeActionId) => {
    if (action === "dismiss" || action === "reopen") return;
    const run = createRun(change, action, runs.length + 1);
    setRuns((prev) => [run, ...prev]);
    setSelectedRunId(run.id);
    setProgress((prev) => ({ ...prev, [change.id]: "running" }));
    setSection("runs");
  };

  const onOpenRun = (changeId: string) => {
    const run = runs.find((item) => item.changeId === changeId);
    if (run) setSelectedRunId(run.id);
    setSection("runs");
  };

  const onContinue = (id: string) => {
    setRuns((prev) => {
      const next = prev.map((run) => (run.id === id ? continueRun(run) : run));
      syncProgress(next);
      return next;
    });
  };

  return (
    <div className="h-full flex min-w-0 overflow-hidden bg-[var(--bg-primary)]">
      <div className="w-56 flex-shrink-0 border-r border-[var(--border-color)] p-3 space-y-1">
        <button
          type="button"
          onClick={() => setSection("releases")}
          className={cn(
            "w-full flex items-center justify-between px-3 py-2 text-xs rounded-lg transition-colors",
            section === "releases"
              ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]",
          )}
        >
          <div className="flex items-center gap-2">
            <Bell className="h-4 w-4" />
            <span className="font-medium">Releases</span>
          </div>
        </button>
        <button
          type="button"
          onClick={() => setSection("runs")}
          className={cn(
            "w-full flex items-center justify-between px-3 py-2 text-xs rounded-lg transition-colors",
            section === "runs"
              ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]",
          )}
        >
          <div className="flex items-center gap-2">
            <Radio className="h-4 w-4" />
            <span className="font-medium">Runs</span>
          </div>
          {activeCount > 0 && (
            <Badge
              variant="outline"
              className="text-[9px] h-5 bg-amber-500/10 text-amber-500 border-amber-500/30"
            >
              {attention > 0 ? attention : activeCount}
            </Badge>
          )}
        </button>
      </div>

      <div className="flex-1 min-w-0 overflow-hidden">
        {section === "releases" ? (
          <ChangesInbox
            hasProject={hasProject}
            projectId={projectId}
            onBrowseSubscriptions={onBrowseSubscriptions}
            progress={progress}
            onCommitted={onCommitted}
            onOpenRun={onOpenRun}
          />
        ) : (
          <RunsPanel
            runs={runs}
            selectedId={selectedRunId}
            onSelect={setSelectedRunId}
            onContinue={onContinue}
          />
        )}
      </div>
    </div>
  );
}
