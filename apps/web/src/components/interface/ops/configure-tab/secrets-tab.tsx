"use client";

import { useMemo, useState, useEffect, useCallback, useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Spinner } from "@/components/ui/spinner";
import { Key, Plus, RefreshCw, AlertTriangle, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { AddSecretDialog, type SecretRepoOption } from "@/components/interface/secret-managers";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type WorkspaceRef = {
  id: string;
  name: string;
  workspace_path?: string | null;
  repo_url?: string | null;
};

export interface ConfiguredSecretRow {
  id: string;
  name: string;
  type: string;
  arn: string;
  created_at: string;
  last_rotated: string | null;
  referenced_by: string[];
  status: string;
  workspace_id?: string | null;
  workspace_name?: string | null;
  workspace_path?: string | null;
}

export interface PendingSecretRow {
  name: string;
  type: string;
  description: string;
  required_by: string[];
  id?: string;
  workspace_id?: string | null;
  workspace_name?: string | null;
  workspace_path?: string | null;
}

interface SecretsTabProps {
  secrets: {
    configured: ConfiguredSecretRow[];
    pending: PendingSecretRow[];
  };
  /** Workspaces from project settings (demo: from mock-ops.workspaces). Empty when unknown. */
  workspaces?: WorkspaceRef[];
  /** Linked GitHub `owner/repo` for repo folder scope (Add Secret). */
  repoFullName?: string | null;
  repoDefaultBranch?: string | null;
  /** Imported repos — Add Secret picks one when there are several. */
  repos?: SecretRepoOption[];
  projectId?: string;
  /** Demo / logged-out: Add Secret simulates save; no API. */
  secretsPreviewMode?: boolean;
  /** Logged-in sample rows from demo JSON — disable Configure / expand actions that assume real API ids. */
  secretsUseMockFallback?: boolean;
  onRequirementSatisfied?: () => void;
  /** When true (one shot), open Add Secret — used by thread CTAs / ?openCredentialModal=secret */
  openCredentialModalRequest?: boolean;
  onOpenCredentialModalConsumed?: () => void;
}

function isSharedWorkspaceId(id: string | null | undefined): boolean {
  return id == null || id === "";
}

/** Repo-relative import path for display, e.g. `services/orchestrator` → `/services/orchestrator/` */
function workspacePathBadge(path: string | null | undefined): string | null {
  const raw = path?.trim() ?? "";
  if (!raw) return null;
  const p = raw.replace(/^\/+|\/+$/g, "");
  if (!p) return null;
  return `/${p}/`;
}

/** Badge on a secret row: prefer import path (matches folder picker), else API workspace name. */
function secretScopeBadge(
  secret: { workspace_id?: string | null; workspace_name?: string | null; workspace_path?: string | null },
  workspacesList: WorkspaceRef[]
): string {
  if (isSharedWorkspaceId(secret.workspace_id)) return "/";
  const directPath = workspacePathBadge(secret.workspace_path);
  if (directPath) return directPath;
  const ws = workspacesList.find((w) => w.id === secret.workspace_id);
  const pathBadge = ws ? workspacePathBadge(ws.workspace_path) : null;
  if (pathBadge) return pathBadge;
  return secret.workspace_name || secret.workspace_id || "Workspace";
}

function workspaceChipLabel(ws: WorkspaceRef): { primary: string; title: string } {
  const pathBadge = workspacePathBadge(ws.workspace_path);
  if (pathBadge) {
    return { primary: pathBadge, title: `${pathBadge} (${ws.name})` };
  }
  return { primary: ws.name, title: ws.name };
}

/** Teal checked/indeterminate + white glyph — matches table selection; works in light/dark. */
const secretsTableCheckboxClass =
  "border-[var(--border-color)] bg-[var(--bg-primary)] text-white data-[state=checked]:bg-primary data-[state=checked]:border-primary data-[state=indeterminate]:bg-primary data-[state=indeterminate]:border-primary data-[state=checked]:text-white data-[state=indeterminate]:text-white";

function deleteSecretQuery(secret: ConfiguredSecretRow): string {
  const params = new URLSearchParams();
  if (isSharedWorkspaceId(secret.workspace_id)) {
    params.set("workspace_id", "_shared");
  } else if (secret.workspace_id) {
    params.set("workspace_id", secret.workspace_id);
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/** Parse KEY=value lines (same idea as bulk add). */
function parseEnvLines(text: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const line of text.split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith("#")) continue;
    const eq = t.indexOf("=");
    if (eq <= 0) continue;
    const k = t.slice(0, eq).trim();
    let v = t.slice(eq + 1).trim();
    if (
      (v.startsWith('"') && v.endsWith('"')) ||
      (v.startsWith("'") && v.endsWith("'"))
    ) {
      v = v.slice(1, -1);
    }
    if (k) out.set(k, v);
  }
  return out;
}

async function postSecretRotation(
  projectId: string,
  secretName: string,
  secretValue: string,
  workspaceId: string | null | undefined
): Promise<void> {
  const body: Record<string, unknown> = {
    secret_name: secretName,
    secret_value: secretValue,
  };
  if (workspaceId != null && workspaceId !== "") {
    body.workspace_id = workspaceId;
  }
  const res = await fetch(`${API_URL}/api/projects/${projectId}/secrets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: string }).detail;
    throw new Error(typeof detail === "string" ? detail : `Failed (${res.status})`);
  }
}

export function SecretsTab({
  secrets,
  workspaces = [],
  repoFullName = null,
  repoDefaultBranch = null,
  repos = [],
  projectId,
  secretsPreviewMode = false,
  secretsUseMockFallback = false,
  onRequirementSatisfied,
  openCredentialModalRequest = false,
  onOpenCredentialModalConsumed,
}: SecretsTabProps) {
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showConfigureDialog, setShowConfigureDialog] = useState(false);
  const [selectedSecret, setSelectedSecret] = useState<PendingSecretRow | null>(null);
  const [rotateTarget, setRotateTarget] = useState<ConfiguredSecretRow | null>(null);
  const [deletingSecretId, setDeletingSecretId] = useState<string | null>(null);
  const [selectedConfiguredIds, setSelectedConfiguredIds] = useState<Set<string>>(() => new Set());
  const [bulkRotateOpen, setBulkRotateOpen] = useState(false);
  const [bulkRotateText, setBulkRotateText] = useState("");
  const [bulkRotateBusy, setBulkRotateBusy] = useState(false);
  const [bulkRotateError, setBulkRotateError] = useState<string | null>(null);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [deleteDialog, setDeleteDialog] = useState<
    { type: "idle" } | { type: "single"; secret: ConfiguredSecretRow } | { type: "bulk" }
  >({ type: "idle" });

  const secretLifecycleEnabled = Boolean(projectId && !secretsPreviewMode && !secretsUseMockFallback);
  /** all | __shared__ (/) | workspace id */
  const [secretsFilter, setSecretsFilter] = useState<"all" | "__shared__" | string>("all");

  const consumeCredentialModalRef = useRef(onOpenCredentialModalConsumed);
  consumeCredentialModalRef.current = onOpenCredentialModalConsumed;
  useEffect(() => {
    if (!openCredentialModalRequest) return;
    setShowAddDialog(true);
    consumeCredentialModalRef.current?.();
  }, [openCredentialModalRequest]);

  const sortedWorkspaces = useMemo(
    () => [...workspaces].sort((a, b) => a.name.localeCompare(b.name)),
    [workspaces]
  );

  const hasWorkspaces = sortedWorkspaces.length > 0;

  const groupedByWorkspace = useMemo(() => {
    const knownIds = new Set(sortedWorkspaces.map((w) => w.id));
    const sharedCfg = secrets.configured.filter((s) => isSharedWorkspaceId(s.workspace_id));
    const sharedPend = secrets.pending.filter((s) => isSharedWorkspaceId(s.workspace_id));
    const groups: {
      key: string;
      title: string;
      subtitle?: string;
      configured: ConfiguredSecretRow[];
      pending: PendingSecretRow[];
    }[] = [];

    if (hasWorkspaces) {
      groups.push({
        key: "__shared__",
        title: "/",
        configured: sharedCfg,
        pending: sharedPend,
      });
      for (const ws of sortedWorkspaces) {
        const cfg = secrets.configured.filter((s) => s.workspace_id === ws.id);
        const pend = secrets.pending.filter((s) => s.workspace_id === ws.id);
        const pathBadge = workspacePathBadge(ws.workspace_path);
        groups.push({
          key: ws.id,
          title: pathBadge ?? ws.name,
          subtitle: pathBadge ? ws.name : undefined,
          configured: cfg,
          pending: pend,
        });
      }
    } else {
      if (sharedCfg.length > 0 || sharedPend.length > 0) {
        groups.push({
          key: "__shared__",
          title: "/",
          configured: sharedCfg,
          pending: sharedPend,
        });
      }
      for (const ws of sortedWorkspaces) {
        const cfg = secrets.configured.filter((s) => s.workspace_id === ws.id);
        const pend = secrets.pending.filter((s) => s.workspace_id === ws.id);
        if (cfg.length === 0 && pend.length === 0) continue;
        const pathBadge = workspacePathBadge(ws.workspace_path);
        groups.push({
          key: ws.id,
          title: pathBadge ?? ws.name,
          subtitle: pathBadge ? ws.name : undefined,
          configured: cfg,
          pending: pend,
        });
      }
    }

    const orphanIds = new Set<string>();
    for (const s of secrets.configured) {
      const wid = s.workspace_id;
      if (!isSharedWorkspaceId(wid) && wid && !knownIds.has(wid)) orphanIds.add(wid);
    }
    for (const s of secrets.pending) {
      const wid = s.workspace_id;
      if (!isSharedWorkspaceId(wid) && wid && !knownIds.has(wid)) orphanIds.add(wid);
    }
    for (const oid of orphanIds) {
      groups.push({
        key: oid,
        title: "Removed workspace",
        configured: secrets.configured.filter((s) => s.workspace_id === oid),
        pending: secrets.pending.filter((s) => s.workspace_id === oid),
      });
    }

    return groups;
  }, [secrets.configured, secrets.pending, sortedWorkspaces, hasWorkspaces]);

  const filteredWorkspaceGroups = useMemo(() => {
    if (!hasWorkspaces) return groupedByWorkspace;
    if (secretsFilter === "all") return groupedByWorkspace;
    if (secretsFilter === "__shared__") {
      return groupedByWorkspace.filter((g) => g.key === "__shared__");
    }
    return groupedByWorkspace.filter((g) => g.key === "__shared__" || g.key === secretsFilter);
  }, [groupedByWorkspace, hasWorkspaces, secretsFilter]);

  useEffect(() => {
    const valid = new Set(secrets.configured.map((s) => s.id));
    setSelectedConfiguredIds((prev) => new Set([...prev].filter((id) => valid.has(id))));
  }, [secrets.configured]);

  const toggleConfiguredSelect = useCallback((id: string, checked: boolean) => {
    setSelectedConfiguredIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const selectedConfiguredRows = useMemo(
    () => secrets.configured.filter((s) => selectedConfiguredIds.has(s.id)),
    [secrets.configured, selectedConfiguredIds]
  );

  const handleConfigure = (secret: PendingSecretRow) => {
    setSelectedSecret(secret);
    setShowConfigureDialog(true);
  };

  const openAddSecret = () => setShowAddDialog(true);

  const performDeleteSecret = async (secret: ConfiguredSecretRow) => {
    if (!projectId || !secretLifecycleEnabled) return;
    setDeletingSecretId(secret.id);
    try {
      const qs = deleteSecretQuery(secret);
      const res = await fetch(
        `${API_URL}/api/projects/${projectId}/secrets/${encodeURIComponent(secret.name)}${qs}`,
        { method: "DELETE", credentials: "include" }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const detail = (err as { detail?: string }).detail;
        throw new Error(typeof detail === "string" ? detail : `Failed (${res.status})`);
      }
      setSelectedConfiguredIds((prev) => {
        if (!prev.has(secret.id)) return prev;
        const next = new Set(prev);
        next.delete(secret.id);
        return next;
      });
      setRotateTarget((t) => (t?.id === secret.id ? null : t));
      onRequirementSatisfied?.();
    } catch (e) {
      console.error(e);
      window.alert(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeletingSecretId(null);
      setDeleteDialog({ type: "idle" });
    }
  };

  const performMassDelete = async () => {
    if (!projectId || !secretLifecycleEnabled || selectedConfiguredRows.length === 0) return;
    setBulkDeleting(true);
    const deletedIds = new Set(selectedConfiguredRows.map((s) => s.id));
    try {
      for (const secret of selectedConfiguredRows) {
        const qs = deleteSecretQuery(secret);
        const res = await fetch(
          `${API_URL}/api/projects/${projectId}/secrets/${encodeURIComponent(secret.name)}${qs}`,
          { method: "DELETE", credentials: "include" }
        );
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          const detail = (err as { detail?: string }).detail;
          throw new Error(
            typeof detail === "string" ? `${secret.name}: ${detail}` : `${secret.name}: ${res.status}`
          );
        }
      }
      setSelectedConfiguredIds(new Set());
      setRotateTarget((t) => (t && deletedIds.has(t.id) ? null : t));
      onRequirementSatisfied?.();
    } catch (e) {
      console.error(e);
      window.alert(e instanceof Error ? e.message : "Bulk delete failed");
    } finally {
      setBulkDeleting(false);
      setDeleteDialog({ type: "idle" });
    }
  };

  const deleteDialogBusy = deletingSecretId !== null || bulkDeleting;

  const applyBulkRotate = async () => {
    if (!projectId || !secretLifecycleEnabled || selectedConfiguredRows.length === 0) return;
    setBulkRotateBusy(true);
    setBulkRotateError(null);
    try {
      const envMap = parseEnvLines(bulkRotateText);
      if (envMap.size === 0) {
        setBulkRotateError("Paste at least one KEY=value line matching selected secret names.");
        return;
      }
      let updated = 0;
      let missing = 0;
      const errors: string[] = [];
      for (const row of selectedConfiguredRows) {
        const val = envMap.get(row.name);
        if (val === undefined) {
          missing++;
          continue;
        }
        try {
          await postSecretRotation(projectId, row.name, val, row.workspace_id);
          updated++;
        } catch (err) {
          errors.push(
            `${row.name}: ${err instanceof Error ? err.message : "failed"}`
          );
        }
      }
      if (errors.length > 0) {
        setBulkRotateError(
          `Updated ${updated}. ${missing} selected had no matching line. Errors: ${errors.slice(0, 5).join("; ")}${
            errors.length > 5 ? "…" : ""
          }`
        );
        if (updated > 0) onRequirementSatisfied?.();
        return;
      }
      setBulkRotateOpen(false);
      setBulkRotateText("");
      setSelectedConfiguredIds(new Set());
      onRequirementSatisfied?.();
      if (missing > 0 && updated === 0) {
        window.alert(
          `No values applied. Add lines for: ${selectedConfiguredRows.map((r) => r.name).join(", ")}`
        );
      } else if (missing > 0) {
        window.alert(`Updated ${updated} secret(s). ${missing} selected had no matching KEY= line.`);
      }
    } catch (e) {
      setBulkRotateError(e instanceof Error ? e.message : "Bulk rotate failed");
    } finally {
      setBulkRotateBusy(false);
    }
  };

  const hasNoSecrets = secrets.pending.length === 0 && secrets.configured.length === 0;

  const renderSecretRow = (secret: ConfiguredSecretRow) => {
    const isSelected = selectedConfiguredIds.has(secret.id);
    return (
      <tr
        key={secret.id}
        className={cn(
          "group border-b border-[var(--border-color)] last:border-b-0 transition-colors text-xs",
          isSelected ? "bg-primary/5" : "hover:bg-[var(--bg-tertiary)]"
        )}
      >
        {secretLifecycleEnabled ? (
          <td className="w-8 px-2 py-2 align-middle">
            <Checkbox
              checked={isSelected}
              onCheckedChange={(v) => toggleConfiguredSelect(secret.id, v === true)}
              aria-label={`Select ${secret.name}`}
              className={secretsTableCheckboxClass}
            />
          </td>
        ) : null}
        <td className="py-2 px-2 align-middle">
          <span className="font-medium font-mono text-[var(--text-primary)] text-[11px]">{secret.name}</span>
        </td>
        {hasWorkspaces ? (
          <td className="py-2 px-2 align-middle max-w-[10rem] truncate">
            <span
              className={cn(
                "text-[10px]",
                isSharedWorkspaceId(secret.workspace_id)
                  ? "font-mono text-primary"
                  : "text-[var(--text-secondary)]"
              )}
            >
              {secretScopeBadge(secret, sortedWorkspaces)}
            </span>
          </td>
        ) : null}
        <td className="py-2 px-2 align-middle w-14">
          <span className="inline-flex items-center gap-1 text-[10px] text-[#10b981]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#10b981] inline-block shrink-0" />
            Active
          </span>
        </td>
        <td className="py-2 px-2 align-middle text-[10px] text-[var(--text-secondary)] tabular-nums whitespace-nowrap">
          {secret.created_at ? new Date(secret.created_at).toLocaleDateString() : "—"}
        </td>
        {secretLifecycleEnabled ? (
          <td className="py-2 px-2 align-middle text-right whitespace-nowrap">
            <div className="opacity-0 group-hover:opacity-100 transition-opacity inline-flex items-center gap-1">
              <button
                type="button"
                disabled={deletingSecretId === secret.id}
                onClick={() => setRotateTarget(secret)}
                className="inline-flex items-center justify-center h-6 w-6 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors disabled:opacity-50"
                title="Rotate"
              >
                <RefreshCw className="h-3 w-3" />
              </button>
              <button
                type="button"
                disabled={deletingSecretId === secret.id}
                onClick={() => setDeleteDialog({ type: "single", secret })}
                className="inline-flex items-center justify-center h-6 w-6 rounded text-[var(--text-secondary)] hover:text-red-500 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                title="Delete"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          </td>
        ) : null}
      </tr>
    );
  };

  const renderSecretTable = (configuredSecrets: ConfiguredSecretRow[]) => {
    if (configuredSecrets.length === 0) return null;
    const allInThisTableSelected =
      configuredSecrets.length > 0 &&
      configuredSecrets.every((s) => selectedConfiguredIds.has(s.id));
    const someInThisTableSelected = configuredSecrets.some((s) => selectedConfiguredIds.has(s.id));
    return (
      <div className="rounded-lg border border-[var(--border-color)] overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-[var(--border-color)] bg-[var(--bg-secondary)]">
              {secretLifecycleEnabled ? (
                <th className="w-8 px-2 py-1.5 align-middle">
                  <Checkbox
                    checked={
                      allInThisTableSelected ? true : someInThisTableSelected ? "indeterminate" : false
                    }
                    onCheckedChange={(v) => {
                      const checked = v === true;
                      setSelectedConfiguredIds((prev) => {
                        const next = new Set(prev);
                        for (const s of configuredSecrets) {
                          if (checked) next.add(s.id);
                          else next.delete(s.id);
                        }
                        return next;
                      });
                    }}
                    disabled={bulkDeleting || bulkRotateBusy}
                    aria-label="Select all in this group"
                    className={secretsTableCheckboxClass}
                  />
                </th>
              ) : null}
              <th className="py-1.5 px-2 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider">Name</th>
              {hasWorkspaces ? (
                <th className="py-1.5 px-2 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider">Scope</th>
              ) : null}
              <th className="py-1.5 px-2 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider w-14">Status</th>
              <th className="py-1.5 px-2 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider">Created</th>
              {secretLifecycleEnabled ? (
                <th className="py-1.5 px-2 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider w-20" />
              ) : null}
            </tr>
          </thead>
          <tbody>
            {configuredSecrets.map((s) => renderSecretRow(s))}
          </tbody>
        </table>
      </div>
    );
  };

  const renderPendingBlock = (pending: PendingSecretRow[]) =>
    pending.length > 0 ? (
      <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-xs text-amber-600 dark:text-amber-400 font-medium">
              {pending.length} secret{pending.length > 1 ? "s" : ""} required
            </p>
            <div className="mt-2 space-y-2">
              {pending.map((secret) => (
                <div
                  key={`${secret.name}-${secret.workspace_id ?? "shared"}`}
                  className="flex items-center justify-between gap-2 bg-[var(--bg-secondary)] rounded-md px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-xs font-medium text-[var(--text-primary)]">{secret.name}</p>
                      {hasWorkspaces && secret.workspace_name && (
                        <Badge variant="outline" className="text-[9px] text-[var(--text-secondary)]">
                          {secret.workspace_name}
                        </Badge>
                      )}
                    </div>
                    <p className="text-[10px] text-[var(--text-secondary)]">{secret.description}</p>
                  </div>
                  {secretsUseMockFallback ? (
                    <span className="text-[9px] text-[var(--text-tertiary)] shrink-0 px-2">Example</span>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleConfigure(secret)}
                      className="h-6 text-[10px] shrink-0 border-amber-500/30 text-amber-500 hover:bg-amber-500/10 hover:text-amber-500"
                    >
                      Configure
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    ) : null;

  return (
    <>
      <AddSecretDialog
        open={showAddDialog}
        onOpenChange={setShowAddDialog}
        mode="add"
        projectId={projectId}
        workspaces={workspaces}
        initialWorkspaceScope="__shared__"
        repoFullName={repoFullName}
        repoDefaultBranch={repoDefaultBranch}
        repos={repos}
        secretsPreviewMode={secretsPreviewMode}
        onSaved={() => onRequirementSatisfied?.()}
      />
      {selectedSecret && (
        <AddSecretDialog
          open={showConfigureDialog}
          onOpenChange={setShowConfigureDialog}
          mode="configure"
          existingSecret={{ name: selectedSecret.name, type: selectedSecret.type }}
          projectId={projectId}
          workspaces={workspaces}
          initialWorkspaceScope={
            selectedSecret.workspace_id != null && selectedSecret.workspace_id !== ""
              ? selectedSecret.workspace_id
              : "__shared__"
          }
          repoFullName={repoFullName}
          repoDefaultBranch={repoDefaultBranch}
          repos={repos}
          requirementId={selectedSecret.id}
          secretsPreviewMode={secretsPreviewMode}
          onSaved={() => onRequirementSatisfied?.()}
        />
      )}
      {rotateTarget && (
        <AddSecretDialog
          open
          onOpenChange={(open) => {
            if (!open) setRotateTarget(null);
          }}
          mode="rotate"
          existingSecret={{ name: rotateTarget.name, type: rotateTarget.type }}
          projectId={projectId}
          workspaces={workspaces}
          initialWorkspaceScope={
            rotateTarget.workspace_id != null && rotateTarget.workspace_id !== ""
              ? rotateTarget.workspace_id
              : "__shared__"
          }
          repoFullName={repoFullName}
          repoDefaultBranch={repoDefaultBranch}
          repos={repos}
          secretsPreviewMode={secretsPreviewMode}
          onSaved={() => {
            setRotateTarget(null);
            onRequirementSatisfied?.();
          }}
        />
      )}

      <Dialog
        open={bulkRotateOpen}
        onOpenChange={(open) => {
          setBulkRotateOpen(open);
          if (!open) {
            setBulkRotateText("");
            setBulkRotateError(null);
          }
        }}
      >
        <DialogContent className="max-w-lg bg-[var(--bg-primary)] border-[var(--border-color)]">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
              Rotate {selectedConfiguredIds.size} secret{selectedConfiguredIds.size === 1 ? "" : "s"}
            </DialogTitle>
            <DialogDescription className="text-xs text-[var(--text-secondary)] pt-1 leading-relaxed">
              Paste <span className="font-mono">KEY=value</span> lines. Each key must match a <strong>selected</strong>{" "}
              secret name; workspace scope stays the same as today. Upload a snippet from an{" "}
              <span className="font-mono">.env</span> is fine.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={bulkRotateText}
            onChange={(e) => setBulkRotateText(e.target.value)}
            placeholder={"OPENAI_API_KEY=sk-...\nDATABASE_URL=postgres://..."}
            disabled={bulkRotateBusy}
            className="min-h-[160px] text-xs font-mono bg-[var(--bg-secondary)] border-[var(--border-color)]"
          />
          {bulkRotateError ? (
            <p className="text-[11px] text-red-500 flex items-start gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              {bulkRotateError}
            </p>
          ) : null}
          <DialogFooter className="gap-2 sm:gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="text-xs"
              disabled={bulkRotateBusy}
              onClick={() => setBulkRotateOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              className="text-xs bg-primary hover:bg-primary/90 text-white"
              disabled={bulkRotateBusy || !bulkRotateText.trim()}
              onClick={() => void applyBulkRotate()}
            >
              {bulkRotateBusy ? (
                <>
                  <Spinner className="h-3.5 w-3.5 mr-2" />
                  Applying…
                </>
              ) : (
                "Apply rotations"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={deleteDialog.type !== "idle"}
        onOpenChange={(open) => {
          if (!open && !deleteDialogBusy) setDeleteDialog({ type: "idle" });
        }}
      >
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-base text-[var(--text-primary)]">
              {deleteDialog.type === "single"
                ? `Delete “${deleteDialog.secret.name}”?`
                : deleteDialog.type === "bulk"
                  ? `Delete ${selectedConfiguredRows.length} secret${selectedConfiguredRows.length === 1 ? "" : "s"}?`
                  : ""}
            </AlertDialogTitle>
            <AlertDialogDescription className="text-sm text-[var(--text-secondary)] leading-relaxed">
              {deleteDialog.type === "single"
                ? "This removes the secret from AWS Secrets Manager and from this project. You can add it again later, but this cannot be undone."
                : deleteDialog.type === "bulk"
                  ? "This removes all selected secrets from AWS Secrets Manager and from this project. You can add them again later, but this cannot be undone."
                  : null}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteDialogBusy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={deleteDialogBusy}
              className="bg-red-500 hover:bg-red-600 text-white focus:ring-red-500 sm:mt-0 inline-flex items-center justify-center gap-2"
              onClick={(e) => {
                e.preventDefault();
                if (deleteDialog.type === "single") void performDeleteSecret(deleteDialog.secret);
                else if (deleteDialog.type === "bulk") void performMassDelete();
              }}
            >
              {deleteDialogBusy ? (
                <>
                  <Spinner className="h-3.5 w-3.5" />
                  Deleting…
                </>
              ) : (
                "Delete"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <div className="h-full overflow-y-auto bg-[var(--bg-primary)] min-w-0">
        {hasNoSecrets ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-md px-4">
              <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
                <Key className="h-5 w-5 text-[var(--text-secondary)]" />
              </div>
              <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">No secrets yet</h2>
              <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
                Add secrets per workspace (or shared across all). Values stay in your cloud secret store; we only keep
                references.
              </p>
              <Button
                size="sm"
                onClick={openAddSecret}
                className="h-8 text-xs bg-primary hover:bg-primary/90 text-white"
              >
                <Plus className="h-3 w-3 mr-1" />
                Add Secret
              </Button>
            </div>
          </div>
        ) : (
          <div className="p-6 space-y-6">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div>
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">Secrets Management</h2>
                <p className="text-xs text-[var(--text-secondary)] mt-1 leading-relaxed">
                  {hasWorkspaces
                    ? "Grouped by workspace. `/` (root) applies to every workspace."
                    : "Store API keys and credentials in your cloud secret store."}
                  {secretsPreviewMode && (
                    <span className="block mt-1.5 text-[10px] text-[var(--text-secondary)] opacity-75">
                      Showing sample data — sign in to add real secrets.
                    </span>
                  )}
                  {secretsUseMockFallback && (
                    <span className="block mt-1.5 text-[10px] text-[var(--text-secondary)] opacity-90">
                      Example layout from demo data until this project has stored secrets or pending requirements. Add
                      Secret still saves to your project.
                    </span>
                  )}
                </p>
              </div>
              <Button
                size="sm"
                onClick={openAddSecret}
                className="h-8 text-xs bg-primary hover:bg-primary/90 text-white"
              >
                <Plus className="h-3 w-3 mr-1" />
                Add Secret
              </Button>
            </div>

            <div className="bg-primary/10 border border-primary/20 rounded-lg p-4">
              <div className="text-[10px] text-[var(--text-secondary)]">
                <span className="font-medium text-primary">Secrets are encrypted and stored confidentially:</span> We
                use Secrets Manager in your account. We never store secret values — only references to them.
              </div>
            </div>

            {hasWorkspaces && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] text-[var(--text-tertiary)] mr-1">View:</span>
                <button
                  type="button"
                  onClick={() => setSecretsFilter("all")}
                  className={cn(
                    "px-2.5 py-1 rounded-md text-[10px] font-medium border transition-colors",
                    secretsFilter === "all"
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-[var(--border-color)] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                  )}
                >
                  All
                </button>
                {sortedWorkspaces.map((ws) => {
                  const chip = workspaceChipLabel(ws);
                  return (
                    <button
                      key={ws.id}
                      type="button"
                      onClick={() => setSecretsFilter(ws.id)}
                      className={cn(
                        "px-2.5 py-1 rounded-md text-[10px] font-medium border transition-colors max-w-[12rem] truncate",
                        secretsFilter === ws.id
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-[var(--border-color)] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]",
                        chip.primary.startsWith("/") && "font-mono tracking-tight"
                      )}
                      title={chip.title}
                    >
                      {chip.primary}
                    </button>
                  );
                })}
                <button
                  type="button"
                  onClick={() => setSecretsFilter("__shared__")}
                  className={cn(
                    "px-2.5 py-1 rounded-md text-[10px] font-medium border font-mono transition-colors",
                    secretsFilter === "__shared__"
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-[var(--border-color)] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                  )}
                  title="Root scope — every workspace"
                >
                  /
                </button>
              </div>
            )}

            {selectedConfiguredIds.size > 0 ? (
              <div className="flex flex-wrap items-center gap-2 px-3 py-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)]">
                <span className="text-[10px] font-medium text-[var(--text-primary)] tabular-nums">
                  {selectedConfiguredIds.size} selected
                </span>
                <span className="w-px h-4 bg-[var(--border-color)]" />
                <button
                  type="button"
                  disabled={bulkDeleting || bulkRotateBusy}
                  onClick={() => {
                    setBulkRotateError(null);
                    setBulkRotateOpen(true);
                  }}
                  className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md text-[10px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors disabled:opacity-50 disabled:pointer-events-none"
                >
                  <RefreshCw className="h-3 w-3" />
                  Rotate
                </button>
                <button
                  type="button"
                  disabled={bulkDeleting || bulkRotateBusy}
                  onClick={() => setDeleteDialog({ type: "bulk" })}
                  className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md text-[10px] font-medium text-red-500 hover:bg-red-500/10 transition-colors disabled:opacity-50 disabled:pointer-events-none"
                >
                  {bulkDeleting ? (
                    <Spinner className="h-3 w-3" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                  {bulkDeleting ? "Deleting…" : "Delete"}
                </button>
                <button
                  type="button"
                  disabled={bulkDeleting || bulkRotateBusy}
                  onClick={() => setSelectedConfiguredIds(new Set())}
                  className="ml-auto h-7 px-2.5 rounded-md text-[10px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors disabled:opacity-50 disabled:pointer-events-none"
                >
                  Clear
                </button>
              </div>
            ) : null}

            {hasWorkspaces ? (
              <div className="space-y-8">
                {filteredWorkspaceGroups.map((group) => (
                  <section key={group.key} className="space-y-3">
                    <div className="flex items-center justify-between gap-2 border-b border-[var(--border-color)] pb-2">
                      <div className="min-w-0">
                        <h3
                          className={cn(
                            "text-xs font-semibold text-[var(--text-primary)] truncate",
                            group.key === "__shared__" && "font-mono tracking-tight",
                            group.subtitle && "font-mono tracking-tight"
                          )}
                        >
                          {group.title}
                        </h3>
                        {group.subtitle ? (
                          <p className="text-[10px] text-[var(--text-secondary)] mt-0.5 truncate">
                            {group.subtitle}
                          </p>
                        ) : null}
                      </div>
                      <span className="text-[10px] text-[var(--text-secondary)] tabular-nums">
                        {group.configured.length} configured
                        {group.pending.length > 0 ? ` · ${group.pending.length} pending` : ""}
                      </span>
                    </div>
                    {renderPendingBlock(group.pending)}
                    {renderSecretTable(group.configured)}
                  </section>
                ))}
              </div>
            ) : (
              <>
                {renderPendingBlock(secrets.pending)}
                {renderSecretTable(secrets.configured)}
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
}
