"use client";

import Image from "next/image";
import { useState } from "react";
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
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ServiceIcon } from "@/components/ui/service-icon";
import { CheckCircle2, Loader2, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { GoogleAppSessionGsiMount } from "./google-app-session-gsi-mount";

export const LOGIN_ASSET = (name: string) => `/assets/login/${name}`;

export type GoogleTestAuthStatus = "disconnected" | "connecting" | "connected";

export interface GoogleTestSessionSlice {
  status: GoogleTestAuthStatus;
  connectedAs?: string;
  capturedAt?: string;
  sessionDisplayName?: string;
  authExchangeUrl?: string;
}

interface GoogleTestConnectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  google: GoogleTestSessionSlice;
  googleSessionIconGeneration: number;
  projectId: string | null;
  onGsiBusy: () => void;
  onGsiSuccess: (detail: {
    connected_as?: string | null;
    session_display_name?: string | null;
    auth_exchange_url?: string | null;
    captured_at?: string | null;
  }) => void;
  onGsiError: (message: string) => void;
  onDisconnect: () => void | Promise<void>;
}

export function GoogleTestConnectDialog({
  open,
  onOpenChange,
  google,
  googleSessionIconGeneration,
  projectId,
  onGsiBusy,
  onGsiSuccess,
  onGsiError,
  onDisconnect,
}: GoogleTestConnectDialogProps) {
  const [disconnectConfirmOpen, setDisconnectConfirmOpen] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const showConnected = google.status === "connected" && google.connectedAs;

  return (
    <>
    <AlertDialog
      open={disconnectConfirmOpen}
      onOpenChange={(next) => {
        if (!disconnecting) setDisconnectConfirmOpen(next);
      }}
    >
      <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-[var(--text-primary)]">
            Disconnect Google test session?
          </AlertDialogTitle>
          <AlertDialogDescription className="text-[var(--text-secondary)] leading-relaxed">
            Are you sure you want to disconnect? Test runs will no longer use this saved Google session until you sign
            in again. You can reconnect anytime.
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
                  await Promise.resolve(onDisconnect());
                } finally {
                  setDisconnecting(false);
                  setDisconnectConfirmOpen(false);
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

    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] max-w-sm gap-0 p-0 overflow-hidden">
        {showConnected ? (
          <>
            <DialogHeader className="px-5 pt-5 pb-3 border-b border-[var(--border-color)] text-left space-y-1.5">
              <DialogTitle
                aria-label="Google authenticated"
                className="flex items-center gap-2.5 text-sm sm:text-base font-semibold text-[var(--text-primary)]"
              >
                <span className="inline-flex shrink-0" aria-hidden>
                  <ServiceIcon key={googleSessionIconGeneration} name="google" size={22} />
                </span>
                Authenticated
              </DialogTitle>
              <p className="text-[10px] sm:text-xs text-[var(--text-secondary)] font-normal leading-snug">
                Test runs can use this session.
              </p>
            </DialogHeader>

            <div className="px-5 py-5 flex flex-col gap-3">
              <div className="flex items-center gap-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)]/80 p-3">
                <CheckCircle2 className="h-4 w-4 text-[#10b981] flex-shrink-0" aria-hidden />
                {google.capturedAt ? (
                  <p className="text-sm text-[var(--text-primary)] leading-snug">Captured {google.capturedAt}</p>
                ) : (
                  <p className="text-sm text-[var(--text-primary)]">Session active</p>
                )}
              </div>

              <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)]/50 overflow-hidden divide-y divide-[var(--border-color)]">
                {[
                  { label: "Name", value: google.sessionDisplayName, mono: false },
                  { label: "Email", value: google.connectedAs, mono: false },
                  { label: "Auth endpoint", value: google.authExchangeUrl, mono: true },
                ]
                  .filter((row) => row.value)
                  .map((row) => (
                    <div key={row.label} className="px-3 py-2.5">
                      <p className="text-[9px] uppercase tracking-wide text-[var(--text-secondary)] mb-1">{row.label}</p>
                      <p
                        className={cn(
                          "text-[11px] text-[var(--text-primary)] break-all leading-snug",
                          row.mono && "font-mono"
                        )}
                      >
                        {row.value}
                      </p>
                    </div>
                  ))}
              </div>

              <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                Requests from sandbox runs include this login. Disconnect removes the session from JetRun.
              </p>
            </div>

            <div className="flex justify-end gap-2 border-t border-[var(--border-color)] bg-[var(--bg-secondary)]/50 px-5 py-3">
              <Button
                variant="outline"
                size="sm"
                type="button"
                onClick={() => onOpenChange(false)}
                className="text-xs border-[var(--border-color)] bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm hover:!bg-[var(--bg-tertiary)] hover:!text-[var(--text-primary)]"
              >
                Done
              </Button>
              <Button
                variant="outline"
                size="sm"
                type="button"
                onClick={() => setDisconnectConfirmOpen(true)}
                className="text-xs border-red-500/35 bg-transparent text-red-600 shadow-sm hover:!bg-red-500/15 hover:!text-red-700 dark:text-red-400 dark:hover:!bg-red-500/20 dark:hover:!text-red-300"
              >
                <LogOut className="h-3 w-3 mr-1.5" />
                Disconnect
              </Button>
            </div>
          </>
        ) : google.status === "connecting" ? (
          <div className="flex flex-col items-center gap-2.5 px-5 py-8">
            <DialogHeader className="sr-only">
              <DialogTitle>Google sign-in</DialogTitle>
            </DialogHeader>
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-[var(--text-secondary)]" aria-hidden />
            <p className="text-[11px] text-[var(--text-secondary)]">Signing in&hellip;</p>
          </div>
        ) : (
          <>
            <DialogHeader className="px-5 pt-5 pb-3 border-b border-[var(--border-color)] text-left space-y-1.5">
              <DialogTitle className="text-sm sm:text-base font-semibold text-[var(--text-primary)]">
                Google test sign-in
              </DialogTitle>
              <p className="text-[10px] sm:text-xs text-[var(--text-secondary)] font-normal leading-snug">
                Signs into Google to create session.
              </p>
            </DialogHeader>

            <div className="px-5 py-5 flex flex-col gap-3">
              <div className="relative mx-auto w-full max-w-[240px] aspect-[5/4] overflow-hidden shrink-0">
                <Image
                  src={LOGIN_ASSET("login.png")}
                  alt="Sign-in illustration"
                  fill
                  sizes="240px"
                  quality={95}
                  className="object-cover object-center"
                />
              </div>
              <div>
                <h3 className="text-sm font-medium text-[var(--text-primary)] mb-1.5">Your app stays in charge</h3>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                  JetRun stores it encrypted for this project, using your linked Google client ID—so validation matches
                  production.
                </p>
              </div>
            </div>

            <div className="px-5 py-3 border-t border-[var(--border-color)] bg-[var(--bg-secondary)]/50 space-y-2">
              {!projectId ? (
                <p className="text-[11px] text-amber-600 dark:text-amber-400 text-center leading-relaxed">
                  Select a project in the sidebar to connect a test session.
                </p>
              ) : (
                <GoogleAppSessionGsiMount
                  projectId={projectId}
                  onBusy={onGsiBusy}
                  onExchangeSuccess={onGsiSuccess}
                  onExchangeError={(msg) => onGsiError(msg)}
                  onNavigateToConfigureSecrets={() => onOpenChange(false)}
                />
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
    </>
  );
}
