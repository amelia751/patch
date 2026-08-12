"use client";

import React from "react";
import { ChevronUp, ChevronDown } from "lucide-react";

interface Version {
  id: string;
  label: string;
  description: string;
  status: "draft" | "approved" | "deployed" | "archived";
}

interface VersionNavigatorProps {
  versions: Version[];
  currentVersionId: string;
  onVersionChange: (versionId: string) => void;
}

export function VersionNavigator({ versions, currentVersionId, onVersionChange }: VersionNavigatorProps) {
  const currentIndex = versions.findIndex((v) => v.id === currentVersionId);
  const currentVersion = versions[currentIndex];

  const handlePrevious = () => {
    if (currentIndex > 0) {
      onVersionChange(versions[currentIndex - 1].id);
    }
  };

  const handleNext = () => {
    if (currentIndex < versions.length - 1) {
      onVersionChange(versions[currentIndex + 1].id);
    }
  };

  const canGoPrevious = currentIndex > 0;
  const canGoNext = currentIndex < versions.length - 1;

  return (
    <div className="absolute bottom-6 left-1/2 transform -translate-x-1/2 z-50">
      <div className="flex items-center gap-2 bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-lg shadow-lg px-3 py-1.5">
        {/* Previous Button */}
        <button
          onClick={handlePrevious}
          disabled={!canGoPrevious}
          className={`p-0.5 rounded transition-all ${
            canGoPrevious
              ? "hover:bg-[var(--bg-secondary)] text-[var(--text-primary)]"
              : "text-gray-500 cursor-not-allowed opacity-30"
          }`}
          title="Previous version"
        >
          <ChevronUp className="w-4 h-4" />
        </button>

        {/* Version Counter */}
        <div className="min-w-[3rem] text-center">
          <span className="text-sm font-medium text-[var(--text-primary)]">
            {currentIndex + 1} / {versions.length}
          </span>
        </div>

        {/* Next Button */}
        <button
          onClick={handleNext}
          disabled={!canGoNext}
          className={`p-0.5 rounded transition-all ${
            canGoNext
              ? "hover:bg-[var(--bg-secondary)] text-[var(--text-primary)]"
              : "text-gray-500 cursor-not-allowed opacity-30"
          }`}
          title="Next version"
        >
          <ChevronDown className="w-4 h-4" />
        </button>

        {/* Divider */}
        <div className="h-5 w-px bg-[var(--border-color)]" />

        {/* Undo Button */}
        <button
          className="px-3 py-1 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] rounded transition-all"
          title="Undo changes"
        >
          Undo
        </button>

        {/* Keep Button */}
        <button
          className="px-3 py-1 text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 rounded transition-all"
          title="Keep this version"
        >
          Keep
        </button>
      </div>
    </div>
  );
}

