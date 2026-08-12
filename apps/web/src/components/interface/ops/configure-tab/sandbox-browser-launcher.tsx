"use client";

/**
 * SandboxBrowserLauncher — handles the localhost browser-capture flow.
 *
 * When the user clicks "Launch browser" on a localhost environment, this
 * component:
 *   1. Calls the sandbox-launch/start endpoint
 *   2. Polls sandbox-launch/status until services are ready
 *   3. Hands the preview URL off to SteelAppBrowserDialog
 *
 * The rest of the capture flow (Steel iframe → sign in → capture) is
 * identical to the normal (non-localhost) path.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  CheckCircle2,
  Loader2,
  Monitor,
  Server,
  Terminal,
  XCircle,
} from "lucide-react";
import { SteelAppBrowserDialog } from "./steel-app-browser-dialog";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type SandboxPhase =
  | "idle"
  | "pending"
  | "creating_sandbox"
  | "cloning_repo"
  | "injecting_env"
  | "starting_services"
  | "ready"
  | "failed"
  | "stopped";

interface ServiceStatus {
  name: string;
  port: number;
  ready: boolean;
  preview_url: string;
  error: string;
}

const PHASE_LABELS: Record<SandboxPhase, string> = {
  idle: "Preparing…",
  pending: "Preparing…",
  creating_sandbox: "Creating sandbox…",
  cloning_repo: "Cloning repository…",
  injecting_env: "Setting up environment…",
  starting_services: "Starting services…",
  ready: "Services are ready!",
  failed: "Launch failed",
  stopped: "Sandbox stopped",
};

const PHASE_ORDER: SandboxPhase[] = [
  "creating_sandbox",
  "cloning_repo",
  "injecting_env",
  "starting_services",
  "ready",
];

interface SandboxBrowserLauncherProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
  targetUrl: string;
  environmentLabel?: string | null;
  onCaptureComplete?: (result: {
    connected: boolean;
    cookies_count: number;
    has_local_storage: boolean;
    app_base_url?: string;
    captured_at?: string;
  }) => void;
}

export function SandboxBrowserLauncher({
  open,
  onOpenChange,
  projectId,
  targetUrl,
  environmentLabel = null,
  onCaptureComplete,
}: SandboxBrowserLauncherProps) {
  const [phase, setPhase] = useState<SandboxPhase>("idle");
  const [phaseMessage, setPhaseMessage] = useState("");
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [launchId, setLaunchId] = useState<string | null>(null);
  const [browserOpen, setBrowserOpen] = useState(false);
  const [selectedPreviewUrl, setSelectedPreviewUrl] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const launchingRef = useRef(false);

  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const cleanup = useCallback(() => {
    clearPoll();
    abortRef.current?.abort();
    abortRef.current = null;
  }, [clearPoll]);

  const stopSandbox = useCallback(async () => {
    if (!launchId || !projectId) return;
    try {
      await fetch(
        `${API_URL}/api/projects/${projectId}/app-session/sandbox-launch/stop?launch_id=${encodeURIComponent(launchId)}`,
        { method: "POST", credentials: "include" }
      );
    } catch {
      // best-effort
    }
  }, [launchId, projectId]);

  const handleClose = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        cleanup();
        launchingRef.current = false;
        if (phase !== "ready" && phase !== "failed" && phase !== "stopped" && phase !== "idle") {
          void stopSandbox();
        }
        setPhase("idle");
        setPhaseMessage("");
        setServices([]);
        setError(null);
        setLaunchId(null);
        setSelectedPreviewUrl(null);
      }
      onOpenChange(nextOpen);
    },
    [cleanup, onOpenChange, phase, stopSandbox]
  );

  const startLaunch = useCallback(async () => {
    if (!projectId || launchingRef.current) return;
    launchingRef.current = true;
    cleanup();
    setPhase("pending");
    setError(null);
    setServices([]);

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const res = await fetch(
        `${API_URL}/api/projects/${projectId}/app-session/sandbox-launch/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: targetUrl }),
          credentials: "include",
          signal: abort.signal,
        }
      );

      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(data.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      const id = data.launch_id as string;
      setLaunchId(id);
      setPhase((data.phase as SandboxPhase) || "pending");

      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await fetch(
            `${API_URL}/api/projects/${projectId}/app-session/sandbox-launch/status?launch_id=${encodeURIComponent(id)}`,
            { credentials: "include", signal: abort.signal }
          );
          if (!statusRes.ok) return;
          const status = await statusRes.json();

          setPhase(status.phase as SandboxPhase);
          setPhaseMessage(status.phase_message || "");
          if (status.services?.length) {
            setServices(status.services);
          }
          if (status.error) {
            setError(status.error);
          }

          if (status.phase === "ready" || status.phase === "failed" || status.phase === "stopped") {
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
          }
        } catch {
          // ignore poll errors (abort, network)
        }
      }, 2000);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setPhase("failed");
    } finally {
      launchingRef.current = false;
    }
  }, [projectId, targetUrl, cleanup]);

  useEffect(() => {
    if (open && phase === "idle" && projectId) {
      void startLaunch();
    }
    // No cleanup here: the poll interval and abort controller are ref-managed.
    // Cleanup happens in handleClose (user closes dialog) and when the poll
    // detects a terminal state. Returning cleanup here would break under
    // React Strict Mode's double-mount cycle.
  }, [open, phase, projectId, startLaunch]);

  const readyServices = services.filter((s) => s.ready && s.preview_url);

  const handleOpenBrowser = useCallback(
    (previewUrl: string) => {
      setSelectedPreviewUrl(previewUrl);
      setBrowserOpen(true);
    },
    []
  );

  const handleCaptureComplete = useCallback(
    (result: {
      connected: boolean;
      cookies_count: number;
      has_local_storage: boolean;
      app_base_url?: string;
      captured_at?: string;
    }) => {
      setBrowserOpen(false);
      // Override app_base_url with the original localhost URL so the session
      // is stored under the correct origin key.
      onCaptureComplete?.({
        ...result,
        app_base_url: targetUrl,
      });
      void stopSandbox();
      handleClose(false);
    },
    [onCaptureComplete, targetUrl, stopSandbox, handleClose]
  );

  const currentPhaseIndex = PHASE_ORDER.indexOf(phase);

  return (
    <>
      <Dialog open={open && !browserOpen} onOpenChange={handleClose}>
        <DialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] sm:max-w-lg gap-0 p-0 overflow-hidden text-[var(--text-primary)] shadow-lg">
          <DialogHeader className="px-5 pt-5 pb-3 border-b border-[var(--border-color)]">
            <DialogTitle className="text-base font-semibold text-[var(--text-primary)] flex items-center gap-2">
              <Terminal className="h-4 w-4 text-amber-500" />
              {environmentLabel
                ? `Launching ${environmentLabel} sandbox`
                : "Launching dev sandbox"}
            </DialogTitle>
            <p className="text-[11px] text-[var(--text-secondary)] mt-1">
              Starting your app in a cloud sandbox so you can sign in via browser.
            </p>
          </DialogHeader>

          <div className="px-5 py-4 space-y-4">
            {/* Phase progress */}
            <div className="space-y-2">
              {PHASE_ORDER.slice(0, -1).map((p, i) => {
                const isCurrent = p === phase;
                const isDone = currentPhaseIndex > i;
                const isFuture = currentPhaseIndex < i;

                return (
                  <div
                    key={p}
                    className={cn(
                      "flex items-center gap-2.5 text-xs py-1 transition-opacity",
                      isFuture && "opacity-35"
                    )}
                  >
                    {isDone ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                    ) : isCurrent ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-500 shrink-0" />
                    ) : (
                      <div className="h-3.5 w-3.5 rounded-full border border-[var(--border-color)] shrink-0" />
                    )}
                    <span
                      className={cn(
                        "text-[var(--text-secondary)]",
                        isCurrent && "text-[var(--text-primary)] font-medium"
                      )}
                    >
                      {PHASE_LABELS[p]}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Status message */}
            {phaseMessage && phase !== "ready" && phase !== "failed" && (
              <p className="text-[10px] text-[var(--text-secondary)] bg-[var(--bg-secondary)] rounded px-2 py-1.5 font-mono">
                {phaseMessage}
              </p>
            )}

            {/* Error */}
            {error && (
              <div className="flex items-start gap-2 text-xs text-red-500 bg-red-500/10 rounded-md px-3 py-2">
                <XCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                <span className="break-all">{error}</span>
              </div>
            )}

            {/* Ready — show services */}
            {phase === "ready" && readyServices.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                  <CheckCircle2 className="h-4 w-4" />
                  Services are running — choose one to open in the browser:
                </div>
                <div className="space-y-1.5">
                  {readyServices.map((svc) => (
                    <button
                      key={svc.port}
                      type="button"
                      onClick={() => handleOpenBrowser(svc.preview_url)}
                      className={cn(
                        "w-full flex items-center gap-3 rounded-md border border-[var(--border-color)] px-3 py-2.5",
                        "bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] transition-colors text-left"
                      )}
                    >
                      <div className="flex items-center justify-center w-8 h-8 rounded bg-primary/10 border border-primary/20 shrink-0">
                        {svc.port === 3000 || svc.port === 5173 ? (
                          <Monitor className="h-4 w-4 text-primary" />
                        ) : (
                          <Server className="h-4 w-4 text-primary" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-[var(--text-primary)] truncate">
                          {svc.name}
                        </p>
                        <p className="text-[10px] text-[var(--text-secondary)] font-mono truncate">
                          port {svc.port}
                        </p>
                      </div>
                      <span className="text-[10px] text-primary font-medium shrink-0">
                        Open →
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-2 border-t border-[var(--border-color)] bg-[var(--bg-secondary)]/50 px-5 py-3">
            {phase === "failed" ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs"
                  onClick={() => handleClose(false)}
                >
                  Close
                </Button>
                <Button
                  size="sm"
                  className="text-xs"
                  onClick={() => {
                    setPhase("idle");
                    setError(null);
                    void startLaunch();
                  }}
                >
                  Retry
                </Button>
              </>
            ) : (
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => handleClose(false)}
              >
                Cancel
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Once the user picks a service, open the normal Steel browser dialog */}
      <SteelAppBrowserDialog
        open={browserOpen}
        onOpenChange={(next) => {
          setBrowserOpen(next);
          if (!next && phase === "ready") {
            // User closed browser dialog without capturing — keep sandbox alive
            // so they can re-pick a service
          }
        }}
        projectId={projectId}
        targetUrl={selectedPreviewUrl || ""}
        environmentLabel={environmentLabel}
        onCaptureComplete={handleCaptureComplete}
      />
    </>
  );
}
