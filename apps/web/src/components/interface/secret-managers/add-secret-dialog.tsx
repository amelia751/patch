"use client";

import { useState, useEffect, useRef, useId, Fragment } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Spinner } from "@/components/ui/spinner";
import {
  Eye,
  EyeOff,
  CloudUpload,
  CheckCircle2,
  X,
  AlertTriangle,
  Check,
  ChevronRight,
  FolderOpen,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  normalizeRepoPath,
  rootWorkspaceId,
  workspaceIdForSelectedFolder,
} from "@/lib/secret-scope";

export type SecretWorkspaceOption = {
  id: string;
  name: string;
  /** Repo-relative folder for this workspace (GitHub import picker). */
  workspace_path?: string | null;
  repo_url?: string | null;
};

export type SecretRepoOption = {
  fullName: string;
  defaultBranch?: string | null;
};

interface AddSecretDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** `rotate` = same as configure (locked scope/name) but updates an existing stored secret’s value. */
  mode?: "add" | "configure" | "rotate";
  existingSecret?: {
    name: string;
    type: string;
  };
  projectId?: string;
  requirementId?: string;
  /** Workspaces from project settings; when empty, scope UI is hidden (shared-only). */
  workspaces?: SecretWorkspaceOption[];
  /** `__shared__` or a workspace id — used when the dialog opens. */
  initialWorkspaceScope?: string;
  /** Linked GitHub `owner/repo` — when set (and not preview), scope uses real repo folders like import. */
  repoFullName?: string | null;
  repoDefaultBranch?: string | null;
  /** Imported repos on this console project. One repo auto-selects; several need a pick. */
  repos?: SecretRepoOption[];
  /** Demo / logged-out: no API call; simulate success. */
  secretsPreviewMode?: boolean;
  onSaved?: () => void;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function resolveWorkspaceScope(
  scope: string | null | undefined,
  workspaces: SecretWorkspaceOption[]
): string | null {
  if (scope && scope !== "__shared__") return scope;
  return rootWorkspaceId(workspaces);
}

function fullNameFromRepoUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const trimmed = url.trim().replace(/\.git$/u, "");
  const match = /github\.com[:/]([^/]+\/[^/]+)/iu.exec(trimmed);
  if (match?.[1]) return match[1];
  if (/^[^/]+\/[^/]+$/u.test(trimmed)) return trimmed;
  return null;
}


/** Clipboard looks like .env lines (at least one KEY=...) */
function looksLikeEnvPaste(text: string): boolean {
  const t = text.trim();
  if (!t || !t.includes("=")) return false;
  return t.split(/\r?\n/).some((line) => /^\s*[A-Za-z_][A-Za-z0-9_]*\s*=/.test(line));
}

