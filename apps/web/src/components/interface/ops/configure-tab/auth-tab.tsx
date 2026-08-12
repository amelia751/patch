"use client";

import { useCallback, useEffect, useState } from "react";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { Globe, Loader2, Pencil, Plus, Trash2, Unplug } from "lucide-react";
import { useProject } from "@/lib/project-context";
import { useTestGoogleSessionOptional } from "@/lib/test-google-session-context";
import { SteelAppBrowserDialog } from "./steel-app-browser-dialog";
import { SandboxBrowserLauncher } from "./sandbox-browser-launcher";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Preset environment keys for the add-environment dialog (labels stored on the project). */
const APP_BROWSER_ENV_PRESETS = [
  { value: "production", label: "Production" },
  { value: "staging", label: "Staging" },
  { value: "development", label: "Development" },
] as const;

function presetValueForLabel(label: string): string {
  const t = label.trim().toLowerCase();
  for (const p of APP_BROWSER_ENV_PRESETS) {
    if (p.label.toLowerCase() === t) return p.value;
  }
  return "";
}

const selectSurfaceTrigger = cn(
  "h-9 w-full text-sm rounded-md shadow-sm",
  "bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]",
  "data-[placeholder]:text-[var(--text-secondary)] data-[placeholder]:opacity-80",
  "focus:ring-1 focus:ring-[var(--border-color)] focus:border-[var(--text-secondary)]",
  "[&_svg]:opacity-70 [&_svg]:text-[var(--text-secondary)]"
);

const selectSurfaceContent = "bg-[var(--bg-primary)] border-[var(--border-color)]";

const selectSurfaceItem = cn(
  "text-sm text-[var(--text-primary)]",
  "focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]",
  "data-[highlighted]:bg-[var(--bg-tertiary)] data-[highlighted]:text-[var(--text-primary)]"
);

/** Inputs in add/edit flows — matches light/dark surface tokens (avoids raw shadcn bg on nested cards). */
const appBrowserFormInputClass = cn(
  "w-full rounded-md border border-[var(--border-color)] shadow-sm",
  "bg-[var(--bg-secondary)] text-[var(--text-primary)]",
  "placeholder:text-[var(--text-secondary)] placeholder:opacity-70",
  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--border-color)] focus-visible:border-[var(--text-secondary)]"
);

const appBrowserFormLabelClass = "text-xs font-medium text-[var(--text-secondary)]";

export interface AppBrowserEnv {
  id: string;
  label: string;
  url: string;
}

interface SessionEntry {
  connected: boolean;
  session_display_name?: string | null;
  app_base_url?: string | null;
  captured_at?: string | null;
}

function isLocalhostUrl(url: string): boolean {
  try {
    const host = new URL(url.trim()).hostname.toLowerCase();
    return host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0" || host === "::1";
  } catch {
    return false;
  }
}

function tryOrigin(url: string): string | null {
  try {
    return new URL(url.trim()).origin;
  } catch {
    return null;
  }
}

function sessionMatchesEnv(
  appBaseUrl: string | null | undefined,
  envUrl: string
): boolean {
  if (!appBaseUrl?.trim()) return false;
  const a = tryOrigin(appBaseUrl);
  const b = tryOrigin(envUrl);
  if (!a || !b) return false;
  return a === b;
}

/** Accepts full URLs or bare hosts (e.g. eduro.live → https://eduro.live).
 *  Localhost-ish hosts default to http:// instead of https://. */
function normalizeAppBrowserUrl(raw: string): string | null {
  const u = raw.trim();
  if (!u) return null;
  let candidate = u;
  if (candidate.startsWith("//")) {
    candidate = `https:${candidate}`;
  } else if (!/^https?:\/\//i.test(candidate)) {
    const isLocal = /^(localhost|127\.0\.0\.1|0\.0\.0\.0|::1)(:\d+)?$/i.test(candidate);
    candidate = isLocal ? `http://${candidate}` : `https://${candidate}`;
  }
  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    if (!parsed.host) return null;
    return candidate;
  } catch {
    return null;
  }
}

const DEV_DEFAULT_URL = "http://localhost";

