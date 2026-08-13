"use client";

import { Button } from "@/components/ui/button";
import { FileBraces, FolderPlus } from "lucide-react";
import { useRouter } from "next/navigation";

export function NoProjectEmptyState() {
  const router = useRouter();

  return (
    <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <FileBraces className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No repository tree
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
          Import a GitHub repository to browse the source PatchAPI will scan when an API provider changes.
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
