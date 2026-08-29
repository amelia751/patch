"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { fetchRun, fetchRuns, isLive, pendingRun, startRemediation, toRun } from "./live-runs";
import { inboxProgressFor, type MockRun } from "./run-scripts";

type Section = "releases" | "runs";

/** How often the runs list is re-read while something is still moving.
 *
 * One second matches the remediator flush tick. Two seconds was enough to
 * miss a whole tool call between paints, which is how a live run looked idle.
 * When nothing is active the list still refreshes, just rarely, so a run
 * started from another tab appears without a reload.
 */
const LIVE_POLL_MS = 1000;
const IDLE_POLL_MS = 15000;

/** One shared empty array, so "no runs" is referentially stable across renders. */
const EMPTY_RUNS: MockRun[] = [];

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

/** Whether two polls describe the same runs, so an unchanged one renders nothing. */
function sameRuns(previous: MockRun[], next: MockRun[]): boolean {
  if (previous.length !== next.length) return false;
  return previous.every((run, index) => {
    const other = next[index];
    return (
      run.id === other.id &&
      run.machine === other.machine &&
      run.log.length === other.log.length &&
      (run.logSource?.trace.length ?? 0) === (other.logSource?.trace.length ?? 0) &&
      run.diffs.length === other.diffs.length &&
      run.commands.length === other.commands.length &&
      run.checks.length === other.checks.length &&
      run.attempt === other.attempt &&
      run.pauseReason === other.pauseReason &&
      run.prBranch === other.prBranch
    );
  });
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
  onGcpConnected,
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
  onGcpConnected?: () => void;
}) {
  const [section, setSection] = useState<Section>("releases");
  // Held with the project they belong to, so switching projects shows nothing
  // rather than the previous project's runs until the first poll lands.
  const [loaded, setLoaded] = useState<{ projectId: string; runs: MockRun[] }>({
    projectId: "",
    runs: [],
  });
  const runs = useMemo(
    () => (loaded.projectId === projectId ? loaded.runs : EMPTY_RUNS),
    [loaded, projectId],
  );
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [progress, setProgress] = useState<Record<string, RunProgress>>({});
  const [changes, setChanges] = useState<ProjectChange[]>([]);
  // Read by the run poll to title a run and draw its base tree. A ref rather
  // than a dependency: the two polls run on different clocks, and making the
  // run loop depend on the inbox would tear it down and rebuild it every time
  // an unrelated card moved.
  const changesRef = useRef<ProjectChange[]>([]);
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

  const loadChanges = useCallback(async (id: string, signal?: AbortSignal) => {
    const payload = await fetchProjectChanges(id);
    if (signal?.aborted) return payload;
    // The inbox re-polls on a timer and almost every response is identical.
    // Keeping the previous array when nothing moved means an unchanged poll
    // renders nothing at all, rather than remounting every card underneath the
    // reader.
    changesRef.current = payload.changes;
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

  const syncProgress = useCallback((list: MockRun[]) => {
    setProgress((prev) => {
      const next = { ...prev };
      for (const run of list) {
        next[runKey({ id: run.changeId, repo: run.repo })] = inboxProgressFor(run.bucket);
      }
      return next;
    });
  }, []);

  const loadRuns = useCallback(
    async (id: string, signal?: AbortSignal): Promise<boolean> => {
      const summaries = await fetchRuns(id);
      if (signal?.aborted) return false;
      // The list is a summary; the panel draws evidence. Reading each run's
      // detail is what fills the trees, the worklog and the checks — the whole
      // reason the panel exists — and a project has a handful of runs, not a
      // page of them.
      const details = await Promise.all(
        summaries.map((summary) =>
          fetchRun(id, summary.run_id).catch(() => null),
        ),
      );
      if (signal?.aborted) return false;
      const mapped = details
        .filter((detail): detail is NonNullable<typeof detail> => detail !== null)
        .map((detail, position) =>
          toRun(
            detail,
            position,
            changesRef.current.find(
              (change) => change.id === detail.change_id && change.repo === detail.repository,
            ),
          ),
        );
      setLoaded((prev) =>
        prev.projectId === id && sameRuns(prev.runs, mapped) ? prev : { projectId: id, runs: mapped },
      );
      syncProgress(mapped);
      setSelectedRunId((prev) => {
        if (prev && mapped.some((run) => run.id === prev)) return prev;
        return mapped[0]?.id ?? null;
      });
      return summaries.some((summary) => isLive(summary.state));
    },
    [syncProgress],
  );

  useEffect(() => {
    if (!hasProject || !projectId) return;
    const controller = new AbortController();
    let timer: number | undefined;

    const tick = async () => {
      let live = false;
      try {
        live = await loadRuns(projectId, controller.signal);
      } catch {
        // A failed poll is not a reason to stop polling; the next one may work.
      }
      if (controller.signal.aborted) return;
      timer = window.setTimeout(() => void tick(), live ? LIVE_POLL_MS : IDLE_POLL_MS);
    };

    void tick();
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [hasProject, loadRuns, projectId]);

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
    if (!projectId) return;
    setProgress((prev) => ({ ...prev, [runKey(change)]: "running" }));
    setSection("runs");
    // Draw the card's own inventory now. Opening the panel on a no-runs empty
    // state while the row is being created reads as "nothing found", which is
    // the opposite of what the join already knows.
    const placeholder = pendingRun(change, runs.length);
    setLoaded((prev) =>
      prev.projectId === projectId &&
      prev.runs.some((item) => runKey({ id: item.changeId, repo: item.repo }) === runKey(change))
        ? prev
        : { projectId, runs: [placeholder, ...(prev.projectId === projectId ? prev.runs : [])] },
    );
    setSelectedRunId((prev) => prev ?? placeholder.id);
    void startRemediation(projectId, change.id, change.repo)
      .then((started) => {
        setSelectedRunId(started.run_id);
        return loadRuns(projectId);
      })
      .catch(() => {
        setProgress((prev) => ({ ...prev, [runKey(change)]: "idle" }));
      });
  };

  const onOpenRun = (change: ProjectChange) => {
    const key = runKey(change);
    const run = runs.find((item) => runKey({ id: item.changeId, repo: item.repo }) === key);
    if (run) setSelectedRunId(run.id);
    setSection("runs");
  };

  // Continue dispatches a new execution of the same row. The API keeps the
  // worklog; the remediator loads the credentials just stored and, when a
  // diff already exists, skips a second patch loop.
  const onContinue = (id: string) => {
    const run = runs.find((item) => item.id === id);
    if (!projectId || !run) return;
    onGcpConnected?.();
    void startRemediation(projectId, run.changeId, run.repo)
      .then(() => loadRuns(projectId))
      .catch(() => undefined);
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
