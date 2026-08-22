"use client";

import { Button } from "@/components/ui/button";
import { Bell, FolderPlus, Store } from "lucide-react";
import { useRouter } from "next/navigation";

export function NoProjectEmptyState() {
  const router = useRouter();

  return (
    <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <Bell className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No Releases
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
          Select a project to watch subscribed providers for API and service releases.
        </p>
        <Button
          size="sm"
          onClick={() => router.push("/")}
          className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
        >
          <FolderPlus className="h-3 w-3 mr-1" />
          Select Project
        </Button>
      </div>
    </div>
  );
}

export function NoDetectionsEmptyState({
  subscribed = false,
  onBrowseSubscriptions,
}: {
  subscribed?: boolean;
  onBrowseSubscriptions?: () => void;
}) {
  return (
    <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <Bell className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No Releases
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
          {subscribed
            ? "No notes from your subscribed providers match this project yet."
            : "Subscribe to providers from the marketplace to watch it for API and service releases."}
        </p>
        {!subscribed && onBrowseSubscriptions && (
          <Button
            size="sm"
            onClick={onBrowseSubscriptions}
            className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            <Store className="h-3 w-3 mr-1" />
            Browse marketplace
          </Button>
        )}
      </div>
    </div>
  );
}
