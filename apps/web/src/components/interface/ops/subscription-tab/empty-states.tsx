"use client";

import { Button } from "@/components/ui/button";
import { FolderPlus, Rss, Store } from "lucide-react";
import { useRouter } from "next/navigation";

export function NoProjectEmptyState() {
  const router = useRouter();

  return (
    <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <Rss className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No subscriptions
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
          Select a project to subscribe to Google Cloud and watch it for API and service releases.
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

export function SubscribedEmptyState({ onBrowse }: { onBrowse: () => void }) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <Rss className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No subscriptions
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
          Subscribe to Google Cloud from the marketplace to watch it for API and service releases.
        </p>
        <Button
          size="sm"
          onClick={onBrowse}
          className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
        >
          <Store className="h-3 w-3 mr-1" />
          Browse marketplace
        </Button>
      </div>
    </div>
  );
}

export function MarketplaceEmptyState() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <Store className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No providers yet
        </h2>
        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          The catalog has nothing to subscribe to right now.
        </p>
      </div>
    </div>
  );
}
