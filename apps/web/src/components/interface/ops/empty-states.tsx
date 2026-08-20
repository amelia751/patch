"use client";

import { Button } from "@/components/ui/button";
import { FolderPlus, Code2, Server, Sparkles, FileBraces, PackageOpen, Github } from "lucide-react";
import { useRouter } from "next/navigation";

export function NoProjectEmptyState() {
  const router = useRouter();

  return (
    <div className="h-full flex items-center justify-center bg-[var(--bg-primary)] px-4">
      <div className="text-center max-w-md">
        <div className="flex justify-center mb-6">
          <div className="relative">
            <div className="absolute inset-0 bg-primary/20 blur-2xl rounded-full"></div>
            <div className="relative bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-2xl p-4">
              <FolderPlus className="h-12 w-12 text-primary" strokeWidth={1.5} />
            </div>
          </div>
        </div>

        <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
          No Project Selected
        </h2>
        <p className="text-sm text-[var(--text-secondary)] mb-6 leading-relaxed">
          Import a GitHub repository so PatchAPI can inventory API usage, verify a migration in isolation, and open a pull request for review.
        </p>

        <div className="flex flex-col gap-3">
          <Button
            onClick={() => router.push("/")}
            className="w-full bg-primary hover:bg-primary/90 text-primary-foreground text-sm"
          >
            <Sparkles className="h-4 w-4 mr-2" />
            Import a project
          </Button>
          <Button
            variant="outline"
            onClick={() => router.push("/")}
            className="w-full text-sm border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
          >
            View All Projects
          </Button>
        </div>

        <div className="mt-8 pt-6 border-t border-[var(--border-color)]">
          <p className="text-xs text-[var(--text-tertiary)] mb-3">
            A run stops at the pull request:
          </p>
          <div className="flex items-center justify-center gap-6 text-xs text-[var(--text-secondary)]">
            <div className="flex items-center gap-1.5">
              <Code2 className="h-3.5 w-3.5" />
              <span>Find call sites</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Server className="h-3.5 w-3.5" />
              <span>Verify in isolation</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ConfigureEmptyState() {
  const router = useRouter();

  return (
    <div className="h-full flex items-center justify-center bg-[var(--bg-primary)] px-4">
      <div className="text-center max-w-md">
        <div className="flex justify-center mb-6">
          <div className="relative">
            <div className="absolute inset-0 bg-purple-500/20 blur-2xl rounded-full"></div>
            <div className="relative bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-2xl p-4">
              <Server className="h-12 w-12 text-purple-500" strokeWidth={1.5} />
            </div>
          </div>
        </div>

        <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
          No Cloud Configuration
        </h2>
        <p className="text-sm text-[var(--text-secondary)] mb-6 leading-relaxed">
          Select a project and connect your cloud provider to configure infrastructure and manage secrets.
        </p>

        <Button
          onClick={() => router.push("/")}
          className="bg-primary hover:bg-primary/90 text-primary-foreground text-sm"
        >
          <FolderPlus className="h-4 w-4 mr-2" />
          Select Project
        </Button>
      </div>
    </div>
  );
}

export function CodebaseEmptyState({ onImport }: { onImport?: () => void }) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <FileBraces className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No repository tree
        </h2>
        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          Import a GitHub repository to browse the source PatchAPI will scan when an API provider changes.
        </p>
        {onImport ? (
          <Button
            size="sm"
            onClick={onImport}
            className="mt-6 h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            <Github className="h-3 w-3 mr-1" />
            Import from GitHub
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function ResourcesEmptyState() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <PackageOpen className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No resources deployed
        </h2>
        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          Select a project to view and manage your deployed cloud resources, including compute, databases, and storage.
        </p>
      </div>
    </div>
  );
}
