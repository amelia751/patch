"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CheckCircle2, XCircle, Trash2, Cable, CloudOff, Pencil, ChevronDown, ChevronUp, Plus, Cloud } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useTheme } from "@/lib/theme-context";
import { cn } from "@/lib/utils";
import { GCPConnectMethodDialog } from "./gcp-connect-method-dialog";
import type { SecretRepoOption } from "@/components/interface/secret-managers";
import type { WorkspaceRef } from "./secrets-tab";

const GCP_REGION_OPTIONS = [
  { value: "us-central1", label: "us-central1 (Iowa)" },
  { value: "us-east1", label: "us-east1 (South Carolina)" },
  { value: "us-west1", label: "us-west1 (Oregon)" },
  { value: "europe-west1", label: "europe-west1 (Belgium)" },
  { value: "asia-east1", label: "asia-east1 (Taiwan)" },
] as const;

const GCP_ENV_OPTIONS = [
  { value: "development", label: "Development" },
  { value: "staging", label: "Staging" },
  { value: "production", label: "Production" },
] as const;

export type GcpStoredConnection = {
  id: string;
  environment: string;
  gcp_project_id: string;
  gcp_project_number?: string | null;
  service_account_email?: string | null;
  default_region: string;
  workspace_id?: string | null;
  repo_full_name?: string | null;
  last_validated_at?: string | null;
  created_at?: string | null;
  is_active?: boolean;
};

interface GCPConnectionTabProps {
  environmentConnections: {
    dev?: GCPConnection;
    staging?: GCPConnection;
    prod?: GCPConnection;
    development?: GCPConnection;
    production?: GCPConnection;
  };
  connections?: GcpStoredConnection[];
  userId?: string;
  projectId?: string;
  workspaces?: WorkspaceRef[];
  repoFullName?: string | null;
  repos?: SecretRepoOption[];
  openCredentialModalRequest?: boolean;
  onOpenCredentialModalConsumed?: () => void;
  onAddCloudProvider?: () => void;
}

interface GCPConnection {
  status: string;
  project_id: string;
  region: string;
  project_number?: string;
  service_account_email?: string;
  connected_at: string;
  required_apis?: RequiredAPI[];
  id?: string;
  repo_full_name?: string | null;
}

interface RequiredAPI {
  name: string;
  description: string;
  validated: boolean;
  api_endpoint: string;
}

function getEnvLabel(env: string) {
  if (env === "dev" || env === "development") return "Development";
  if (env === "staging") return "Staging";
  if (env === "prod" || env === "production") return "Production";
  return env;
}

function getEnvColor(env: string, theme: string | undefined, mounted: boolean) {
  const colors: Record<string, { dark: string; light: string }> = {
    dev: { dark: "border-blue-500/30 text-blue-400", light: "bg-blue-100 text-blue-700 border-blue-200" },
    development: { dark: "border-blue-500/30 text-blue-400", light: "bg-blue-100 text-blue-700 border-blue-200" },
    staging: { dark: "border-amber-500/30 text-amber-400", light: "bg-amber-100 text-amber-700 border-amber-200" },
    prod: { dark: "border-emerald-500/30 text-emerald-400", light: "bg-emerald-100 text-emerald-700 border-emerald-200" },
    production: { dark: "border-emerald-500/30 text-emerald-400", light: "bg-emerald-100 text-emerald-700 border-emerald-200" },
  };
  const c = colors[env] || colors.development;
  if (!mounted) return "";
  return theme === "dark" ? c.dark : c.light;
}

