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
          No changes to show
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
          Select a project to match its inventory against known provider deprecations — including ones that already happened.
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
  onBrowseSubscriptions,
}: {
  onBrowseSubscriptions?: () => void;
}) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <Bell className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No matching deprecations
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
          Nothing in this project matches a known deprecation yet. Subscribe to a provider to keep watching.
        </p>
        {onBrowseSubscriptions && (
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
