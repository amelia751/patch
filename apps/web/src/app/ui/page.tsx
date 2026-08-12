"use client";

import { Cloud } from "lucide-react";

/** Dev placeholder; main workspace lives on `/`. */
export default function UIPage() {
  return (
    <div className="flex-1 flex items-center justify-center px-6">
      <div className="text-center max-w-md">
        <div className="h-10 w-10 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <Cloud className="h-4 w-4 text-[var(--text-secondary)]" />
        </div>
        <p className="text-sm text-[var(--text-secondary)]">
          Use the main workspace: architecture and threads are on the home view.
        </p>
      </div>
    </div>
  );
}
