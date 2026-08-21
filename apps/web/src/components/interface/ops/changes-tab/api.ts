import type { ChangeKind } from "@/components/interface/provider/data";
import type { DetectionStatus, FileHit, ProjectChange } from "./data";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type ChangeScanStatus = "idle" | "scanning" | "ready" | "error";

export interface ChangeScan {
  provider: string;
  status: ChangeScanStatus;
  progress_percent: number;
  error_message?: string | null;
}

export interface ProjectChangesResponse {
  subscribed: boolean;
  scan: ChangeScan;
  changes: ProjectChange[];
}

const KINDS = new Set<ChangeKind>([
  "deprecation",
  "replacement",
  "new_identifier",
  "breaking_change",
  "feature",
  "fix",
  "issue",
  "security",
  "announcement",
  "change",
  "libraries",
  "other",
]);

const STATUSES = new Set<DetectionStatus>(["needs_you", "watching", "dismissed"]);

function asChange(raw: unknown): ProjectChange | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const kind = KINDS.has(row.kind as ChangeKind) ? (row.kind as ChangeKind) : "other";
  const status = STATUSES.has(row.status as DetectionStatus)
    ? (row.status as DetectionStatus)
    : "watching";
  const files = Array.isArray(row.files)
    ? row.files.filter((file): file is FileHit => {
        return Boolean(file && typeof file === "object" && typeof (file as FileHit).path === "string");
      })
    : [];
  const identifiers = Array.isArray(row.identifiers)
    ? row.identifiers.map((item) => String(item))
    : [];
  const repos = Array.isArray(row.repos) ? row.repos.map((item) => String(item)) : [];
  return {
    id: String(row.id ?? ""),
    provider: String(row.provider ?? "Google Cloud"),
    providerSlug: String(row.providerSlug ?? "google"),
    product: String(row.product ?? ""),
    title: String(row.title ?? ""),
    summary: String(row.summary ?? ""),
    kind,
    status,
    statusReason: row.statusReason ? String(row.statusReason) : undefined,
    announcedAt: row.announcedAt ? String(row.announcedAt) : undefined,
    effectiveAt: row.effectiveAt ? String(row.effectiveAt) : undefined,
    identifiers,
    identifierCounts:
      row.identifierCounts && typeof row.identifierCounts === "object"
        ? (row.identifierCounts as Record<string, number>)
        : undefined,
    replacement: row.replacement ? String(row.replacement) : undefined,
    migration: row.migration === "semantic" || row.migration === "mechanical" ? row.migration : undefined,
    failClosed: Boolean(row.failClosed),
    repo: row.repo ? String(row.repo) : undefined,
    repos: repos.length > 0 ? repos : undefined,
    fileHits: Number(row.fileHits ?? files.reduce((sum, file) => sum + (file.hits ?? 0), 0)),
    fileCount: Number(row.fileCount ?? files.length),
    files,
    sourceUrls: Array.isArray(row.sourceUrls) ? row.sourceUrls.map((item) => String(item)) : [],
    source: "live",
  };
}

export async function fetchProjectChanges(projectId: string): Promise<ProjectChangesResponse> {
  const response = await fetch(`${API_URL}/api/projects/${projectId}/changes`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`changes ${response.status}`);
  }
  const payload = (await response.json()) as {
    subscribed?: boolean;
    scan?: Partial<ChangeScan>;
    changes?: unknown[];
  };
  return {
    subscribed: Boolean(payload.subscribed),
    scan: {
      provider: String(payload.scan?.provider ?? "google"),
      status: (payload.scan?.status as ChangeScanStatus) || "idle",
      progress_percent: Number(payload.scan?.progress_percent ?? 0),
      error_message: payload.scan?.error_message ?? null,
    },
    changes: (payload.changes ?? []).map(asChange).filter((row): row is ProjectChange => row != null && row.id !== ""),
  };
}

export async function dismissProjectChange(projectId: string, changeId: string): Promise<void> {
  const response = await fetch(
    `${API_URL}/api/projects/${projectId}/changes/${encodeURIComponent(changeId)}/dismiss`,
    { method: "POST", credentials: "include" },
  );
  if (!response.ok) {
    throw new Error(`dismiss ${response.status}`);
  }
}

export async function reopenProjectChange(projectId: string, changeId: string): Promise<void> {
  const response = await fetch(
    `${API_URL}/api/projects/${projectId}/changes/${encodeURIComponent(changeId)}/reopen`,
    { method: "POST", credentials: "include" },
  );
  if (!response.ok) {
    throw new Error(`reopen ${response.status}`);
  }
}
