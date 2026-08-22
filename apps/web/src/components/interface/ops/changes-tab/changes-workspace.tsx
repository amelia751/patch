"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bell, Radio, ScanSearch } from "lucide-react";
import { SectionRail, SectionRailButton } from "@/components/interface/shared/section-rail";
import { Spinner } from "@/components/ui/spinner";
import type { ChangeActionId, RunProgress } from "./actions";
import { ChangesInbox } from "./changes-tab";
import { ReleasesLoadingState } from "./empty-states";
import type { SecretRepoOption, SecretWorkspaceOption } from "@/components/interface/secret-managers";
import { dismissProjectChange, fetchProjectChanges, reopenProjectChange } from "./api";
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

/** Whether two poll responses describe the same inbox.
 *
 * Compared as JSON because the payload is plain data from the API and any
 * difference in it is a difference worth re-rendering for. Cheap at inbox
 * sizes, and far cheaper than the remount it avoids.
 */
function sameChanges(previous: ProjectChange[], next: ProjectChange[]): boolean {
  if (previous.length !== next.length) return false;
  return JSON.stringify(previous) === JSON.stringify(next);
}

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
  userId,
  workspaces = [],
  repos = [],
  secretsPreviewMode = false,
  inboxTick = 0,
  assumeSubscribed = false,
}: {
  hasProject?: boolean;
  projectId?: string;
  onBrowseSubscriptions?: () => void;
  userId?: string;
  workspaces?: SecretWorkspaceOption[];
  repos?: SecretRepoOption[];
  secretsPreviewMode?: boolean;
  inboxTick?: number;
  assumeSubscribed?: boolean;
}) {
  const [section, setSection] = useState<Section>("releases");
  const [boot] = useState(initialWorkspace);
  const [runs, setRuns] = useState<MockRun[]>(boot.runs);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(boot.runs[0]?.id ?? null);
  const [progress, setProgress] = useState<Record<string, RunProgress>>(boot.progress);
  const [changes, setChanges] = useState<ProjectChange[]>([]);
  const [subscribed, setSubscribed] = useState(assumeSubscribed);
  const [inboxLoading, setInboxLoading] = useState(Boolean(hasProject && projectId));
  const [scanning, setScanning] = useState(false);
  const [scanPct, setScanPct] = useState(0);

  const attention = useMemo(
    () => runs.filter((run) => bucketNeedsYou(run.bucket)).length,
    [runs],
  );
  const activeCount = useMemo(
    () => runs.filter((run) => run.bucket === "active" || run.bucket === "needs_attention").length,
    [runs],
  );

  const hasActive = runs.some((run) => run.bucket === "active");

  const loadChanges = useCallback(async (id: string, signal?: AbortSignal) => {
    const payload = await fetchProjectChanges(id);
    if (signal?.aborted) return payload;
    // The inbox re-polls on a timer and almost every response is identical.
    // Keeping the previous array when nothing moved means an unchanged poll
    // renders nothing at all, rather than remounting every card underneath the
    // reader.
    setChanges((prev) => (sameChanges(prev, payload.changes) ? prev : payload.changes));
    setSubscribed(payload.subscribed);
    const scanningNow = payload.subscribed && payload.scan.status === "scanning";
    setScanning(scanningNow);
    setScanPct(payload.scan.progress_percent);
    return payload;
  }, []);

  useEffect(() => {
    if (!hasProject || !projectId) {
      setChanges([]);
      setSubscribed(false);
      setScanning(false);
      setInboxLoading(false);
      return;
    }
    if (assumeSubscribed) {
      setSubscribed(true);
    }
    setInboxLoading(true);
    const controller = new AbortController();
    let timer: number | undefined;

    const tick = async (intervalMs: number) => {
      try {
        const payload = await loadChanges(projectId, controller.signal);
        if (controller.signal.aborted) return;
        setInboxLoading(false);
        const next = payload.subscribed && payload.scan.status === "scanning" ? 1500 : 5000;
        timer = window.setTimeout(() => {
          void tick(next);
        }, intervalMs);
      } catch {
        if (controller.signal.aborted) return;
        setInboxLoading(false);
        timer = window.setTimeout(() => {
          void tick(4000);
        }, 4000);
      }
    };

    void tick(1500);
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [assumeSubscribed, hasProject, inboxTick, loadChanges, projectId]);

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
    if (action === "dismiss" || action === "reopen") {
      if (projectId) {
        const request = action === "dismiss" ? dismissProjectChange : reopenProjectChange;
        void request(projectId, change.id)
          .then(() => loadChanges(projectId))
          .catch(() => undefined);
      }
      return;
    }
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
        {inboxLoading && changes.length === 0 ? (
          <ReleasesLoadingState />
        ) : scanning ? (
          <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
            <div className="w-full max-w-sm px-6 text-center">
              <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-full border border-[var(--border-color)] bg-[var(--bg-secondary)]">
                <ScanSearch className="h-5 w-5 text-primary" />
              </div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Scanning your codebase
              </p>
              <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
                Matching Google Cloud releases against imported repositories
              </p>
              <div className="mt-5 h-1 overflow-hidden rounded-full bg-[var(--bg-secondary)]">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${scanPct}%` }}
                />
              </div>
              <div className="mt-3 flex items-center justify-center gap-1.5 text-[11px] text-[var(--text-secondary)]">
                <Spinner className="h-3 w-3" />
                {Math.round(scanPct)}%
              </div>
            </div>
          </div>
        ) : section === "releases" ? (
          <ChangesInbox
            hasProject={hasProject}
            projectId={projectId}
            changes={changes}
            subscribed={subscribed}
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
            projectId={projectId}
            userId={userId}
            workspaces={workspaces}
            repos={repos}
            secretsPreviewMode={secretsPreviewMode}
          />
        )}
      </div>
    </div>
  );
}
