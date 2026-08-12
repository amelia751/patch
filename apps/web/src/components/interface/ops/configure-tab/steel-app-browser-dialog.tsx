"use client";

import Image from "next/image";
import { useCallback, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CheckCircle2, Globe, Loader2, X } from "lucide-react";
import { LOGIN_ASSET } from "./google-test-connect-dialog";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Outline actions on themed dialog chrome — overrides shadcn outline hover (accent) for light/dark. */
const steelDialogOutlineButtonClass = cn(
  "text-xs shadow-sm",
  "border-[var(--border-color)] !bg-[var(--bg-primary)] !text-[var(--text-primary)]",
  "hover:!bg-[var(--bg-tertiary)] hover:!text-[var(--text-primary)]",
  "focus-visible:ring-1 focus-visible:ring-[var(--border-color)]"
);

const steelDialogPrimaryButtonClass =
  "text-xs bg-primary text-primary-foreground shadow-sm hover:bg-primary/90";

export type BrowserCaptureStatus = "idle" | "launching" | "live" | "capturing" | "done" | "error";

interface SteelAppBrowserDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
  targetUrl: string;
  /** Shown in the header (e.g. "Production", "Staging") when set. */
  environmentLabel?: string | null;
  onCaptureComplete?: (result: {
    connected: boolean;
    cookies_count: number;
    has_local_storage: boolean;
    app_base_url?: string;
    captured_at?: string;
  }) => void;
}