export function GCPConnectionTab({
  environmentConnections,
  connections = [],
  userId = "default",
  projectId,
  workspaces = [],
  repoFullName = null,
  repos = [],
  openCredentialModalRequest = false,
  onOpenCredentialModalConsumed,
  onAddCloudProvider,
}: GCPConnectionTabProps) {
  const { theme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [expandedEnvs, setExpandedEnvs] = useState<Set<string>>(new Set());
  const [showGcpConnectDialog, setShowGcpConnectDialog] = useState(false);
  const [connectEnv, setConnectEnv] = useState<string>("development");

  // Edit dialog state
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editEnvKey, setEditEnvKey] = useState("");
  const [editRegion, setEditRegion] = useState("");
  const [editEnvironment, setEditEnvironment] = useState("");
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Disconnect state (per-environment)
  const [detachEnv, setDetachEnv] = useState<string | null>(null);
  const [detachConfirmText, setDetachConfirmText] = useState("");
  const [isDetaching, setIsDetaching] = useState(false);
  const [detachError, setDetachError] = useState<string | null>(null);

  useEffect(() => { setMounted(true); }, []);

  const consumeCredentialModalRef = useRef(onOpenCredentialModalConsumed);
  consumeCredentialModalRef.current = onOpenCredentialModalConsumed;
  useEffect(() => {
    if (!openCredentialModalRequest) return;
    setShowGcpConnectDialog(true);
    consumeCredentialModalRef.current?.();
  }, [openCredentialModalRequest]);

  const storedCards = connections.filter((c) => c.is_active !== false);
  const fallbackEntries = (Object.entries(environmentConnections) as [string, GCPConnection | undefined][])
    .filter((e): e is [string, GCPConnection] => !!e[1]);
  const connectedEntries: [string, GCPConnection & { id?: string; repo_full_name?: string | null }][] =
    storedCards.length > 0
      ? storedCards.map((c) => [
          c.id,
          {
            status: "connected",
            project_id: c.gcp_project_id,
            region: c.default_region,
            project_number: c.gcp_project_number ?? undefined,
            service_account_email: c.service_account_email ?? undefined,
            connected_at: c.last_validated_at || c.created_at || new Date().toISOString(),
            id: c.id,
            repo_full_name: c.repo_full_name,
          },
        ])
      : fallbackEntries;

  const availableForConnect = GCP_ENV_OPTIONS;
  const editingConnection = storedCards.find((c) => c.id === editEnvKey);
  const connectedEnvKeys = new Set(
    storedCards.length > 0
      ? storedCards
          .filter((c) => {
            if (!editingConnection) return true;
            return (c.workspace_id ?? "") === (editingConnection.workspace_id ?? "");
          })
          .map((c) => c.environment)
      : fallbackEntries.map(([env]) => env)
  );

  const toggleExpanded = (env: string) => {
    setExpandedEnvs((prev) => {
      const next = new Set(prev);
      next.has(env) ? next.delete(env) : next.add(env);
      return next;
    });
  };

  const openEdit = (envKey: string, conn: GCPConnection) => {
    const stored = storedCards.find((c) => c.id === envKey);
    setEditEnvKey(envKey);
    setEditRegion(conn.region);
    setEditEnvironment(stored?.environment ?? envKey);
    setEditError(null);
    setEditDialogOpen(true);
  };

  const handleSaveEdit = async () => {
    setIsSavingEdit(true);
    setEditError(null);
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      if (!projectId) throw new Error("No PatchAPI project is selected.");
      const resp = await fetch(`${API_URL}/api/projects/${projectId}/gcp-connections/${editEnvKey}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          region: editRegion,
          environment: editEnvironment !== editEnvKey ? editEnvironment : undefined,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Failed to update connection");
      }
      setEditDialogOpen(false);
      window.location.reload();
    } catch (err: any) {
      setEditError(err.message || "Failed to update");
    } finally {
      setIsSavingEdit(false);
    }
  };

  const editHasChanges = () => {
    const stored = storedCards.find((c) => c.id === editEnvKey);
    if (stored) {
      return editRegion !== stored.default_region || editEnvironment !== stored.environment;
    }
    const conn = environmentConnections[editEnvKey as keyof typeof environmentConnections];
    if (!conn) return false;
    return editRegion !== conn.region || editEnvironment !== editEnvKey;
  };

  const handleDetach = async (env: string) => {
    setIsDetaching(true);
    setDetachError(null);
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      if (!projectId) throw new Error("No PatchAPI project is selected.");
      const resp = await fetch(`${API_URL}/api/projects/${projectId}/gcp-connections/${env}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Failed to disconnect");
      }
      window.location.reload();
    } catch (err: any) {
      setDetachError(err.message || "Failed to disconnect");
    } finally {
      setIsDetaching(false);
    }
  };

  const handleConnectClick = () => {
    const firstAvailable = availableForConnect[0]?.value || "development";
    setConnectEnv(firstAvailable);
    setShowGcpConnectDialog(true);
  };

  // ── No connections at all ──
  if (connectedEntries.length === 0) {
    return (
      <>
        <div className="h-full overflow-y-auto bg-[var(--bg-primary)] min-w-0">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <img src="/google-cloud.svg" alt="Google Cloud" className="h-6 w-6" />
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">GCP Connections</h2>
            </div>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-12 text-center">
              <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
                <CloudOff className="h-5 w-5 text-[var(--text-secondary)]" />
              </div>
              <h3 className="text-sm font-medium text-[var(--text-primary)] mb-2">
                No GCP connections
              </h3>
              <p className="text-xs text-[var(--text-secondary)] mb-4">
                Connect Google Cloud Platform to deploy and manage your infrastructure
              </p>
              <Button
                onClick={handleConnectClick}
                className="bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                <Cable className="h-4 w-4 mr-2" />
                Connect GCP project
              </Button>
            </div>
          </div>
        </div>
        <GCPConnectMethodDialog
          open={showGcpConnectDialog}
          onOpenChange={setShowGcpConnectDialog}
          userId={userId}
          environment={connectEnv}
          onEnvironmentChange={setConnectEnv}
          environmentOptions={[...GCP_ENV_OPTIONS]}
          projectId={projectId}
          workspaces={workspaces}
          repoFullName={repoFullName}
          repos={repos}
        />
      </>
    );
  }

  // ── Connected state: accordion cards ──
  return (
    <>
      <div className="h-full overflow-y-auto bg-[var(--bg-primary)] min-w-0">
        <div className="p-6 space-y-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <img src="/google-cloud.svg" alt="Google Cloud" className="h-6 w-6" />
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">GCP Connections</h2>
            </div>
            {availableForConnect.length > 0 && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleConnectClick}
                className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
              >
                <Plus className="h-3.5 w-3.5 mr-1.5" />
                Add connection
              </Button>
            )}
          </div>

          {/* Connection Cards */}
          <div className="space-y-3">
            {connectedEntries.map(([envKey, conn]) => {
              const expanded = expandedEnvs.has(envKey);
              const apis = conn.required_apis || [];
              const allApisValid = apis.length === 0 || apis.every((a) => a.validated);
              const isDetachTarget = detachEnv === envKey;

              return (
                <div
                  key={envKey}
                  className="border border-[var(--border-color)] rounded-lg overflow-hidden bg-[var(--bg-secondary)]"
                >
                  {/* ── Compact header row ── */}
                  <button
                    type="button"
                    onClick={() => toggleExpanded(envKey)}
                    className="w-full p-4 bg-[var(--bg-primary)] flex items-center gap-3 text-left hover:bg-[var(--bg-tertiary)]/50 transition-colors"
                  >
                    {/* Status icon */}
                    {allApisValid ? (
                      <CheckCircle2 className="h-4 w-4 text-[#10b981] flex-shrink-0" />
                    ) : (
                      <XCircle className="h-4 w-4 text-amber-500 flex-shrink-0" />
                    )}

                    {/* Environment tag */}
                    <span className={cn(
                      "text-[10px] font-semibold px-2 py-0.5 rounded border flex-shrink-0",
                      getEnvColor(storedCards.find((c) => c.id === envKey)?.environment ?? envKey, theme, mounted),
                    )}>
                      {getEnvLabel(storedCards.find((c) => c.id === envKey)?.environment ?? envKey)}
                    </span>
                    {conn.repo_full_name ? (
                      <span className="text-[10px] font-mono text-[var(--text-secondary)] truncate max-w-[10rem]">
                        {conn.repo_full_name}
                      </span>
                    ) : null}

                    {/* Summary info */}
                    <span className="text-xs text-[var(--text-secondary)] truncate flex-1 min-w-0">
                      {conn.region} · {conn.project_id}
                    </span>

                    {/* Edit button (stop propagation so it doesn't toggle) */}
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(e) => { e.stopPropagation(); openEdit(envKey, conn); }}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); openEdit(envKey, conn); } }}
                      className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors flex-shrink-0"
                      title="Edit connection"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </span>

                    {/* Chevron */}
                    {expanded ? (
                      <ChevronUp className="h-4 w-4 text-[var(--text-secondary)] flex-shrink-0" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-[var(--text-secondary)] flex-shrink-0" />
                    )}
                  </button>

                  {/* ── Expanded details ── */}
                  {expanded && (
                    <div className="border-t border-[var(--border-color)]">
                      {/* Connection details */}
                      <div className="p-5 space-y-3">
                        <div className="grid grid-cols-2 gap-4 min-w-0">
                          <div className="min-w-0">
                            <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider mb-1 block">Region</label>
                            <p className="text-xs text-[var(--text-primary)] font-medium">{conn.region}</p>
                          </div>
                          <div className="min-w-0">
                            <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider mb-1 block">Project ID</label>
                            <p className="text-xs text-[var(--text-primary)] font-mono truncate">{conn.project_id}</p>
                          </div>
                          {conn.repo_full_name ? (
                            <div className="col-span-2 min-w-0">
                              <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider mb-1 block">Repository</label>
                              <p className="text-xs text-[var(--text-primary)] font-mono truncate">{conn.repo_full_name}</p>
                            </div>
                          ) : null}
                          <div>
                            <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider mb-1 block">Connected</label>
                            <p className="text-xs text-[var(--text-primary)]">
                              {new Date(conn.connected_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                            </p>
                          </div>
                        </div>
                      </div>

                      {/* Required APIs */}
                      {apis.length > 0 && (
                        <div className="px-5 pb-5 pt-0">
                          <div className="flex items-center justify-between mb-3">
                            <h4 className="text-xs font-semibold text-[var(--text-primary)]">Required APIs</h4>
                            <span className="text-[10px] text-[var(--text-secondary)]">
                              {apis.filter((a) => a.validated).length}/{apis.length} enabled
                            </span>
                          </div>
                          <div className="space-y-2">
                            {apis.map((api) => (
                              <div
                                key={api.name}
                                className="flex items-center justify-between gap-3 p-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-primary)]"
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  {api.validated ? (
                                    <CheckCircle2 className="h-3.5 w-3.5 text-[#10b981] flex-shrink-0" />
                                  ) : (
                                    <XCircle className="h-3.5 w-3.5 text-amber-500 flex-shrink-0" />
                                  )}
                                  <div className="min-w-0">
                                    <p className="text-xs font-medium text-[var(--text-primary)] truncate">{api.name}</p>
                                    <p className="text-[10px] text-[var(--text-secondary)] truncate">{api.description}</p>
                                  </div>
                                </div>
                                {!api.validated && (
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => window.open(`https://console.cloud.google.com/apis/library/${api.api_endpoint}?project=${conn.project_id}`, "_blank")}
                                    className="text-[10px] h-7 border-[var(--border-color)] !text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:!text-[var(--text-primary)] flex-shrink-0"
                                  >
                                    Enable
                                  </Button>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Warning banner */}
                      {apis.length > 0 && !allApisValid && (
                        <div className="mx-5 mb-5 bg-amber-500/10 border border-amber-500/20 rounded-lg p-3">
                          <p className="text-[10px] text-amber-600 dark:text-amber-500">
                            <strong>Warning:</strong> Some required APIs are not enabled. Deployment may fail.
                          </p>
                        </div>
                      )}

                      {/* Danger zone */}
                      <div className="border-t border-[var(--border-color)] p-5">
                        {!isDetachTarget ? (
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-[10px] h-7 border-red-500/30 text-red-500 hover:bg-red-500/10 hover:text-red-500"
                            onClick={() => {
                              setDetachEnv(envKey);
                              setDetachConfirmText("");
                              setDetachError(null);
                            }}
                          >
                            <Trash2 className="h-3 w-3 mr-1.5" />
                            Disconnect
                          </Button>
                        ) : (
                          <div className="space-y-3">
                            <p className="text-[10px] text-[var(--text-secondary)]">
                              Type <strong className="text-red-500">DISCONNECT</strong> to confirm:
                            </p>
                            <Input
                              value={detachConfirmText}
                              onChange={(e) => setDetachConfirmText(e.target.value)}
                              placeholder="Type DISCONNECT"
                              className={cn(
                                "h-8 text-xs bg-[var(--bg-primary)] text-[var(--text-primary)]",
                                detachError
                                  ? "border-red-500 focus:ring-red-500"
                                  : "border-red-500/30 focus:border-red-500 focus:ring-red-500/20"
                              )}
                            />
                            {detachError && (
                              <p className="text-[10px] text-red-500">{detachError}</p>
                            )}
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-[10px] h-7 border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                                onClick={() => setDetachEnv(null)}
                                disabled={isDetaching}
                              >
                                Cancel
                              </Button>
                              <Button
                                size="sm"
                                variant="destructive"
                                className="text-[10px] h-7 bg-red-500 hover:bg-red-600 text-white"
                                onClick={() => handleDetach(envKey)}
                                disabled={detachConfirmText !== "DISCONNECT" || isDetaching}
                              >
                                {isDetaching ? (
                                  <>
                                    <Spinner className="h-3 w-3 mr-1" />
                                    <span className="shimmer-text">Disconnecting</span>
                                  </>
                                ) : (
                                  "Disconnect"
                                )}
                              </Button>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Add another cloud provider */}
          {onAddCloudProvider && (
            <div className="flex items-center gap-3 pt-3 border-t border-[var(--border-color)]">
              <p className="text-xs text-[var(--text-secondary)] flex-1">
                Need to connect another cloud?
              </p>
              <Button
                size="sm"
                variant="outline"
                onClick={onAddCloudProvider}
                className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
              >
                <Cloud className="h-3.5 w-3.5 mr-1.5" />
                Add cloud provider
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Connect dialog */}
      <GCPConnectMethodDialog
        open={showGcpConnectDialog}
        onOpenChange={setShowGcpConnectDialog}
        userId={userId}
        environment={connectEnv}
        onEnvironmentChange={setConnectEnv}
        environmentOptions={[...GCP_ENV_OPTIONS]}
        projectId={projectId}
        workspaces={workspaces}
        repoFullName={repoFullName}
        repos={repos}
      />

      {/* Edit Connection Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
              Edit Connection
            </DialogTitle>
            <DialogDescription className="text-xs text-[var(--text-secondary)]">
              Update the environment label or default region.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 pt-2">
            <div>
              <label className="text-xs font-medium text-[var(--text-secondary)] mb-1.5 block">
                Environment
              </label>
              <Select value={editEnvironment} onValueChange={setEditEnvironment}>
                <SelectTrigger className="h-9 text-xs bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
                  {GCP_ENV_OPTIONS.map((o) => {
                    const currentEnv = editingConnection?.environment ?? editEnvKey;
                    const taken = connectedEnvKeys.has(o.value) && o.value !== currentEnv;
                    return (
                      <SelectItem
                        key={o.value}
                        value={o.value}
                        disabled={taken}
                        className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]"
                      >
                        {o.label}{taken ? " (in use)" : ""}
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="text-xs font-medium text-[var(--text-secondary)] mb-1.5 block">
                Default Region
              </label>
              <Select value={editRegion} onValueChange={setEditRegion}>
                <SelectTrigger className="h-9 text-xs bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
                  {GCP_REGION_OPTIONS.map((r) => (
                    <SelectItem
                      key={r.value}
                      value={r.value}
                      className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]"
                    >
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {editError && (
              <p className="text-[10px] text-red-500">{editError}</p>
            )}

            <div className="flex gap-2 pt-2 border-t border-[var(--border-color)]">
              <Button
                variant="outline"
                size="sm"
                className="flex-1 text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                onClick={() => setEditDialogOpen(false)}
                disabled={isSavingEdit}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                className="flex-1 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
                onClick={handleSaveEdit}
                disabled={isSavingEdit || !editHasChanges()}
              >
                {isSavingEdit ? (
                  <>
                    <Spinner className="h-3 w-3 mr-1.5" />
                    Saving…
                  </>
                ) : (
                  "Save"
                )}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