export function AddSecretDialog({
  open,
  onOpenChange,
  mode = "add",
  existingSecret,
  projectId,
  requirementId,
  workspaces = [],
  initialWorkspaceScope = "__shared__",
  repoFullName = null,
  repoDefaultBranch = null,
  repos = [],
  secretsPreviewMode = false,
  onSaved,
}: AddSecretDialogProps) {
  const scopeLocked = mode === "configure" || mode === "rotate";
  /** Avoid transient `workspaces=[]` during refetch causing a dead Create button. */
  const lastNonEmptyWorkspacesRef = useRef<SecretWorkspaceOption[]>([]);
  const prevProjectIdRef = useRef(projectId);
  if (prevProjectIdRef.current !== projectId) {
    prevProjectIdRef.current = projectId;
    lastNonEmptyWorkspacesRef.current = [];
  }
  useEffect(() => {
    if (workspaces.length > 0) {
      lastNonEmptyWorkspacesRef.current = workspaces;
    }
  }, [workspaces]);
  const workspacesForScope = workspaces.length > 0 ? workspaces : lastNonEmptyWorkspacesRef.current;

  const repoOptions: SecretRepoOption[] = (() => {
    const fromProp = repos.filter((r) => r.fullName.includes("/"));
    if (fromProp.length > 0) return fromProp;
    if (repoFullName?.includes("/")) {
      return [{ fullName: repoFullName, defaultBranch: repoDefaultBranch }];
    }
    return [];
  })();

  const [selectedRepoFullName, setSelectedRepoFullName] = useState("");
  const selectedRepo =
    repoOptions.find((r) => r.fullName === selectedRepoFullName) ??
    (repoOptions.length === 1 ? repoOptions[0] : undefined);
  const workspacesForSelectedRepo = selectedRepo
    ? workspacesForScope.filter((w) => {
        const fromUrl = fullNameFromRepoUrl(w.repo_url);
        return !fromUrl || fromUrl === selectedRepo.fullName;
      })
    : workspacesForScope;

  const [secretName, setSecretName] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [showSecretKey, setShowSecretKey] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  /** Workspace id, or `__shared__` until resolved to that repo's root workspace. */
  const [workspaceScope, setWorkspaceScope] = useState<string>("__shared__");
  /**
   * When not using GitHub repo folders: `null` = root list; workspace id = drilled into that workspace.
   */
  const [scopeBrowseWorkspaceId, setScopeBrowseWorkspaceId] = useState<string | null>(null);
  /** GitHub import-style path segments from repo root (add mode + repo linked). */
  const [folderPath, setFolderPath] = useState<string[]>([]);
  const [repoFolders, setRepoFolders] = useState<string[]>([]);
  const [repoFoldersLoading, setRepoFoldersLoading] = useState(false);
  const [repoFoldersError, setRepoFoldersError] = useState<string | null>(null);
  const [repoFoldersRetryKey, setRepoFoldersRetryKey] = useState(0);

  const useRepoBrowser = Boolean(selectedRepo?.fullName.includes("/")) && !secretsPreviewMode;
  const [detectedEntries, setDetectedEntries] = useState<{ key: string; value: string }[]>([]);
  const [isParsingEnv, setIsParsingEnv] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  /** Drop zone shows GCP-style success only after file upload/drop, not paste */
  const [lastImportViaFile, setLastImportViaFile] = useState(false);
  /** Bulk add: indices of detectedEntries to import (all selected by default when allowed) */
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const envFileInputId = `add-secret-env-${useId().replace(/:/g, "")}`;

  const isBulkMode =
    mode === "add" &&
    !requirementId &&
    detectedEntries.length > 1;

  // Pre-fill secret name when scope/name are locked
  useEffect(() => {
    if (scopeLocked && existingSecret) {
      setSecretName(existingSecret.name);
    } else {
      setSecretName("");
    }
    setSecretKey("");
    setShowSecretKey(false);
    setDetectedEntries([]);
    setParseError(null);
    setIsDragOver(false);
    setLastImportViaFile(false);
    setSelectedIndices(new Set());
  }, [scopeLocked, existingSecret, open]);

  /** Scope init: full reset only when the dialog opens — not on every parent `workspaces` refetch (avoids wiping folder path mid-session). */
  const addDialogWasOpenRef = useRef(false);
  useEffect(() => {
    if (!open) {
      addDialogWasOpenRef.current = false;
      return;
    }
    const justOpened = !addDialogWasOpenRef.current;
    addDialogWasOpenRef.current = true;

    const scope = initialWorkspaceScope || "__shared__";
    if (useRepoBrowser) {
      if (justOpened) {
        setScopeBrowseWorkspaceId(null);
        if (scope === "__shared__") {
          setFolderPath([]);
          if (scopeLocked || mode !== "add") setWorkspaceScope("__shared__");
        } else {
          const ws = workspacesForSelectedRepo.find((w) => w.id === scope);
          const bp = normalizeRepoPath(ws?.workspace_path ?? null);
          setFolderPath(bp ? bp.split("/").filter(Boolean) : []);
          if (scopeLocked || mode !== "add") setWorkspaceScope(scope);
        }
        return;
      }
      if (!scopeLocked && mode === "add" && scope !== "__shared__") {
        setFolderPath((prev) => {
          if (prev.length > 0) return prev;
          const ws = workspacesForSelectedRepo.find((w) => w.id === scope);
          const bp = normalizeRepoPath(ws?.workspace_path ?? null);
          return bp ? bp.split("/").filter(Boolean) : prev;
        });
      }
      return;
    }
    if (justOpened) {
      setFolderPath([]);
      setWorkspaceScope(scope);
      setScopeBrowseWorkspaceId(scope === "__shared__" ? null : scope);
    }
  }, [open, initialWorkspaceScope, useRepoBrowser, workspacesForSelectedRepo, scopeLocked, mode]);

  useEffect(() => {
    if (!open || !useRepoBrowser || scopeLocked) {
      setRepoFolders([]);
      setRepoFoldersLoading(false);
      setRepoFoldersError(null);
      return;
    }
    const full = selectedRepo?.fullName ?? "";
    const [owner, repo] = full.split("/");
    if (!owner || !repo) {
      setRepoFolders([]);
      return;
    }
    const pathStr = folderPath.join("/");
    const controller = new AbortController();
    setRepoFoldersLoading(true);
    setRepoFoldersError(null);
    const params = new URLSearchParams();
    if (pathStr) params.set("path", pathStr);
    const ref = (selectedRepo?.defaultBranch || repoDefaultBranch || "").trim();
    if (ref) params.set("ref", ref);
    const qs = params.toString() ? `?${params.toString()}` : "";
    fetch(`${API_URL}/api/github/repos/${owner}/${repo}/files${qs}`, {
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          let message = `Could not load folders (${res.status})`;
          try {
            const errBody = await res.json();
            if (typeof errBody?.detail === "string") message = errBody.detail;
            else if (Array.isArray(errBody?.detail) && errBody.detail[0]?.msg) {
              message = errBody.detail[0].msg;
            }
          } catch {
            /* ignore */
          }
          throw new Error(message);
        }
        return res.json() as Promise<{ type?: string; name: string }[]>;
      })
      .then((data) => {
        if (controller.signal.aborted) return;
        const directories = data
          .filter((item) => item.type === "dir")
          .map((item) => item.name)
          .sort();
        setRepoFolders(directories);
        setRepoFoldersError(null);
      })
      .catch((err: unknown) => {
        if ((err as Error).name === "AbortError") return;
        console.error("Failed to fetch repo folders:", err);
        setRepoFolders([]);
        setRepoFoldersError(
          err instanceof Error ? err.message : "Could not load repository folders."
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setRepoFoldersLoading(false);
      });
    return () => controller.abort();
  }, [
    open,
    useRepoBrowser,
    scopeLocked,
    selectedRepo?.fullName,
    selectedRepo?.defaultBranch,
    repoDefaultBranch,
    folderPath.join("/"),
    repoFoldersRetryKey,
  ]);

  useEffect(() => {
    if (open) return;
    setFolderPath([]);
    setWorkspaceScope("__shared__");
    setRepoFolders([]);
    setRepoFoldersError(null);
    setRepoFoldersRetryKey(0);
    setScopeBrowseWorkspaceId(null);
    setSelectedRepoFullName("");
    setIsSubmitting(false);
    setIsParsingEnv(false);
  }, [open]);

  const repoOptionKey = repoOptions.map((r) => r.fullName).join("|");
  useEffect(() => {
    if (!open) return;
    if (repoOptions.length === 1) {
      setSelectedRepoFullName(repoOptions[0].fullName);
      return;
    }
    if (repoOptions.length > 1) {
      setSelectedRepoFullName((prev) =>
        repoOptions.some((r) => r.fullName === prev) ? prev : repoOptions[0].fullName
      );
    }
    // repoOptionKey is the stable identity of the imported-repo list
    // eslint-disable-next-line react-hooks/exhaustive-deps -- avoid resetting on new array identity
  }, [open, repoOptionKey]);

  const pickRepo = (fullName: string) => {
    if (fullName === selectedRepoFullName) return;
    setSelectedRepoFullName(fullName);
    setFolderPath([]);
    setRepoFolders([]);
    setRepoFoldersError(null);
    setWorkspaceScope("__shared__");
  };

  /** Repo-browser add mode: scope follows `folderPath` synchronously (avoids init vs sync effect races). */
  const scopeFromFolderBrowse = workspaceIdForSelectedFolder(
    folderPath,
    workspacesForSelectedRepo
  );
  const activeWorkspaceScope =
    open && useRepoBrowser && !scopeLocked && mode === "add"
      ? resolveWorkspaceScope(scopeFromFolderBrowse, workspacesForSelectedRepo) ?? "__shared__"
      : resolveWorkspaceScope(workspaceScope, workspacesForScope) ?? workspaceScope;

  const showWorkspaceScope = workspaces.length > 0 || useRepoBrowser;

  const goToRepoPathDepth = (depth: number) => {
    setFolderPath((prev) => prev.slice(0, depth));
  };

  const handleRepoFolderClick = (folderName: string) => {
    setFolderPath([...folderPath, folderName]);
  };

  const goToRepoRoot = () => {
    setFolderPath([]);
  };

  // Multi-variable import without a single requirement: assume user wants all → all selected
  useEffect(() => {
    if (detectedEntries.length <= 1) {
      setSelectedIndices(new Set());
      return;
    }
    if (!requirementId) {
      setSelectedIndices(new Set(detectedEntries.map((_, i) => i)));
    } else {
      setSelectedIndices(new Set());
    }
  }, [detectedEntries, requirementId]);

  const parseEnvContent = async (
    content: string,
    fromFile: boolean,
    fromFieldPaste = false
  ) => {
    const trimmed = content.trim();
    if (!trimmed) {
      setParseError("No content to parse");
      setLastImportViaFile(false);
      return;
    }
    setIsParsingEnv(true);
    setParseError(null);
    try {
      const res = await fetch(`${API_URL}/api/projects/parse-env`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: trimmed }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setParseError((err as { detail?: string }).detail || `Parse failed (${res.status})`);
        setDetectedEntries([]);
        setLastImportViaFile(false);
        return;
      }
      const data = await res.json();
      const entries = (data.entries || []) as { key: string; value: string }[];
      if (entries.length === 0) {
        setDetectedEntries([]);
        setParseError("No KEY=value pairs found (use standard .env format)");
        setLastImportViaFile(false);
        return;
      }
      if (entries.length === 1 && (fromFieldPaste || fromFile)) {
        setSecretName(entries[0].key);
        setSecretKey(entries[0].value);
        setDetectedEntries([]);
        setParseError(null);
        setLastImportViaFile(false);
        return;
      }
      setDetectedEntries(entries);
      if (entries.length > 1) {
        setSelectedIndices(
          requirementId ? new Set() : new Set(entries.map((_, i) => i))
        );
      }
      setLastImportViaFile(fromFile && entries.length > 0);
    } catch {
      setParseError("Network error while parsing");
      setDetectedEntries([]);
      setLastImportViaFile(false);
    } finally {
      setIsParsingEnv(false);
    }
  };

  const readFileAsText = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === "string" ? reader.result : "";
      void parseEnvContent(text, true);
    };
    reader.readAsText(file, "UTF-8");
  };

  const onPickEnvFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    readFileAsText(file);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const file = e.dataTransfer.files?.[0];
    if (!file) return;

    const isTextLike =
      file.type === "text/plain" ||
      file.name.endsWith(".env") ||
      /\.env/i.test(file.name) ||
      file.name.toLowerCase().endsWith(".local");

    if (!isTextLike && file.type !== "" && !file.type.startsWith("text/")) {
      setParseError("Drop a .env or plain text file");
      setDetectedEntries([]);
      return;
    }

    readFileAsText(file);
  };

  const clearEnvImport = () => {
    setDetectedEntries([]);
    setParseError(null);
    setLastImportViaFile(false);
    setSelectedIndices(new Set());
    const input = document.getElementById(envFileInputId) as HTMLInputElement | null;
    if (input) input.value = "";
  };

  const toggleIndex = (i: number) => {
    setSelectedIndices((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const selectAllDetected = () => {
    setSelectedIndices(new Set(detectedEntries.map((_, i) => i)));
  };

  const deselectAllDetected = () => {
    setSelectedIndices(new Set());
  };

  const applyDetectedEntry = (entry: { key: string; value: string }) => {
    setSecretName(entry.key);
    setSecretKey(entry.value);
    setParseError(null);
  };

  const onEnvPaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    if (mode !== "add") return;
    const text = e.clipboardData.getData("text/plain");
    if (!looksLikeEnvPaste(text)) return;
    e.preventDefault();
    void parseEnvContent(text, false, true);
  };

  function maskValue(v: string, maxLen = 28) {
    if (v.length <= 4) return "••••";
    if (v.length <= maxLen) return `${v.slice(0, 2)}…${v.slice(-2)}`;
    return `${v.slice(0, 4)}…${v.slice(-4)} (${v.length} chars)`;
  }

  const storeOneSecret = async (name: string, value: string, reqId?: string, scope?: string) => {
    if (secretsPreviewMode) {
      await new Promise((r) => setTimeout(r, 350));
      return;
    }
    if (!projectId) {
      throw new Error("No project selected — cannot store secrets.");
    }
    const effectiveScope = resolveWorkspaceScope(
      scope ?? activeWorkspaceScope,
      workspacesForSelectedRepo.length > 0 ? workspacesForSelectedRepo : workspacesForScope
    );
    const body: Record<string, unknown> = {
      secret_name: name,
      secret_value: value,
    };
    if (reqId) body.requirement_id = reqId;
    if (effectiveScope) {
      body.workspace_id = effectiveScope;
    }
    const currentPath = folderPath.join("/");
    if (currentPath) {
      body.scope_path = currentPath;
    }
    const res = await fetch(`${API_URL}/api/projects/${projectId}/secrets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as { detail?: string }).detail || `Failed (${res.status})`);
    }
  };

  const handleSubmit = async () => {
    if (!secretsPreviewMode && !projectId) {
      setParseError("No project selected — cannot store secrets.");
      return;
    }
    const bulk = isBulkMode && selectedIndices.size > 0;
    if (bulk) {
      const toAdd = detectedEntries.filter((_, i) => selectedIndices.has(i));
      setIsSubmitting(true);
      setParseError(null);
      try {
        for (const entry of toAdd) {
          await storeOneSecret(entry.key, entry.value, undefined, activeWorkspaceScope);
        }
        onSaved?.();
        onOpenChange(false);
      } catch (err) {
        console.error("Error saving secrets:", err);
        setParseError(err instanceof Error ? err.message : "Failed to save secrets");
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    if (!secretName.trim() || !secretKey.trim()) return;

    setIsSubmitting(true);
    setParseError(null);
    try {
      await storeOneSecret(secretName.trim(), secretKey.trim(), requirementId, activeWorkspaceScope);
      onSaved?.();
      onOpenChange(false);
    } catch (err) {
      console.error("Error saving secret:", err);
      setParseError(err instanceof Error ? err.message : "Failed to save secret");
    } finally {
      setIsSubmitting(false);
    }
  };

  const canStoreToApi = secretsPreviewMode || Boolean(projectId?.trim());
  const canSubmitBulk =
    isBulkMode && selectedIndices.size > 0 && canStoreToApi;
  const canSubmitSingle =
    !isBulkMode &&
    secretName.trim().length > 0 &&
    secretKey.trim().length > 0 &&
    canStoreToApi;

  const browsedWorkspace =
    scopeBrowseWorkspaceId != null
      ? workspaces.find((w) => w.id === scopeBrowseWorkspaceId)
      : undefined;

  const goToScopePathRoot = () => {
    const root = rootWorkspaceId(workspacesForScope);
    setScopeBrowseWorkspaceId(null);
    setWorkspaceScope(root ?? "__shared__");
  };

  const configureScopeWs = workspaces.find((w) => w.id === workspaceScope);
  const configurePathNorm = normalizeRepoPath(configureScopeWs?.workspace_path ?? null);
  const configurePathSegments = configurePathNorm ? configurePathNorm.split("/").filter(Boolean) : [];

  const repoFolderLabel =
    folderPath.length > 0 ? `/${folderPath.join("/")}/` : "/";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        onOpenAutoFocus={(e) => e.preventDefault()}
        className="max-w-lg bg-[var(--bg-primary)] border-[var(--border-color)] flex flex-col max-h-[min(90dvh,40rem)] gap-0 overflow-hidden p-0 sm:max-w-lg"
      >
        <div className="shrink-0 px-6 pt-6 pb-4 border-b border-[var(--border-color)]">
          <DialogHeader className="space-y-0 text-left">
            <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
              {mode === "add"
                ? "Add New Secret"
                : mode === "rotate"
                  ? `Rotate ${existingSecret?.name ?? "secret"}`
                  : `Configure ${existingSecret?.name ?? "secret"}`}
            </DialogTitle>
            <DialogDescription className="text-xs text-[var(--text-secondary)] pt-2">
              {mode === "add"
                ? isBulkMode
                  ? "All variables are selected by default. Uncheck any you do not want, then add the rest in one step. Or upload a .env file."
                  : "Paste KEY=value into Secret name or Secret key (one variable auto-fills). Multiple lines: all selected for bulk add. Or upload a .env file."
                : mode === "rotate"
                  ? "Enter a new value. The same secret name and workspace scope stay fixed; AWS Secrets Manager stores the updated value."
                  : "Configure the secret value. Changes will be applied to Secrets Manager."}
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-6 py-4 space-y-4">
          {repoOptions.length > 0 && (
            <div className="space-y-2">
              <Label className="text-xs text-[var(--text-secondary)]">Project</Label>
              <Select
                value={selectedRepo?.fullName ?? ""}
                onValueChange={pickRepo}
                disabled={scopeLocked || repoOptions.length === 1}
              >
                <SelectTrigger className="h-8 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
                  <SelectValue placeholder="Select a repository" />
                </SelectTrigger>
                <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
                  {repoOptions.map((repo) => (
                    <SelectItem
                      key={repo.fullName}
                      value={repo.fullName}
                      className="text-xs font-mono text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]"
                    >
                      {repo.fullName}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                {repoOptions.length === 1
                  ? "Only imported repository on this project — folder scope below applies here."
                  : "Imported repository. Folder scope below applies to the selected repo."}
              </p>
            </div>
          )}

          {showWorkspaceScope && (
            <div className="space-y-2">
              <Label className="text-xs text-[var(--text-secondary)]">Workspace scope</Label>

              {useRepoBrowser ? (
                <>
                  {mode === "add" && (
                    <div className="flex flex-nowrap items-center gap-1 text-xs min-h-[28px] max-w-full overflow-x-auto overflow-y-hidden py-0.5 [scrollbar-width:thin]">
                      <button
                        type="button"
                        onClick={goToRepoRoot}
                        className={cn(
                          "shrink-0 rounded px-1.5 py-0.5 transition-colors",
                          folderPath.length === 0
                            ? "bg-primary/15 text-primary"
                            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                        )}
                      >
                        /
                      </button>
                      {folderPath.map((segment, index) => {
                        const isActiveTail = index === folderPath.length - 1;
                        return (
                          <Fragment key={`${segment}-${index}`}>
                            <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-secondary)]" />
                            <button
                              type="button"
                              onClick={() => goToRepoPathDepth(index + 1)}
                              className={cn(
                                "shrink-0 rounded px-1.5 py-0.5 transition-colors max-w-[10rem] truncate",
                                isActiveTail
                                  ? "bg-primary/15 text-primary"
                                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                              )}
                              title={segment}
                            >
                              {segment}
                            </button>
                          </Fragment>
                        );
                      })}
                    </div>
                  )}

                  {scopeLocked && (
                    <div className="flex flex-nowrap items-center gap-1 text-xs min-h-[28px] max-w-full overflow-x-auto overflow-y-hidden py-0.5 [scrollbar-width:thin]">
                      <span
                        className={cn(
                          "shrink-0 rounded px-1.5 py-0.5",
                          workspaceScope === "__shared__"
                            ? "bg-primary/15 text-primary"
                            : "text-[var(--text-secondary)]"
                        )}
                      >
                        /
                      </span>
                      {configurePathSegments.map((seg, index) => {
                        const isTail = index === configurePathSegments.length - 1;
                        return (
                          <Fragment key={`${seg}-${index}`}>
                            <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-secondary)]" />
                            <span
                              className={cn(
                                "shrink-0 rounded px-1.5 py-0.5 max-w-[10rem] truncate",
                                isTail && workspaceScope !== "__shared__"
                                  ? "bg-primary/15 text-primary"
                                  : "text-[var(--text-secondary)]"
                              )}
                              title={seg}
                            >
                              {seg}
                            </span>
                          </Fragment>
                        );
                      })}
                      {workspaceScope !== "__shared__" &&
                        configurePathSegments.length === 0 &&
                        configureScopeWs && (
                          <>
                            <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-secondary)]" />
                            <span className="shrink-0 rounded px-1.5 py-0.5 bg-primary/15 text-primary max-w-[10rem] truncate">
                              {configureScopeWs.name}
                            </span>
                          </>
                        )}
                    </div>
                  )}

                  <div
                    className={cn(
                      "rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] max-h-48 overflow-y-auto",
                      scopeLocked && "pointer-events-none opacity-90"
                    )}
                  >
                    {scopeLocked ? (
                      <div className="px-3 py-4 text-xs text-[var(--text-secondary)] leading-relaxed">
                        {configurePathNorm
                          ? `Secrets at this path apply to the workspace whose folder is ${configurePathNorm}/`
                          : `Workspace root (` +
                            `/` +
                            `) — ${configureScopeWs?.name ?? "this workspace"}`}
                      </div>
                    ) : repoFoldersLoading ? (
                      <div className="h-32 rounded-lg flex items-center justify-center">
                        <Spinner className="h-4 w-4 text-[var(--text-secondary)]" />
                      </div>
                    ) : repoFoldersError ? (
                      <div className="rounded-lg px-3 py-4 space-y-2">
                        <p className="text-xs text-red-600 dark:text-red-400">{repoFoldersError}</p>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="text-xs h-8"
                          onClick={() => setRepoFoldersRetryKey((k) => k + 1)}
                        >
                          Retry
                        </Button>
                      </div>
                    ) : (
                      <div>
                        {repoFolders.length > 0 ? (
                          repoFolders.map((folder) => (
                            <button
                              key={folder}
                              type="button"
                              onClick={() => handleRepoFolderClick(folder)}
                              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border-b border-[var(--border-color)] last:border-b-0"
                            >
                              <FolderOpen className="h-3.5 w-3.5 shrink-0 text-[var(--text-secondary)]" />
                              <span>{folder}/</span>
                              <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-secondary)] ml-auto" />
                            </button>
                          ))
                        ) : (
                          <div className="px-3 py-6 text-center text-xs text-[var(--text-secondary)]">
                            No subfolders found
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                    {folderPath.length === 0
                      ? `Repository root (` +
                        `/` +
                        `) — ${workspacesForSelectedRepo.find((w) => w.id === activeWorkspaceScope)?.name ?? "this workspace"}.`
                      : `These credentials will apply to your ${repoFolderLabel} folder.`}
                  </p>
                </>
              ) : (
                <>
                  {mode === "add" && (
                    <div className="flex flex-nowrap items-center gap-1 text-xs min-h-[28px] max-w-full overflow-x-auto overflow-y-hidden py-0.5 [scrollbar-width:thin]">
                      <button
                        type="button"
                        onClick={goToScopePathRoot}
                        className={cn(
                          "shrink-0 rounded px-1.5 py-0.5 transition-colors",
                          scopeBrowseWorkspaceId === null
                            ? "bg-primary/15 text-primary"
                            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                        )}
                      >
                        /
                      </button>
                      {browsedWorkspace && (
                        <>
                          <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-secondary)]" />
                          <span
                            className="shrink-0 rounded px-1.5 py-0.5 bg-primary/15 text-primary max-w-[10rem] truncate"
                            title={browsedWorkspace.name}
                          >
                            {browsedWorkspace.name}
                          </span>
                        </>
                      )}
                    </div>
                  )}

                  {scopeLocked && (
                    <div className="flex flex-nowrap items-center gap-1 text-xs min-h-[28px] max-w-full overflow-x-auto overflow-y-hidden py-0.5 [scrollbar-width:thin]">
                      <span
                        className={cn(
                          "shrink-0 rounded px-1.5 py-0.5",
                          workspaceScope === "__shared__"
                            ? "bg-primary/15 text-primary"
                            : "text-[var(--text-secondary)]"
                        )}
                      >
                        /
                      </span>
                      {workspaceScope !== "__shared__" && (
                        <>
                          <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-secondary)]" />
                          <span
                            className="shrink-0 rounded px-1.5 py-0.5 bg-primary/15 text-primary max-w-[10rem] truncate"
                            title={workspaces.find((w) => w.id === workspaceScope)?.name}
                          >
                            {workspaces.find((w) => w.id === workspaceScope)?.name ?? workspaceScope}
                          </span>
                        </>
                      )}
                    </div>
                  )}

                  <div
                    className={cn(
                      "rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] max-h-48 overflow-y-auto",
                      scopeLocked && "pointer-events-none opacity-90"
                    )}
                  >
                    {scopeLocked ? (
                      <>
                        <button
                          type="button"
                          tabIndex={-1}
                          className={cn(
                            "w-full flex items-center gap-2 px-3 py-2.5 text-left text-xs transition-colors border-b border-[var(--border-color)]",
                            workspaceScope === "__shared__"
                              ? "bg-primary/15 text-primary"
                              : "text-[var(--text-primary)]"
                          )}
                        >
                          <Layers className="h-3.5 w-3.5 shrink-0 text-[var(--text-secondary)]" />
                          <span className="flex-1 min-w-0 font-medium font-mono tracking-tight">/</span>
                          {workspaceScope === "__shared__" && (
                            <Check className="h-3.5 w-3.5 shrink-0 text-primary" />
                          )}
                        </button>
                        {workspaces.map((ws) => (
                          <button
                            key={ws.id}
                            type="button"
                            tabIndex={-1}
                            className={cn(
                              "w-full flex items-center gap-2 px-3 py-2.5 text-left text-xs transition-colors border-b border-[var(--border-color)] last:border-b-0",
                              workspaceScope === ws.id
                                ? "bg-primary/15 text-primary"
                                : "text-[var(--text-primary)]"
                            )}
                          >
                            <FolderOpen className="h-3.5 w-3.5 shrink-0 text-[var(--text-secondary)]" />
                            <span className="flex-1 min-w-0 font-medium truncate" title={ws.name}>
                              {ws.name}/
                            </span>
                            {workspaceScope === ws.id && (
                              <Check className="h-3.5 w-3.5 shrink-0 text-primary" />
                            )}
                          </button>
                        ))}
                      </>
                    ) : scopeBrowseWorkspaceId === null ? (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            const root = rootWorkspaceId(workspacesForScope);
                            setWorkspaceScope(root ?? "__shared__");
                            setScopeBrowseWorkspaceId(null);
                          }}
                          className={cn(
                            "w-full flex items-center gap-2 px-3 py-2.5 text-left text-xs transition-colors border-b border-[var(--border-color)]",
                            workspaceScope === "__shared__"
                              ? "bg-primary/15 text-primary"
                              : "text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                          )}
                        >
                          <Layers className="h-3.5 w-3.5 shrink-0 text-[var(--text-secondary)]" />
                          <span className="flex-1 min-w-0 font-medium font-mono tracking-tight">/</span>
                          {workspaceScope === "__shared__" && (
                            <Check className="h-3.5 w-3.5 shrink-0 text-primary" />
                          )}
                        </button>
                        {workspaces.map((ws) => (
                          <button
                            key={ws.id}
                            type="button"
                            onClick={() => {
                              setWorkspaceScope(ws.id);
                              setScopeBrowseWorkspaceId(ws.id);
                            }}
                            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border-b border-[var(--border-color)] last:border-b-0"
                          >
                            <FolderOpen className="h-3.5 w-3.5 shrink-0 text-[var(--text-secondary)]" />
                            <span>{ws.name}/</span>
                            <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-secondary)] ml-auto" />
                          </button>
                        ))}
                      </>
                    ) : (
                      <div className="px-3 py-6 text-center text-xs text-[var(--text-secondary)]">
                        No subfolders found
                      </div>
                    )}
                  </div>
                  <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                    {`Injected for the “${workspaces.find((w) => w.id === activeWorkspaceScope)?.name ?? "selected"}” workspace at repo root (` +
                      `/` +
                      `).`}
                  </p>
                </>
              )}
            </div>
          )}

          <div className="grid gap-2">
            <Label className="text-xs text-[var(--text-secondary)]">Secret name</Label>
            <Input
              value={secretName}
              onChange={(e) => setSecretName(e.target.value)}
              onPaste={onEnvPaste}
              placeholder="e.g. DATABASE_URL or paste FOO=bar"
              disabled={scopeLocked || isParsingEnv}
              className="h-8 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] disabled:opacity-60 focus-visible:ring-1 focus-visible:ring-[var(--border-color)]"
            />
          </div>

          <div className="grid gap-2">
            <Label className="text-xs text-[var(--text-secondary)]">Secret key</Label>
            <div className="relative">
              <Input
                type={showSecretKey ? "text" : "password"}
                value={secretKey}
                onChange={(e) => setSecretKey(e.target.value)}
                onPaste={onEnvPaste}
                placeholder="Value or paste multiple KEY=value lines"
                disabled={isParsingEnv}
                className="h-8 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] pr-10 focus-visible:ring-1 focus-visible:ring-[var(--border-color)]"
              />
              <button
                type="button"
                onClick={() => setShowSecretKey(!showSecretKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                {showSecretKey ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>

          {mode === "add" && isParsingEnv && (
            <p className="text-[11px] text-[var(--text-secondary)] flex items-center gap-2">
              <Spinner className="h-3.5 w-3.5" />
              Parsing pasted .env…
            </p>
          )}

          {parseError && (
            <p className="text-[11px] text-red-500 flex items-center gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              {parseError}
            </p>
          )}

          {mode === "add" && detectedEntries.length > 0 && (
            <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] overflow-hidden flex flex-col min-h-0 max-h-48 sm:max-h-56">
              <div className="flex flex-wrap items-center justify-between gap-2 px-2.5 py-1.5 border-b border-[var(--border-color)] bg-[var(--bg-primary)] shrink-0">
                <p className="text-[9px] font-medium text-[var(--text-tertiary)] uppercase tracking-wide">
                  {isBulkMode
                    ? `Add variables (${selectedIndices.size}/${detectedEntries.length})`
                    : `Pick a variable (${detectedEntries.length})`}
                </p>
                <div className="flex items-center gap-2 flex-wrap justify-end">
                  {isBulkMode && (
                    <>
                      <button
                        type="button"
                        onClick={selectAllDetected}
                        className="text-[10px] text-primary hover:underline"
                      >
                        Select all
                      </button>
                      <span className="text-[var(--border-color)]">|</span>
                      <button
                        type="button"
                        onClick={deselectAllDetected}
                        className="text-[10px] text-[var(--text-secondary)] hover:underline"
                      >
                        Deselect all
                      </button>
                      <span className="text-[var(--border-color)]">|</span>
                    </>
                  )}
                  <button
                    type="button"
                    onClick={clearEnvImport}
                    className="text-[10px] text-primary hover:underline"
                  >
                    Clear
                  </button>
                </div>
              </div>
              <div className="overflow-y-auto overscroll-contain divide-y divide-[var(--border-color)] min-h-0 flex-1">
                {detectedEntries.map((e, idx) =>
                  isBulkMode ? (
                    <label
                      key={`${e.key}-${idx}`}
                      className="flex items-center gap-2.5 px-2.5 py-2 text-[11px] hover:bg-[var(--bg-tertiary)] cursor-pointer"
                    >
                      <Checkbox
                        checked={selectedIndices.has(idx)}
                        onCheckedChange={() => toggleIndex(idx)}
                        className="border-[var(--border-color)] data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                      />
                      <span className="font-mono text-[var(--text-primary)] shrink-0 min-w-0 flex-1 truncate">
                        {e.key}
                      </span>
                      <span className="text-[var(--text-secondary)] truncate max-w-[40%]" title={e.value}>
                        {maskValue(e.value)}
                      </span>
                    </label>
                  ) : (
                    <button
                      key={`${e.key}-${idx}`}
                      type="button"
                      onClick={() => applyDetectedEntry(e)}
                      className="w-full text-left px-2.5 py-2 text-[11px] hover:bg-[var(--bg-tertiary)] transition-colors flex justify-between gap-2"
                    >
                      <span className="font-mono text-[var(--text-primary)] shrink-0">{e.key}</span>
                      <span className="text-[var(--text-secondary)] truncate" title={e.value}>
                        {maskValue(e.value)}
                      </span>
                    </button>
                  )
                )}
              </div>
            </div>
          )}

          {mode === "add" && (
            <div className="space-y-2">
              <div className="relative flex items-center gap-3 py-1">
                <div className="h-px flex-1 bg-[var(--border-color)]" />
                <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
                  or upload
                </span>
                <div className="h-px flex-1 bg-[var(--border-color)]" />
              </div>
              <label className="text-xs font-medium text-[var(--text-primary)]">Upload .env file</label>
              <div className="relative">
                <input
                  ref={fileInputRef}
                  id={envFileInputId}
                  type="file"
                  accept=".env,.env.*,.local,text/plain"
                  onChange={onPickEnvFile}
                  className="hidden"
                />
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={cn(
                    "relative flex flex-col items-center justify-center w-full min-h-[7.5rem] border-2 border-dashed rounded-lg cursor-pointer transition-colors",
                    lastImportViaFile && detectedEntries.length > 0 && !parseError
                      ? "border-[#10b981] bg-[#10b981]/5"
                      : isDragOver
                        ? "border-primary bg-primary/10"
                        : "border-[var(--border-color)] hover:border-primary hover:bg-[var(--bg-secondary)]"
                  )}
                  onClick={() =>
                    !isParsingEnv && document.getElementById(envFileInputId)?.click()
                  }
                >
                  {lastImportViaFile && detectedEntries.length > 0 && !parseError && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        clearEnvImport();
                      }}
                      className="absolute top-2 right-2 p-1 rounded-full bg-[var(--bg-tertiary)] hover:bg-[var(--border-color)] text-[var(--text-secondary)] transition-colors"
                      title="Clear"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {isParsingEnv ? (
                    <Spinner className="h-6 w-6 text-[var(--text-secondary)]" />
                  ) : lastImportViaFile && detectedEntries.length > 0 && !parseError ? (
                    <>
                      <CheckCircle2 className="h-7 w-7 text-[#10b981] mb-1.5" />
                      <p className="text-xs text-[#10b981] font-medium">
                        {detectedEntries.length} variable{detectedEntries.length === 1 ? "" : "s"} detected
                      </p>
                      <p className="text-[10px] text-[var(--text-secondary)] mt-0.5">
                        Drop another file to replace
                      </p>
                    </>
                  ) : (
                    <>
                      <CloudUpload className="h-6 w-6 text-[var(--text-secondary)] mb-2" />
                      <p className="text-xs text-[var(--text-primary)] font-medium">
                        Click to upload .env file
                      </p>
                      <p className="text-[10px] text-[var(--text-secondary)] mt-1">
                        or drag and drop
                      </p>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="p-3 rounded-lg bg-primary/10 border border-primary/20">
            <p className="text-[10px] text-primary leading-relaxed">
              This secret will be encrypted and stored confidentially in Secrets Manager. We never store secret values - only references to them.
            </p>
          </div>
        </div>

        <DialogFooter className="shrink-0 border-t border-[var(--border-color)] bg-[var(--bg-primary)] px-6 py-4 gap-2 sm:gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
            className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting || (!canSubmitBulk && !canSubmitSingle)}
            className="text-xs bg-primary hover:bg-primary/90 text-primary-foreground disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <Spinner className="h-3.5 w-3.5 mr-2" />
                {isBulkMode
                  ? "Adding…"
                  : mode === "add"
                    ? "Creating..."
                    : mode === "rotate"
                      ? "Rotating…"
                      : "Configuring..."}
              </>
            ) : isBulkMode && selectedIndices.size > 0 ? (
              `Add ${selectedIndices.size} secret${selectedIndices.size === 1 ? "" : "s"}`
            ) : mode === "add" ? (
              "Create Secret"
            ) : mode === "rotate" ? (
              "Rotate secret"
            ) : (
              "Configure"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
