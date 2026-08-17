"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ConnectionKind, ProviderConnection } from "@/lib/providers";

const KIND_COPY: Record<
  ConnectionKind,
  { connect: string; connected: string; placeholder: string }
> = {
  catalog: {
    connect: "Paste the catalog endpoint. The project is read from the URL.",
    connected: "Imported from the destination catalog endpoint.",
    placeholder: "https://serviceusage.googleapis.com/v1/projects/{project}/services",
  },
  changes: {
    connect: "Paste the changes endpoint. Project, dataset, and table are read from the URL.",
    connected: "Imported from the destination changes endpoint.",
    placeholder:
      "https://console.cloud.google.com/bigquery?p=bigquery-public-data&d=google_cloud_release_notes&t=release_notes",
  },
};

export function ConnectionDialog({
  open,
  onOpenChange,
  kind,
  connection,
  pending,
  error,
  onConnect,
  onDisconnect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: ConnectionKind;
  connection: ProviderConnection | null;
  pending?: boolean;
  error?: string | null;
  onConnect: (url: string) => void;
  onDisconnect: () => void;
}) {
  const [url, setUrl] = useState("");
  const copy = KIND_COPY[kind];
  const live = connection?.status === "connected" || connection?.status === "pending";
  const href = connection?.source_url || "";

  useEffect(() => {
    if (open) setUrl(connection?.source_url || "");
  }, [connection?.source_url, open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg bg-[var(--bg-primary)] border-[var(--border-color)] flex flex-col gap-0 overflow-hidden p-0 sm:max-w-lg">
        <div className="shrink-0 px-6 pt-6 pb-4 border-b border-[var(--border-color)]">
          <DialogHeader className="space-y-0 text-left">
            <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
              Source
            </DialogTitle>
            <DialogDescription className="text-xs text-[var(--text-secondary)] pt-2">
              {live ? copy.connected : copy.connect}
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="px-6 py-4 space-y-3">
          {live && href ? (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="min-h-8 px-3 py-2 flex items-start gap-2 rounded-md border border-[var(--border-color)] bg-[var(--bg-secondary)] text-xs text-[var(--text-primary)] hover:border-primary/40 hover:text-primary transition-colors font-mono break-all leading-snug"
            >
              <span className="flex-1 min-w-0">{href}</span>
              <ArrowUpRight className="h-3.5 w-3.5 flex-shrink-0 mt-0.5 text-[var(--text-secondary)]" />
            </a>
          ) : (
            <div className="grid gap-2">
              <Label className="text-xs text-[var(--text-secondary)]">Endpoint</Label>
              <Input
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder={copy.placeholder}
                className="h-8 text-xs font-mono bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]"
              />
            </div>
          )}
          {connection?.status === "error" && connection.last_error && (
            <p className="text-xs text-red-500">{connection.last_error}</p>
          )}
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>

        <DialogFooter className="shrink-0 border-t border-[var(--border-color)] bg-[var(--bg-primary)] px-6 py-4 gap-2">
          {live ? (
            <>
              <Button
                variant="outline"
                type="button"
                disabled={pending}
                onClick={onDisconnect}
                className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
              >
                Disconnect
              </Button>
              <Button
                variant="outline"
                type="button"
                onClick={() => onOpenChange(false)}
                className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
              >
                Done
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="outline"
                type="button"
                onClick={() => onOpenChange(false)}
                className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
              >
                Cancel
              </Button>
              <Button
                type="button"
                disabled={pending || !url.trim()}
                onClick={() => onConnect(url.trim())}
                className="text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                {pending ? "Connecting…" : "Connect"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ConnectionChip({
  connection,
  onClick,
}: {
  connection: ProviderConnection | null;
  onClick: () => void;
}) {
  const status = connection?.status;
  const connected = status === "connected";
  const pending = status === "pending";
  const errored = status === "error";
  const label = connected ? "Connected" : pending ? "Connecting" : errored ? "Retry" : "Connect";
  const tone = connected
    ? "text-[#10b981] border-[#10b981]/30 hover:bg-[#10b981]/10"
    : pending
      ? "text-amber-500 border-amber-500/30 hover:bg-amber-500/10"
      : errored
        ? "text-red-500 border-red-500/30 hover:bg-red-500/10"
        : "text-[var(--text-primary)] border-[var(--border-color)] hover:bg-[var(--bg-tertiary)]";
  const dot = connected
    ? "bg-[#10b981]"
    : pending
      ? "bg-amber-500"
      : errored
        ? "bg-red-500"
        : "bg-[var(--text-secondary)]";

  return (
    <button
      type="button"
      title="Endpoint source"
      onClick={onClick}
      className={`h-8 inline-flex items-center gap-1.5 px-2.5 rounded-md border text-xs font-medium transition-colors ${tone}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {label}
    </button>
  );
}