export function AuthTab() {
  const { currentProject } = useProject();
  const testGoogleSession = useTestGoogleSessionOptional();
  const projectId = currentProject?.id ?? null;

  const [appBrowserEnvs, setAppBrowserEnvs] = useState<AppBrowserEnv[]>([]);
  const [loadingEnvs, setLoadingEnvs] = useState(false);
  const [savingEnvs, setSavingEnvs] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [addEnvPreset, setAddEnvPreset] = useState<string>("");
  const [addUrl, setAddUrl] = useState("");

  const [browserDialogOpen, setBrowserDialogOpen] = useState(false);
  const [browserTarget, setBrowserTarget] = useState<AppBrowserEnv | null>(null);

  const [sessions, setSessions] = useState<SessionEntry[]>([]);
  const [loadingSession, setLoadingSession] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [disconnectTarget, setDisconnectTarget] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftEnvPreset, setDraftEnvPreset] = useState<string>("");
  const [draftUrl, setDraftUrl] = useState("");

  const [removeEnvId, setRemoveEnvId] = useState<string | null>(null);

  const loadProjectEnvs = useCallback(async () => {
    if (!projectId) {
      setAppBrowserEnvs([]);
      return;
    }
    setLoadingEnvs(true);
    setSaveError(null);
    try {
      const res = await fetch(`${API_URL}/api/projects/${projectId}`, { credentials: "include" });
      if (!res.ok) return;
      const data = await res.json();
      const raw = data.app_browser_envs;
      if (Array.isArray(raw)) {
        setAppBrowserEnvs(
          raw
            .filter(
              (e: unknown) =>
                e &&
                typeof e === "object" &&
                typeof (e as AppBrowserEnv).id === "string" &&
                typeof (e as AppBrowserEnv).label === "string" &&
                typeof (e as AppBrowserEnv).url === "string"
            )
            .map((e: AppBrowserEnv) => ({
              id: e.id,
              label: e.label,
              url: e.url,
            }))
        );
      } else {
        setAppBrowserEnvs([]);
      }
    } catch {
      setSaveError("Could not load environments.");
    } finally {
      setLoadingEnvs(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadProjectEnvs();
  }, [loadProjectEnvs]);

  const persistEnvs = useCallback(
    async (next: AppBrowserEnv[]): Promise<boolean> => {
      if (!projectId) return false;
      setSavingEnvs(true);
      setSaveError(null);
      try {
        const res = await fetch(`${API_URL}/api/projects/${projectId}/app-browser-envs`, {
          method: "PATCH",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ envs: next }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          setSaveError(typeof err.detail === "string" ? err.detail : "Failed to save environments.");
          return false;
        }
        const data = await res.json();
        const raw = data.app_browser_envs;
        if (Array.isArray(raw)) {
          setAppBrowserEnvs(
            raw.map((e: AppBrowserEnv) => ({ id: e.id, label: e.label, url: e.url }))
          );
        }
        return true;
      } catch {
        setSaveError("Failed to save environments.");
        return false;
      } finally {
        setSavingEnvs(false);
      }
    },
    [projectId]
  );

  const fetchSession = useCallback(async () => {
    if (!projectId) {
      setSessions([]);
      return;
    }
    setLoadingSession(true);
    try {
      const res = await fetch(`${API_URL}/api/projects/${projectId}/app-session`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setSessions(Array.isArray(data.sessions) ? data.sessions : []);
      }
    } catch {
      /* silent */
    } finally {
      setLoadingSession(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  const handleCaptureComplete = useCallback(() => {
    fetchSession();
  }, [fetchSession]);

  const handleDisconnect = useCallback(async (appBaseUrl?: string | null): Promise<boolean> => {
    if (!projectId) return false;
    try {
      const qs = appBaseUrl ? `?app_base_url=${encodeURIComponent(appBaseUrl)}` : "";
      const res = await fetch(`${API_URL}/api/projects/${projectId}/app-session${qs}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!res.ok) return false;
      setSessions((prev) =>
        appBaseUrl
          ? prev.filter((s) => !sessionMatchesEnv(s.app_base_url, appBaseUrl))
          : []
      );
      return true;
    } catch {
      return false;
    }
  }, [projectId]);

  const startEdit = (env: AppBrowserEnv) => {
    setEditingId(env.id);
    setDraftEnvPreset(presetValueForLabel(env.label));
    setDraftUrl(env.url);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setDraftEnvPreset("");
    setDraftUrl("");
  };

  const saveEdit = async () => {
    if (!editingId) return;
    const preset = APP_BROWSER_ENV_PRESETS.find((p) => p.value === draftEnvPreset);
    const label = preset?.label?.trim() ?? "";
    const urlOk = normalizeAppBrowserUrl(draftUrl);
    if (!draftEnvPreset || !label) {
      setSaveError("Choose an environment.");
      return;
    }
    if (!urlOk) {
      setSaveError("Enter a valid URL or domain (https:// is added if you omit it).");
      return;
    }
    const next = appBrowserEnvs.map((e) =>
      e.id === editingId ? { ...e, label, url: urlOk } : e
    );
    const ok = await persistEnvs(next);
    if (ok) cancelEdit();
  };

  const resetAddForm = useCallback(() => {
    setAddEnvPreset("");
    setAddUrl("");
  }, []);

  const confirmAdd = async () => {
    const preset = APP_BROWSER_ENV_PRESETS.find((p) => p.value === addEnvPreset);
    const label = preset?.label?.trim() ?? "";
    const urlOk = normalizeAppBrowserUrl(addUrl);
    if (!addEnvPreset || !label) {
      setSaveError("Choose an environment.");
      return;
    }
    if (!urlOk) {
      setSaveError("Enter a valid URL or domain (https:// is added if you omit it).");
      return;
    }
    const next = [...appBrowserEnvs, { id: crypto.randomUUID(), label, url: urlOk }];
    const ok = await persistEnvs(next);
    if (ok) {
      setAddOpen(false);
      resetAddForm();
    }
  };

  const confirmRemoveEnv = async () => {
    if (!removeEnvId) return;
    const id = removeEnvId;
    const next = appBrowserEnvs.filter((e) => e.id !== id);
    const ok = await persistEnvs(next);
    if (ok) {
      setRemoveEnvId(null);
      if (editingId === id) cancelEdit();
    }
  };

  const openBrowserFor = (env: AppBrowserEnv) => {
    setBrowserTarget(env);
    setBrowserDialogOpen(true);
  };

  const findSessionForEnv = useCallback(
    (envUrl: string): SessionEntry | undefined =>
      sessions.find((s) => s.connected && sessionMatchesEnv(s.app_base_url, envUrl)),
    [sessions]
  );

  const formatCaptured = (s: SessionEntry | undefined) =>
    s?.captured_at
      ? `Captured ${new Date(s.captured_at).toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })}`
      : null;

  return (
    <>
      <AlertDialog
        open={disconnectTarget !== null}
        onOpenChange={(next) => {
          if (!disconnecting && !next) setDisconnectTarget(null);
        }}
      >
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-[var(--text-primary)]">
              Disconnect saved browser session?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-[var(--text-secondary)] leading-relaxed">
              Test runs will no longer use this captured login until you connect again. You can launch the browser and
              capture a new session anytime.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={disconnecting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={disconnecting}
              className="bg-red-500 hover:bg-red-600 text-white focus:ring-red-500 sm:mt-0 inline-flex items-center justify-center gap-2"
              onClick={(e) => {
                e.preventDefault();
                void (async () => {
                  setDisconnecting(true);
                  try {
                    const ok = await handleDisconnect(disconnectTarget);
                    if (ok) setDisconnectTarget(null);
                  } finally {
                    setDisconnecting(false);
                  }
                })();
              }}
            >
              {disconnecting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                  Disconnecting&hellip;
                </>
              ) : (
                "Disconnect"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={removeEnvId !== null}
        onOpenChange={(next) => {
          if (!next) setRemoveEnvId(null);
        }}
      >
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-[var(--text-primary)]">Remove this environment?</AlertDialogTitle>
            <AlertDialogDescription className="text-[var(--text-secondary)] leading-relaxed">
              This removes this environment card from the project. It does not delete a captured session—disconnect
              first if you want test runs to stop using that login.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-500 hover:bg-red-600 text-white focus:ring-red-500 sm:mt-0"
              onClick={(e) => {
                e.preventDefault();
                void confirmRemoveEnv();
              }}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog
        open={addOpen}
        onOpenChange={(open) => {
          setAddOpen(open);
          if (!open) resetAddForm();
        }}
      >
        <DialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] sm:max-w-md gap-0 p-0 overflow-hidden text-[var(--text-primary)] shadow-lg">
          <DialogHeader className="space-y-1 px-5 pt-5 pb-3 border-b border-[var(--border-color)] text-left">
            <DialogTitle className="text-base font-semibold text-[var(--text-primary)] pr-8">
              Add app environment
            </DialogTitle>
            <p className="text-[11px] sm:text-xs text-[var(--text-secondary)] font-normal leading-snug">
              Choose the environment, then paste the base URL you open in the browser.
            </p>
          </DialogHeader>
          <div className="grid gap-3.5 px-5 py-4">
            <div className="grid gap-1.5">
              <Label htmlFor="app-env-preset" className={appBrowserFormLabelClass}>
                Environment
              </Label>
              <Select
                value={addEnvPreset || undefined}
                onValueChange={(v) => {
                  setAddEnvPreset(v);
                  if (v === "development") {
                    setAddUrl(DEV_DEFAULT_URL);
                  } else if (addUrl === DEV_DEFAULT_URL) {
                    setAddUrl("");
                  }
                }}
              >
                <SelectTrigger id="app-env-preset" className={selectSurfaceTrigger}>
                  <SelectValue placeholder="Choose environment" />
                </SelectTrigger>
                <SelectContent className={selectSurfaceContent}>
                  {APP_BROWSER_ENV_PRESETS.map((p) => (
                    <SelectItem key={p.value} value={p.value} className={selectSurfaceItem}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {addEnvPreset === "development" ? (
              <p className="text-[11px] text-[var(--text-secondary)] bg-[var(--bg-secondary)] rounded px-2.5 py-2 leading-relaxed">
                We'll clone your repo into a cloud sandbox, auto-detect services &amp; ports, and
                start them for you — no URL needed.
              </p>
            ) : (
              <div className="grid gap-1.5">
                <Label htmlFor="app-env-url" className={appBrowserFormLabelClass}>
                  App URL
                </Label>
                <Input
                  id="app-env-url"
                  placeholder="https://app.example.com"
                  value={addUrl}
                  onChange={(e) => setAddUrl(e.target.value)}
                  className={cn(appBrowserFormInputClass, "h-9 text-sm font-mono")}
                />
              </div>
            )}
          </div>
          <DialogFooter className="flex flex-row flex-wrap justify-end gap-2 border-t border-[var(--border-color)] bg-[var(--bg-secondary)]/50 px-5 py-3 sm:space-x-0">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setAddOpen(false)}
              className="text-xs border-[var(--border-color)] bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm hover:!bg-[var(--bg-tertiary)] hover:!text-[var(--text-primary)]"
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => void confirmAdd()}
              disabled={savingEnvs}
              className="text-xs bg-primary text-primary-foreground shadow-sm hover:bg-primary/90"
            >
              {savingEnvs ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="h-full overflow-y-auto bg-[var(--bg-primary)]">
        <div className="w-full mx-auto p-3 sm:p-4 md:p-6 space-y-4 sm:space-y-6">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Test user sign-in</h2>
            <div className="mt-1 max-w-xl space-y-1.5">
              <p className="text-xs text-[var(--text-secondary)]">
                For features behind login, tests need a real session—same as opening your app in a browser while signed
                in. Connect once here; we store it for this project only and you can disconnect anytime.
              </p>
              {testGoogleSession ? (
                <button
                  type="button"
                  onClick={() => testGoogleSession.openTestSignInLearnMore()}
                  className="text-xs font-medium text-primary hover:underline underline-offset-2"
                >
                  Learn more
                </button>
              ) : null}
            </div>
          </div>

          {saveError && (
            <p className="text-xs text-red-600 dark:text-red-400 max-w-xl" role="alert">
              {saveError}
            </p>
          )}

          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 220px), 1fr))" }}
          >
            {loadingEnvs ? (
              <div className="flex items-center gap-2 text-[var(--text-secondary)] text-xs py-6 col-span-full">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading environments&hellip;
              </div>
            ) : (
              <>
                {appBrowserEnvs.map((env) => {
                  const isEditing = editingId === env.id;
                  const envSession = findSessionForEnv(env.url);
                  const envConnected = !!envSession;
                  const capturedLabel = formatCaptured(envSession);
                  return (
                    <div
                      key={env.id}
                      className="group relative bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg py-3 pl-3 pr-9 text-left sm:py-4 sm:pl-4 sm:pr-10"
                    >
                      <button
                        type="button"
                        disabled={savingEnvs}
                        title="Remove environment"
                        aria-label={`Remove ${env.label} environment`}
                        onClick={() => setRemoveEnvId(env.id)}
                        className={cn(
                          "absolute right-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-md",
                          "border border-[var(--border-color)] bg-[var(--bg-primary)] text-[var(--text-secondary)] shadow-sm",
                          "opacity-0 pointer-events-none transition-opacity duration-150",
                          "group-hover:pointer-events-auto group-hover:opacity-100",
                          "hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-600 dark:hover:text-red-400",
                          "focus-visible:pointer-events-auto focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/35",
                          "disabled:pointer-events-none disabled:opacity-30"
                        )}
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden />
                      </button>
                      <div className="flex items-center gap-2 sm:gap-3 mb-2 sm:mb-3">
                        <div className="flex items-center justify-center w-7 h-7 sm:w-8 sm:h-8 rounded-md bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-blue-500/20">
                          <Globe className="h-4 w-4 text-blue-500" aria-hidden />
                        </div>
                      </div>
                      {isEditing ? (
                        <div className="mb-3 space-y-2.5 rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)] p-2.5">
                          <div className="grid gap-1.5">
                            <Label htmlFor={`env-preset-${env.id}`} className={appBrowserFormLabelClass}>
                              Environment
                            </Label>
                            <Select
                              value={draftEnvPreset || undefined}
                              onValueChange={setDraftEnvPreset}
                            >
                              <SelectTrigger
                                id={`env-preset-${env.id}`}
                                className={cn(selectSurfaceTrigger, "h-8 text-xs")}
                              >
                                <SelectValue placeholder="Choose environment" />
                              </SelectTrigger>
                              <SelectContent className={selectSurfaceContent}>
                                {APP_BROWSER_ENV_PRESETS.map((p) => (
                                  <SelectItem key={p.value} value={p.value} className={cn(selectSurfaceItem, "text-xs")}>
                                    {p.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          {isLocalhostUrl(draftUrl) ? (
                            <p className="text-[11px] text-[var(--text-secondary)] bg-[var(--bg-secondary)] rounded px-2 py-1.5 leading-relaxed">
                              Services are auto-detected from your repository.
                            </p>
                          ) : (
                            <div className="grid gap-1.5">
                              <Label htmlFor={`env-url-${env.id}`} className={appBrowserFormLabelClass}>
                                App URL
                              </Label>
                              <div
                                className={cn(envConnected && "cursor-not-allowed rounded-md")}
                                title={
                                  envConnected
                                    ? "Disconnect above to edit this URL. You can still change the environment label."
                                    : undefined
                                }
                              >
                                <Input
                                  id={`env-url-${env.id}`}
                                  value={draftUrl}
                                  onChange={(e) => setDraftUrl(e.target.value)}
                                  disabled={envConnected}
                                  className={cn(
                                    appBrowserFormInputClass,
                                    "h-8 text-xs font-mono",
                                    envConnected && "pointer-events-none opacity-80"
                                  )}
                                />
                              </div>
                            </div>
                          )}
                          <div className="flex flex-wrap gap-1.5 border-t border-[var(--border-color)] pt-2.5">
                            <Button
                              type="button"
                              size="sm"
                              className="h-7 text-[10px] bg-primary text-primary-foreground shadow-sm hover:bg-primary/90"
                              disabled={savingEnvs}
                              onClick={() => void saveEdit()}
                            >
                              Save
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-7 text-[10px] border-[var(--border-color)] bg-[var(--bg-secondary)] text-[var(--text-primary)] shadow-sm hover:!bg-[var(--bg-tertiary)] hover:!text-[var(--text-primary)]"
                              disabled={savingEnvs}
                              onClick={cancelEdit}
                            >
                              Cancel
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="flex items-start justify-between gap-1 mb-1 min-w-0">
                            <h3 className="text-xs sm:text-sm font-medium text-[var(--text-primary)] leading-snug flex-1 min-w-0">
                              {env.label}
                            </h3>
                            {envConnected ? (
                              <button
                                type="button"
                                className="shrink-0 p-0.5 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                                title="Edit environment name"
                                onClick={() => startEdit(env)}
                                disabled={savingEnvs}
                              >
                                <Pencil className="h-3.5 w-3.5" aria-hidden />
                              </button>
                            ) : null}
                          </div>
                          {isLocalhostUrl(env.url) ? (
                            <p className="text-[10px] text-[var(--text-secondary)] mb-1 min-w-0">
                              Auto-detected from your repository
                            </p>
                          ) : (
                            <div
                              className={cn(
                                "flex items-start gap-1 mb-1 min-w-0 rounded",
                                envConnected && "cursor-not-allowed"
                              )}
                              title={
                                envConnected
                                  ? "Disconnect this session before you can change the app URL."
                                  : undefined
                              }
                            >
                              <p className="text-[10px] text-[var(--text-secondary)] truncate flex-1 min-w-0 font-mono">
                                {env.url}
                              </p>
                              {!envConnected ? (
                                <button
                                  type="button"
                                  className="shrink-0 p-0.5 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                                  title="Edit environment and URL"
                                  onClick={() => startEdit(env)}
                                  disabled={savingEnvs}
                                >
                                  <Pencil className="h-3.5 w-3.5" aria-hidden />
                                </button>
                              ) : null}
                            </div>
                          )}
                          {loadingSession ? (
                            <div className="flex items-center gap-1.5 mb-3 mt-1">
                              <Loader2 className="h-3 w-3 animate-spin text-[var(--text-secondary)]" />
                              <span className="text-[10px] text-[var(--text-secondary)]">Checking…</span>
                            </div>
                          ) : envConnected ? (
                            <>
                              <Badge
                                variant="outline"
                                className="text-[9px] mb-2 bg-[#10b981]/10 text-[#10b981] border-[#10b981]/30"
                              >
                                connected
                              </Badge>
                              <div className="space-y-1 mb-3">
                                {capturedLabel && (
                                  <p className="text-[10px] text-[var(--text-secondary)]">{capturedLabel}</p>
                                )}
                                {envSession?.session_display_name && (
                                  <p
                                    className="text-[10px] text-[var(--text-secondary)] truncate"
                                    title={envSession.session_display_name ?? undefined}
                                  >
                                    {envSession.session_display_name}
                                  </p>
                                )}
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="w-full text-xs h-8 border-[var(--border-color)] text-[var(--text-secondary)] hover:text-red-500 hover:border-red-500/30"
                                  onClick={() => setDisconnectTarget(env.url)}
                                >
                                  <Unplug className="h-3.5 w-3.5 mr-1.5" />
                                  Disconnect
                                </Button>
                                <button
                                  type="button"
                                  className="text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] underline-offset-2 hover:underline transition-colors text-left"
                                  onClick={() => openBrowserFor(env)}
                                >
                                  Recapture session
                                </button>
                              </div>
                            </>
                          ) : (
                            <>
                              <Badge
                                variant="outline"
                                className="text-[9px] mb-3 bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border-[var(--border-color)]"
                              >
                                not connected
                              </Badge>
                              <Button
                                type="button"
                                size="sm"
                                className="w-full text-xs h-8"
                                onClick={() => openBrowserFor(env)}
                              >
                                Launch browser
                              </Button>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  );
                })}

                <button
                  type="button"
                  onClick={() => {
                    setSaveError(null);
                    resetAddForm();
                    setAddOpen(true);
                  }}
                  disabled={!projectId || savingEnvs}
                  className={cn(
                    "rounded-lg border border-dashed border-[var(--border-color)] bg-transparent",
                    "p-3 sm:p-4 min-h-[140px] flex flex-col items-center justify-center gap-2",
                    "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]/50",
                    "transition-colors disabled:opacity-40 disabled:pointer-events-none"
                  )}
                >
                  <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[var(--bg-tertiary)] border border-[var(--border-color)]">
                    <Plus className="h-4 w-4" aria-hidden />
                  </div>
                  <span className="text-xs font-medium">Add environment</span>
                  <span className="text-[10px] text-center text-[var(--text-secondary)] px-1">
                    Name + URL for production, staging, or development
                  </span>
                </button>
              </>
            )}
          </div>

          {!loadingEnvs && appBrowserEnvs.length === 0 && projectId && (
            <p className="text-[10px] text-[var(--text-secondary)] max-w-md">
              No environments yet. Use <span className="font-medium text-[var(--text-primary)]">Add environment</span>{" "}
              to save the URLs you sign in against.
            </p>
          )}
        </div>
      </div>

      {browserTarget && isLocalhostUrl(browserTarget.url) ? (
        <SandboxBrowserLauncher
          open={browserDialogOpen && browserTarget !== null}
          onOpenChange={(open) => {
            setBrowserDialogOpen(open);
            if (!open) setBrowserTarget(null);
          }}
          projectId={projectId}
          targetUrl={browserTarget.url}
          environmentLabel={browserTarget.label ?? null}
          onCaptureComplete={handleCaptureComplete}
        />
      ) : (
        <SteelAppBrowserDialog
          open={browserDialogOpen && browserTarget !== null}
          onOpenChange={(open) => {
            setBrowserDialogOpen(open);
            if (!open) setBrowserTarget(null);
          }}
          projectId={projectId}
          targetUrl={browserTarget?.url ?? ""}
          environmentLabel={browserTarget?.label ?? null}
          onCaptureComplete={handleCaptureComplete}
        />
      )}
    </>
  );
}
