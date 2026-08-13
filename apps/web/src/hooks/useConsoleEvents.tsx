"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";
import { useProject } from "@/lib/project-context";
import type {
  IndexingStatus,
  ProjectIndexingState,
} from "@/components/interface/ops/codebase-tab/codebase-indexing-sign";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Fallback only: the live path is EventSource `/events`. */
export const INDEXING_POLL_MS = 1500;
export const NOTIFICATIONS_POLL_MS = 30000;

const INDEXING_STATUSES: readonly IndexingStatus[] = [
  "indexing",
  "ready",
  "idle",
  "error",
];

export interface ConsoleNotification {
  id: string;
  project_id?: string;
  type: "success" | "pending" | "question" | "info" | "error";
  title: string;
  message: string;
  timestamp: string;
  priority: string;
  read: boolean;
  dismissed: boolean;
  details?: { label: string; items: string[] } | null;
  questions?: { question: string; options: string[] } | null;
  actions?: Array<{
    label: string;
    action_type: string;
    variant: "default" | "outline" | "ghost";
    data?: Record<string, unknown>;
  }>;
  contract_ids?: string[];
  source_commit?: string;
  metadata?: Record<string, unknown>;
}

export interface ConsoleEventsState {
  projectId: string | null;
  indexing: ProjectIndexingState | null;
  notifications: ConsoleNotification[] | null;
  live: boolean;
}

const EMPTY_STATE: ConsoleEventsState = {
  projectId: null,
  indexing: null,
  notifications: null,
  live: false,
};

const ConsoleEventsContext = createContext<ConsoleEventsState>(EMPTY_STATE);

function clampPercent(value: unknown): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.round(Math.min(100, Math.max(0, n)));
}

function normalizeIndexingState(payload: unknown): ProjectIndexingState {
  const raw = (payload ?? {}) as Partial<ProjectIndexingState>;
  const status = INDEXING_STATUSES.includes(raw.status as IndexingStatus)
    ? (raw.status as IndexingStatus)
    : "idle";
  const repositories = Array.isArray(raw.repositories) ? raw.repositories : [];
  return {
    status,
    progress_percent: clampPercent(raw.progress_percent),
    repositories: repositories.map((repo) => ({
      full_name: String(repo?.full_name ?? ""),
      branch: String(repo?.branch ?? ""),
      status: INDEXING_STATUSES.includes(repo?.status as IndexingStatus)
        ? (repo.status as IndexingStatus)
        : "idle",
      progress_percent: clampPercent(repo?.progress_percent),
    })),
  };
}

function asNotificationList(payload: unknown): ConsoleNotification[] {
  if (Array.isArray(payload)) {
    return payload as ConsoleNotification[];
  }
  if (payload && typeof payload === "object" && "notifications" in payload) {
    const items = (payload as { notifications?: unknown }).notifications;
    return Array.isArray(items) ? (items as ConsoleNotification[]) : [];
  }
  return [];
}

async function fetchIndexing(
  projectId: string,
  signal: AbortSignal
): Promise<ProjectIndexingState | null> {
  const resp = await fetch(`${API_URL}/api/projects/${projectId}/indexing`, {
    credentials: "include",
    cache: "no-store",
    signal,
  });
  if (!resp.ok) return null;
  return normalizeIndexingState(await resp.json());
}

async function fetchNotifications(
  projectId: string,
  signal: AbortSignal
): Promise<ConsoleNotification[] | null> {
  const resp = await fetch(
    `${API_URL}/api/notifications?project_id=${projectId}&limit=20`,
    { credentials: "include", cache: "no-store", signal }
  );
  if (!resp.ok) return null;
  return asNotificationList(await resp.json());
}

/**
 * One project console stream: snapshot on connect, push events after that.
 * Polls `/indexing` and `/notifications` only while the EventSource is down.
 */