export function SteelAppBrowserDialog({
  open,
  onOpenChange,
  projectId,
  targetUrl,
  environmentLabel = null,
  onCaptureComplete,
}: SteelAppBrowserDialogProps) {
  const [status, setStatus] = useState<BrowserCaptureStatus>("idle");
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [captureResult, setCaptureResult] = useState<{
    cookies_count: number;
    has_local_storage: boolean;
    app_base_url?: string;
  } | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    setStatus("idle");
    setViewerUrl(null);
    setSessionId(null);
    setError(null);
    setCaptureResult(null);
  }, []);

  const launchSession = useCallback(async () => {
    if (!projectId || !targetUrl.trim()) return;
    setStatus("launching");
    setError(null);

    try {
      abortRef.current = new AbortController();
      const res = await fetch(
        `${API_URL}/api/projects/${projectId}/app-session/browser-capture/start`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: targetUrl }),
          signal: abortRef.current.signal,
        }
      );
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `Failed to launch browser (${res.status})`);
      }
      const data = await res.json();
      setSessionId(data.session_id);
      setViewerUrl(data.session_viewer_url);
      setStatus("live");
    } catch (e: any) {
      if (e.name === "AbortError") return;
      setError(e.message || "Failed to launch browser session");
      setStatus("error");
    }
  }, [projectId, targetUrl]);

  const captureAndFinish = useCallback(async () => {
    if (!projectId || !sessionId) return;
    setStatus("capturing");

    try {
      const res = await fetch(
        `${API_URL}/api/projects/${projectId}/app-session/browser-capture/complete?session_id=${encodeURIComponent(sessionId)}`,
        { method: "POST", credentials: "include" }
      );
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `Capture failed (${res.status})`);
      }
      const data = await res.json();
      setCaptureResult({
        cookies_count: data.cookies_count,
        has_local_storage: data.has_local_storage,
        app_base_url: data.app_base_url,
      });
      setStatus("done");
      onCaptureComplete?.({
        connected: data.connected,
        cookies_count: data.cookies_count,
        has_local_storage: data.has_local_storage,
        app_base_url: data.app_base_url,
        captured_at: data.captured_at,
      });
    } catch (e: any) {
      setError(e.message || "Failed to capture session");
      setStatus("error");
    }
  }, [projectId, sessionId, onCaptureComplete]);

  const cancelSession = useCallback(async () => {
    if (sessionId && projectId) {
      try {
        await fetch(
          `${API_URL}/api/projects/${projectId}/app-session/browser-capture/cancel?session_id=${encodeURIComponent(sessionId)}`,
          { method: "POST", credentials: "include" }
        );
      } catch {
        /* best-effort cleanup */
      }
    }
    abortRef.current?.abort();
    reset();
    onOpenChange(false);
  }, [sessionId, projectId, reset, onOpenChange]);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (!next && (status === "live" || status === "launching")) {
        cancelSession();
        return;
      }
      if (!next) {
        reset();
      }
      onOpenChange(next);
    },
    [status, cancelSession, reset, onOpenChange]
  );

  const expandedChrome = status === "live" || status === "capturing";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className={
          expandedChrome
            ? "bg-[var(--bg-primary)] border-[var(--border-color)] max-w-4xl w-[95vw] h-[85vh] max-h-[85vh] gap-0 p-0 overflow-hidden flex flex-col"
            : "bg-[var(--bg-primary)] border-[var(--border-color)] max-w-sm gap-0 p-0 overflow-hidden flex flex-col"
        }
      >
        <DialogHeader
          className={
            expandedChrome
              ? "px-5 pt-4 pb-3 border-b border-[var(--border-color)] text-left space-y-0 flex-shrink-0"
              : "px-5 pt-5 pb-3 border-b border-[var(--border-color)] text-left space-y-1.5"
          }
        >
          <div className="flex items-center justify-between gap-2">
            <DialogTitle className="text-sm sm:text-base font-semibold text-[var(--text-primary)]">
              {expandedChrome ? (
                <span className="flex flex-col gap-0.5 items-start min-w-0">
                  <span className="flex items-center gap-2 min-w-0">
                    <Globe className="h-4 w-4 shrink-0 text-[var(--text-secondary)]" aria-hidden />
                    <span className="truncate">
                      {environmentLabel ? (
                        <>
                          <span className="text-[var(--text-secondary)] font-medium">{environmentLabel}</span>
                          <span className="text-[var(--text-secondary)]"> · </span>
                        </>
                      ) : null}
                      <span className="break-all">{targetUrl}</span>
                    </span>
                  </span>
                </span>
              ) : (
                "Remote browser sign-in"
              )}
            </DialogTitle>
            {status === "live" && (
              <div className="flex items-center gap-1.5 mr-8 shrink-0">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
                </span>
                <span className="text-[10px] text-green-600 dark:text-green-400 font-medium">Live</span>
              </div>
            )}
          </div>
          {!expandedChrome && status === "idle" && (
            <div className="space-y-1 pr-8">
              {environmentLabel ? (
                <p className="text-[10px] sm:text-xs text-[var(--text-primary)] font-medium">
                  Environment · {environmentLabel}
                </p>
              ) : null}
              <p className="text-[10px] sm:text-xs text-[var(--text-secondary)] font-normal leading-snug">
                A real browser in the cloud. Sign in once; we encrypt and store the session for this project only.
              </p>
            </div>
          )}
        </DialogHeader>

        <div className={expandedChrome ? "flex-1 min-h-0 relative" : "relative"}>
          {status === "idle" && (
            <div className="px-5 py-5 flex flex-col gap-3">
              <div className="relative mx-auto w-full max-w-[240px] aspect-[5/4] overflow-hidden shrink-0">
                <Image
                  src={LOGIN_ASSET("secure-browser.png")}
                  alt="Remote browser for sign-in"
                  fill
                  sizes="240px"
                  quality={95}
                  className="object-cover object-center"
                />
              </div>
              <div>
                <h3 className="text-sm font-medium text-[var(--text-primary)] mb-1.5">Use your app’s real login</h3>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                  After you launch, you’ll see{" "}
                  <span className="font-medium text-[var(--text-primary)]">{targetUrl}</span> in a live browser. Go
                  through whatever flow you normally use—password, SSO, OAuth, magic links—then tap Capture Session.
                  Sandbox runs replay that logged-in state.
                </p>
              </div>
            </div>
          )}

          {status === "launching" && (
            <div className="flex flex-col items-center gap-2.5 px-5 py-10">
              <Loader2 className="h-6 w-6 animate-spin text-[var(--text-secondary)]" aria-hidden />
              <p className="text-[11px] text-[var(--text-secondary)]">Starting browser session&hellip;</p>
            </div>
          )}

          {status === "live" && viewerUrl && (
            <iframe
              src={viewerUrl}
              title="App browser"
              className="w-full h-full border-0"
              allow="clipboard-read; clipboard-write"
            />
          )}

          {status === "capturing" && (
            <div className="flex flex-col items-center justify-center min-h-[min(50vh,320px)] gap-3 py-8">
              <Loader2 className="h-6 w-6 animate-spin text-[var(--text-secondary)]" aria-hidden />
              <p className="text-xs text-[var(--text-secondary)]">Capturing session data&hellip;</p>
            </div>
          )}

          {status === "done" && captureResult && (
            <div className="px-5 py-5 flex flex-col gap-3">
              <div className="flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/5 p-3">
                <CheckCircle2 className="h-4 w-4 text-[#10b981] flex-shrink-0" aria-hidden />
                <div>
                  <p className="text-sm font-medium text-[var(--text-primary)]">Session captured</p>
                  <p className="text-[11px] text-[var(--text-secondary)] mt-1 leading-snug">
                    {captureResult.cookies_count} cookies
                    {captureResult.has_local_storage ? " · localStorage included" : ""}
                    {captureResult.app_base_url ? ` · ${captureResult.app_base_url}` : ""}
                  </p>
                </div>
              </div>
            </div>
          )}

          {status === "error" && (
            <div className="px-5 py-5 flex flex-col gap-3">
              <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4">
                <div className="flex gap-2">
                  <X className="h-4 w-4 text-red-500 shrink-0 mt-0.5" aria-hidden />
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">Something went wrong</p>
                    <p className="text-xs text-[var(--text-secondary)] mt-1 leading-relaxed">{error}</p>
                  </div>
                </div>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => reset()}
                className={cn(steelDialogOutlineButtonClass, "w-full sm:w-auto")}
              >
                Try again
              </Button>
            </div>
          )}
        </div>

        <div
          className={
            status === "idle" && !projectId
              ? "flex items-center justify-center border-t border-[var(--border-color)] bg-[var(--bg-secondary)]/50 px-5 py-3 flex-shrink-0"
              : "flex items-center justify-between border-t border-[var(--border-color)] bg-[var(--bg-secondary)]/50 px-5 py-3 flex-shrink-0 gap-2"
          }
        >
          {!(status === "idle" && !projectId) && (
            <p className="text-[10px] text-[var(--text-secondary)] min-w-0">
              {status === "live"
                ? "Sign in in the browser above, then capture the session."
                : status === "done"
                  ? "You can close this dialog."
                  : "\u00A0"}
            </p>
          )}
          <div className="flex gap-2 shrink-0">
            {status === "idle" && projectId && (
              <Button type="button" size="sm" onClick={launchSession} className={steelDialogPrimaryButtonClass}>
                Launch Browser
              </Button>
            )}
            {status === "idle" && !projectId && (
              <p className="text-[11px] text-amber-600 dark:text-amber-400 text-center leading-relaxed">
                Select a project in the sidebar first.
              </p>
            )}
            {status === "live" && (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={cancelSession}
                  className={steelDialogOutlineButtonClass}
                >
                  Cancel
                </Button>
                <Button type="button" size="sm" onClick={captureAndFinish} className={steelDialogPrimaryButtonClass}>
                  Capture Session
                </Button>
              </>
            )}
            {(status === "done" || status === "error") && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => handleOpenChange(false)}
                className={steelDialogOutlineButtonClass}
              >
                Close
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
