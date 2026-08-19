"use client";

import { useEffect, useMemo, useState } from "react";
import { Bell, Radio } from "lucide-react";
import { SectionRail, SectionRailButton } from "@/components/interface/shared/section-rail";
import type { ChangeActionId, RunProgress } from "./actions";
import { ChangesInbox } from "./changes-tab";
import { runKey, type ProjectChange } from "./data";
import { RunsPanel, bucketNeedsYou } from "./runs-panel";
import {
  advanceRun,
  createRun,
  continueRun,
  findRunFor,
  inboxProgressFor,
  seedRuns,
  type MockRun,
} from "./run-scripts";

type Section = "releases" | "runs";

function initialWorkspace(): { runs: MockRun[]; progress: Record<string, RunProgress> } {
  const runs = seedRuns();
  const progress: Record<string, RunProgress> = {};
  for (const run of runs) {
    progress[runKey({ id: run.changeId, repo: run.repo })] = inboxProgressFor(run.bucket);
  }
  return { runs, progress };
}

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
  const [boot] = useState(initialWorkspace);
  const [runs, setRuns] = useState<MockRun[]>(boot.runs);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(boot.runs[0]?.id ?? null);
  const [progress, setProgress] = useState<Record<string, RunProgress>>(boot.progress);

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
        next[runKey({ id: run.changeId, repo: run.repo })] = inboxProgressFor(run.bucket);
      }
      return next;
    });
  };

  const onCommitted = (change: ProjectChange, action: ChangeActionId) => {
    if (action === "dismiss" || action === "reopen") return;
    const existing = findRunFor(runs, change);
    if (existing) {
      setSelectedRunId(existing.id);
      setSection("runs");
      return;
    }
    const run = createRun(change, action, runs.length + 1);
    setRuns((prev) => [run, ...prev]);
    setSelectedRunId(run.id);
    setProgress((prev) => ({ ...prev, [runKey(change)]: "running" }));
    setSection("runs");
  };

  const onOpenRun = (change: ProjectChange) => {
    const key = runKey(change);
    const run = runs.find((item) => runKey({ id: item.changeId, repo: item.repo }) === key);
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
      <SectionRail>
        <SectionRailButton
          active={section === "releases"}
          icon={Bell}
          label="Releases"
          onClick={() => setSection("releases")}
        />
        <SectionRailButton
          active={section === "runs"}
          icon={Radio}
          label="Runs"
          count={activeCount > 0 ? (attention > 0 ? attention : activeCount) : undefined}
          onClick={() => setSection("runs")}
        />
      </SectionRail>

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