export function useConsoleEventsStream(
  projectId: string | null,
  enabled: boolean
): ConsoleEventsState {
  const [state, setState] = useState<ConsoleEventsState>(EMPTY_STATE);

  useEffect(() => {
    if (!enabled || !projectId) {
      setState(EMPTY_STATE);
      return;
    }

    const abort = new AbortController();
    const { signal } = abort;
    let source: EventSource | null = null;
    let indexingTimer: number | undefined;
    let notificationTimer: number | undefined;
    let polling = false;

    const stopPoll = () => {
      polling = false;
      if (indexingTimer !== undefined) window.clearInterval(indexingTimer);
      if (notificationTimer !== undefined) window.clearInterval(notificationTimer);
      indexingTimer = undefined;
      notificationTimer = undefined;
    };

    const applyIndexing = (payload: unknown) => {
      if (signal.aborted) return;
      setState((current) => ({
        ...current,
        projectId,
        indexing: normalizeIndexingState(payload),
      }));
    };

    const applyNotifications = (payload: unknown) => {
      if (signal.aborted) return;
      setState((current) => ({
        ...current,
        projectId,
        notifications: asNotificationList(payload),
      }));
    };

    const pollOnce = async () => {
      try {
        const [indexing, notifications] = await Promise.all([
          fetchIndexing(projectId, signal),
          fetchNotifications(projectId, signal),
        ]);
        if (signal.aborted) return;
        setState((current) => ({
          projectId,
          live: current.live,
          indexing,
          notifications: notifications ?? current.notifications,
        }));
      } catch {
        if (signal.aborted) return;
      }
    };

    const startPoll = () => {
      if (polling || signal.aborted) return;
      polling = true;
      void pollOnce();
      indexingTimer = window.setInterval(() => {
        void fetchIndexing(projectId, signal).then((indexing) => {
          if (signal.aborted || indexing == null) return;
          setState((current) => ({ ...current, projectId, indexing }));
        });
      }, INDEXING_POLL_MS);
      notificationTimer = window.setInterval(() => {
        void fetchNotifications(projectId, signal).then((notifications) => {
          if (signal.aborted || notifications == null) return;
          setState((current) => ({ ...current, projectId, notifications }));
        });
      }, NOTIFICATIONS_POLL_MS);
    };

    const url = `${API_URL}/api/projects/${projectId}/events`;
    try {
      source = new EventSource(url, { withCredentials: true });
    } catch {
      setState({ projectId, indexing: null, notifications: null, live: false });
      startPoll();
      return () => {
        abort.abort();
        stopPoll();
      };
    }

    source.addEventListener("snapshot", (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as {
          indexing?: unknown;
          notifications?: unknown;
        };
        if (signal.aborted) return;
        setState({
          projectId,
          live: true,
          indexing: normalizeIndexingState(payload.indexing),
          notifications: asNotificationList(payload.notifications),
        });
      } catch {
        /* malformed frame: keep the last good snapshot */
      }
    });
    source.addEventListener("indexing", (event: MessageEvent<string>) => {
      try {
        applyIndexing(JSON.parse(event.data));
      } catch {
        /* ignore */
      }
    });
    source.addEventListener("notifications", (event: MessageEvent<string>) => {
      try {
        applyNotifications(JSON.parse(event.data));
      } catch {
        /* ignore */
      }
    });
    source.onopen = () => {
      if (signal.aborted) return;
      stopPoll();
      setState((current) => ({ ...current, projectId, live: true }));
    };
    source.onerror = () => {
      if (signal.aborted) return;
      setState((current) => ({ ...current, projectId, live: false }));
      startPoll();
    };

    setState({ projectId, indexing: null, notifications: null, live: false });
    void pollOnce();

    return () => {
      abort.abort();
      stopPoll();
      source?.close();
    };
  }, [projectId, enabled]);

  if (!enabled || !projectId) return EMPTY_STATE;
  return state.projectId === projectId ? state : { ...EMPTY_STATE, projectId };
}

export function ConsoleEventsProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const { currentProject } = useProject();
  const enabled = isAuthenticated && !!currentProject?.id;
  const value = useConsoleEventsStream(currentProject?.id ?? null, enabled);
  return (
    <ConsoleEventsContext.Provider value={value}>
      {children}
    </ConsoleEventsContext.Provider>
  );
}

export function useConsoleEvents(): ConsoleEventsState {
  return useContext(ConsoleEventsContext);
}

/** Stable callback identity is not required; this is a read of the live stream. */
export function useConsoleIndexing(
  projectId: string,
  enabled: boolean
): ProjectIndexingState | null {
  const events = useConsoleEvents();
  if (!enabled || !projectId) return null;
  if (events.projectId !== projectId) return null;
  return events.indexing;
}
