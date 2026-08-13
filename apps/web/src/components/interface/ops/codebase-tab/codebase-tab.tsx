"use client";

import { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { NoProjectEmptyState } from "./no-project-empty-state";
import { CodebaseEmptyState } from "../empty-states";
import {
  withCodebaseIndexingSign,
} from "./codebase-indexing-sign";
import {
  Code,
  FileCode,
  ChevronRight,
  ChevronDown,
  GitBranch,
  ExternalLink,
  Copy,
  Check,
  FolderOpen,
  Folder,
  Search,
  X,
  Package,
  Database,
  SquareMousePointer,
  Settings,
  FileJson,
  Boxes,
  Download,
  RefreshCw,
  AlertCircle,
  Plus,
  Github,
  MoreVertical,
  Unplug,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { FileIcon } from "@/components/ui/file-icon";
import { Skeleton } from "@/components/ui/skeleton";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { useSyntaxTheme, MONO_FONT } from "@/components/chat/code-block/syntax-theme";
import { useConsoleIndexing } from "@/hooks/useConsoleEvents";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Avoid stale tree/file content when the user hits Refresh (browser HTTP cache). */
const CODEBASE_FETCH_INIT: RequestInit = { credentials: "include", cache: "no-store" };

// ============================================================================
// Types
// ============================================================================

interface CodeVersion {
  id: string;
  created_at: string;
  created_by: string;
  label: string;
  status: string;
  commit_sha: string;
}

interface CodeFile {
  name: string;
  path: string;
  lines?: number;
  description?: string;
  last_modified?: string;
  content?: string;
}

interface ServiceFolder {
  name: string;
  path: string;
  files: CodeFile[];
}

interface FileTreeNode {
  id: string;
  name: string;
  path: string;
  type: "folder" | "file" | "directory";
  children?: FileTreeNode[];
  lines?: number;
  description?: string;
  icon?: React.ReactNode;
  content?: string;
  metadata?: {
    handlers?: number;
    dependencies?: string[];
    endpoints?: string[];
  };
}

interface OpenTab {
  id: string;
  name: string;
  path: string;
  content: string;
  language: string;
  lines?: number;
  metadata?: any;
}

// API response types
interface CodebaseResponse {
  current_version: string;
  versions: CodeVersion[];
  file_tree: FileTreeNode[];
  services: ServiceFolder[];
  shared?: {
    path: string;
    files: CodeFile[];
  };
  api_spec?: {
    path: string;
    format: string;
    endpoints: number;
    content: string;
  };
  readme?: string;
  stats: {
    total_files: number;
    total_lines: number;
    total_folders: number;
  };
  branch?: string;
  source?: string;
}

interface CodebaseTabProps {
  projectId: string;
  threadId?: string | null;
  mockData?: any;
  hasProject?: boolean;
  onAddRepository?: () => void;
}

// ============================================================================
// Utility Functions
// ============================================================================

function getFileIcon(filename: string): React.ReactNode {
  return <FileIcon filename={filename} size={12} />;
}

function getFolderIcon(folderName: string): React.ReactNode {
  switch (folderName) {
    case "services":
      return <Package className="h-3.5 w-3.5 text-[var(--text-secondary)]" />;
    case "shared":
      return <FolderOpen className="h-3.5 w-3.5 text-[var(--text-secondary)]" />;
    case "api":
      return <SquareMousePointer className="h-3.5 w-3.5 text-[var(--text-secondary)]" />;
    case "database":
      return <Database className="h-3.5 w-3.5 text-[var(--text-secondary)]" />;
    case "infrastructure":
      return <Settings className="h-3.5 w-3.5 text-[var(--text-secondary)]" />;
    case "terraform":
      return <Boxes className="h-3.5 w-3.5 text-[var(--text-secondary)]" />;
    case "scripts":
      return <Code className="h-3.5 w-3.5 text-[var(--text-secondary)]" />;
    default:
      return <Folder className="h-3.5 w-3.5 text-[var(--text-secondary)]" />;
  }
}

function buildFileTreeFromResponse(data: any): FileTreeNode[] {
  // If API returns pre-built file_tree, use it
  if (data.file_tree && data.file_tree.length > 0) {
    const processed = data.file_tree.map((node: FileTreeNode) => addIconsToTree(node));
    // Deduplicate top-level nodes — API can return the same node twice
    const seenIds = new Set<string>();
    return processed.filter((node: FileTreeNode) => {
      if (seenIds.has(node.id)) return false;
      seenIds.add(node.id);
      return true;
    });
  }

  const tree: FileTreeNode[] = [];

  // Handle mock data structure with lambda_handlers.services
  const services = data.services || data.lambda_handlers?.services || [];
  
  // Services/Functions folder
  if (services.length > 0) {
    const servicesFolder: FileTreeNode = {
      id: "services",
      name: data.lambda_handlers ? "functions" : "services",
      path: data.lambda_handlers?.path || "services/",
      type: "folder",
      icon: getFolderIcon("services"),
      children: services.map((service: ServiceFolder) => ({
        id: `service-${service.name}`,
        name: service.name,
        path: service.path,
        type: "folder" as const,
        icon: <Code className="h-3.5 w-3.5 text-[var(--text-secondary)]" />,
        children: service.files.map((file: CodeFile) => ({
          id: `${service.name}-${file.name}`,
          name: file.name,
          path: file.path || `${service.path}${file.name}`,
          type: "file" as const,
          lines: file.lines,
          content: file.content || (service as any).preview,
          icon: getFileIcon(file.name),
        })),
      })),
    };
    tree.push(servicesFolder);
  }

  // Handle terraform/infrastructure folder from mock data - build nested structure
  if (data.terraform?.files?.length > 0) {
    const basePath = data.terraform.path || "terraform/";
    const infraFolder: FileTreeNode = {
      id: "infrastructure",
      name: "infrastructure",
      path: basePath,
      type: "folder",
      icon: getFolderIcon("terraform"),
      children: [],
    };
    
    // Build nested folder structure from file paths
    const folderMap = new Map<string, FileTreeNode>();
    folderMap.set("", infraFolder);
    
    data.terraform.files.forEach((file: any) => {
      const parts = file.name.split("/");
      const fileName = parts.pop()!;
      
      // Create folder hierarchy
      let currentPath = "";
      let parentFolder = infraFolder;
      
      for (const folderName of parts) {
        const newPath = currentPath ? `${currentPath}/${folderName}` : folderName;
        
        if (!folderMap.has(newPath)) {
          const newFolder: FileTreeNode = {
            id: `infra-${newPath.replace(/\//g, '-')}`,
            name: folderName,
            path: `${basePath}${newPath}/`,
            type: "folder",
            icon: getFolderIcon(folderName),
            children: [],
          };
          parentFolder.children!.push(newFolder);
          folderMap.set(newPath, newFolder);
        }
        
        parentFolder = folderMap.get(newPath)!;
        currentPath = newPath;
      }
      
      // Add file to its parent folder
      parentFolder.children!.push({
        id: `terraform-${file.name.replace(/\//g, '-')}`,
        name: fileName,
        path: `${basePath}${file.name}`,
        type: "file",
        lines: file.lines,
        content: data.terraform.preview,
        icon: getFileIcon(fileName),
      });
    });
    
    tree.push(infraFolder);
  }

  // Shared folder
  if (data.shared && data.shared.files?.length > 0) {
    const sharedFolder: FileTreeNode = {
      id: "shared",
      name: "shared",
      path: "shared/",
      type: "folder",
      icon: getFolderIcon("shared"),
      children: data.shared.files.map((file: CodeFile) => ({
        id: `shared-${file.name}`,
        name: file.name,
        path: file.path || `shared/${file.name}`,
        type: "file" as const,
        lines: file.lines,
        content: file.content,
        icon: getFileIcon(file.name),
      })),
    };
    tree.push(sharedFolder);
  }

  // API folder
  if (data.api_spec) {
    const apiFolder: FileTreeNode = {
      id: "api",
      name: "api",
      path: "api/",
      type: "folder",
      icon: getFolderIcon("api"),
      children: [
        {
          id: "openapi-spec",
          name: data.api_spec.path?.split('/').pop() || "openapi.yaml",
          path: data.api_spec.path || "api/openapi.yaml",
          type: "file",
          lines: data.api_spec.endpoints * 10,
          content: data.api_spec.content || data.api_spec.preview,
          icon: <FileJson className="h-3 w-3 text-[var(--text-secondary)]" />,
          metadata: {
            endpoints: data.api_spec.endpoints,
          },
        },
      ],
    };
    tree.push(apiFolder);
  }

  // Handle migrations folder from mock data
  if (data.migrations?.files?.length > 0) {
    const migrationsFolder: FileTreeNode = {
      id: "migrations",
      name: "migrations",
      path: data.migrations.path || "migrations/",
      type: "folder",
      icon: getFolderIcon("database"),
      children: data.migrations.files.map((file: any) => ({
        id: `migration-${file.name}`,
        name: file.name,
        path: `${data.migrations.path || 'migrations/'}${file.name}`,
        type: "file" as const,
        lines: file.lines || 50,
        content: file.content,
        icon: getFileIcon(file.name),
      })),
    };
    tree.push(migrationsFolder);
  }

  return tree;
}

function addIconsToTree(node: FileTreeNode, parentPath = ""): FileTreeNode {
  // Use the full path as the ID to guarantee uniqueness across same-named files
  const uniqueId = node.path || (parentPath ? `${parentPath}/${node.name}` : node.name);
  if (node.type === "folder" || node.type === "directory") {
    const processedChildren = node.children?.map((child) => addIconsToTree(child, uniqueId));
    // Deduplicate children by ID — API can return the same file multiple times
    const seenIds = new Set<string>();
    const dedupedChildren = processedChildren?.filter((child) => {
      if (seenIds.has(child.id)) return false;
      seenIds.add(child.id);
      return true;
    });
    return {
      ...node,
      id: uniqueId,
      icon: node.type === "directory" ? undefined : getFolderIcon(node.name),
      children: dedupedChildren,
    };
  }
  return {
    ...node,
    id: uniqueId,
    icon: getFileIcon(node.name),
  };
}

function searchTree(nodes: FileTreeNode[], query: string): FileTreeNode[] {
  if (!query) return nodes;

  const lowerQuery = query.toLowerCase();
  const results: FileTreeNode[] = [];

  function search(node: FileTreeNode): boolean {
    const matches = node.name.toLowerCase().includes(lowerQuery);

    if ((node.type === "folder" || node.type === "directory") && node.children) {
      const matchingChildren = node.children.filter((child) => search(child));
      if (matchingChildren.length > 0 || matches) {
        results.push({
          ...node,
          children: matchingChildren.length > 0 ? matchingChildren : node.children,
        });
        return true;
      }
    } else if (matches) {
      results.push(node);
      return true;
    }

    return matches;
  }

  nodes.forEach((node) => search(node));
  return results;
}

function getFileStats(tree: FileTreeNode[]): { totalFiles: number; totalLines: number; totalFolders: number } {
  let totalFiles = 0;
  let totalLines = 0;
  let totalFolders = 0;

  function traverse(node: FileTreeNode) {
    if (node.type === "folder" || node.type === "directory") {
      totalFolders++;
      node.children?.forEach(traverse);
    } else {
      totalFiles++;
      totalLines += node.lines || 0;
    }
  }

  tree.forEach(traverse);
  return { totalFiles, totalLines, totalFolders };
}

/** Match event path to tab path (sandbox tree uses relative paths; diffs may use basename or segments). */
function pathsMatch(tabPath: string, eventPath: string): boolean {
  const n = (p: string) => p.replace(/\\/g, "/").replace(/^\/+/, "").replace(/^\/home\/user\/project-workspace\/?/, "");
  const a = n(tabPath);
  const b = n(eventPath);
  if (a === b) return true;
  if (a.endsWith("/" + b) || a.endsWith(b)) return true;
  if (b.endsWith("/" + a) || b.endsWith(a)) return true;
  const baseA = a.split("/").pop() || a;
  const baseB = b.split("/").pop() || b;
  return baseA === baseB && (a.includes(b) || b.includes(a));
}

function getLanguage(filename: string): string {
  const lower = filename.toLowerCase();
  if (lower === "dockerfile") return "docker";
  if (lower === "makefile") return "makefile";
  const ext = lower.split(".").pop() || "";
  const map: Record<string, string> = {
    py: "python", ts: "typescript", tsx: "tsx", js: "javascript", jsx: "jsx",
    rb: "ruby", go: "go", rs: "rust", java: "java", kt: "kotlin", swift: "swift",
    php: "php", cs: "csharp", cpp: "cpp", c: "c", h: "c", hpp: "cpp",
    yaml: "yaml", yml: "yaml", json: "json", toml: "toml", xml: "xml",
    html: "html", css: "css", scss: "scss", sql: "sql", sh: "bash",
    md: "markdown", txt: "text", tf: "hcl", graphql: "graphql", lua: "lua", r: "r",
  };
  return map[ext] || "text";
}

// ============================================================================
// Components
// ============================================================================

function DisconnectRepoModal({
  repoName,
  projectId,
  open,
  onOpenChange,
  onDisconnected,
}: {
  repoName: string;
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDisconnected?: () => void;
}) {
  const [confirmText, setConfirmText] = useState("");
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const matches = confirmText === repoName;

  const handleConfirm = async () => {
    if (!matches) return;
    setIsDisconnecting(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/api/projects/${projectId}/repositories/${encodeURIComponent(repoName)}`,
        { method: "DELETE", credentials: "include" },
      );
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `Failed to disconnect (${res.status})`);
      }
      onOpenChange(false);
      setConfirmText("");
      onDisconnected?.();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsDisconnecting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) { setConfirmText(""); setError(null); } }}>
      <DialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] max-w-md">
        <DialogHeader>
          <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
            Disconnect repository
          </DialogTitle>
          <DialogDescription className="text-xs text-[var(--text-secondary)] leading-relaxed">
            This will remove <span className="font-medium text-[var(--text-primary)]">{repoName}</span> from this project. Your code on GitHub will not be affected.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 pt-1">
          <p className="text-[11px] text-[var(--text-secondary)]">
            Type <strong className="text-red-500 font-medium">{repoName}</strong> to confirm:
          </p>
          <Input
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder={repoName}
            className="h-8 text-xs bg-[var(--bg-secondary)] border-red-500/30 text-[var(--text-primary)] focus:border-red-500 focus:ring-red-500/20 placeholder:text-[var(--text-secondary)]/40"
          />
          {error && <p className="text-xs text-red-500">{error}</p>}
          <div className="flex gap-2 justify-end pt-1">
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              onClick={() => { onOpenChange(false); setConfirmText(""); setError(null); }}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={!matches || isDisconnecting}
              onClick={handleConfirm}
              className="h-7 text-xs bg-red-500 hover:bg-red-600 text-white disabled:opacity-40"
            >
              {isDisconnecting ? "Disconnecting..." : "Disconnect"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function FileTreeItem({
  node,
  level = 0,
  expandedFolders,
  onToggle,
  onFileSelect,
  selectedFileId,
  projectId,
  onRepoDisconnected,
}: {
  node: FileTreeNode;
  level?: number;
  expandedFolders: Set<string>;
  onToggle: (id: string) => void;
  onFileSelect: (node: FileTreeNode) => void;
  selectedFileId?: string;
  projectId?: string;
  onRepoDisconnected?: () => void;
}) {
  const isExpanded = expandedFolders.has(node.id);
  const isSelected = selectedFileId === node.id;
  const [disconnectOpen, setDisconnectOpen] = useState(false);

  if (node.type === "directory") {
    return (
      <div className={cn(level > 0 && "mt-1")}>
        {projectId && (
          <DisconnectRepoModal
            repoName={node.name}
            projectId={projectId}
            open={disconnectOpen}
            onOpenChange={setDisconnectOpen}
            onDisconnected={onRepoDisconnected}
          />
        )}
        <div className="group/dir relative flex items-center border-b border-[var(--border-color)] bg-[var(--bg-secondary)]/30 hover:bg-[var(--bg-secondary)]/50 transition-colors">
          <button
            onClick={() => onToggle(node.id)}
            className="flex-1 flex items-center gap-2 px-3 py-1.5 text-[11px] font-medium uppercase [font-family:var(--font-space-grotesk)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            {isExpanded ? (
              <ChevronDown className="h-3 w-3 flex-shrink-0" />
            ) : (
              <ChevronRight className="h-3 w-3 flex-shrink-0" />
            )}
            <Github className="h-3.5 w-3.5 flex-shrink-0" />
            <span className="truncate">{node.name}</span>
          </button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                onClick={(e) => e.stopPropagation()}
                className="opacity-0 group-hover/dir:opacity-100 mr-2 h-5 w-5 flex items-center justify-center rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-all flex-shrink-0"
              >
                <MoreVertical className="h-3.5 w-3.5" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44 bg-[var(--bg-primary)] border-[var(--border-color)]">
              <DropdownMenuItem
                onClick={() => setDisconnectOpen(true)}
                className="flex items-center gap-2 p-2 cursor-pointer text-red-500 hover:bg-red-500/10 focus:bg-red-500/10 focus:text-red-500"
              >
                <Unplug className="h-3.5 w-3.5" />
                <span className="text-xs">Disconnect Repo</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        {isExpanded && node.children && (
          <div className="pb-1">
            {node.children.map((child) => (
              <FileTreeItem
                key={child.id}
                node={child}
                level={0}
                expandedFolders={expandedFolders}
                onToggle={onToggle}
                onFileSelect={onFileSelect}
                selectedFileId={selectedFileId}
                projectId={projectId}
                onRepoDisconnected={onRepoDisconnected}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  if (node.type === "folder") {
    return (
      <div>
        <button
          onClick={() => onToggle(node.id)}
          className={cn(
            "w-full flex items-center gap-2 px-2 py-1.5 text-xs rounded transition-colors hover:bg-[var(--bg-secondary)]",
            isExpanded && "bg-[var(--bg-secondary)]"
          )}
          style={{ paddingLeft: `${level * 12 + 8}px` }}
        >
          {isExpanded ? (
            <ChevronDown className="h-3 w-3 text-[var(--text-secondary)] flex-shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 text-[var(--text-secondary)] flex-shrink-0" />
          )}
          {node.icon}
          <span className="font-medium text-[var(--text-primary)] truncate">{node.name}</span>
          {node.children && (
            <span className="ml-auto text-[9px] text-[var(--text-secondary)] flex-shrink-0">
              {node.children.length}
            </span>
          )}
        </button>
        {isExpanded && node.children && (
          <div>
            {node.children.map((child) => (
              <FileTreeItem
                key={child.id}
                node={child}
                level={level + 1}
                expandedFolders={expandedFolders}
                onToggle={onToggle}
                onFileSelect={onFileSelect}
                selectedFileId={selectedFileId}
                projectId={projectId}
                onRepoDisconnected={onRepoDisconnected}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <button
      onClick={() => onFileSelect(node)}
      className={cn(
        "w-full flex items-center gap-2 px-2 py-1.5 text-xs rounded transition-colors",
        isSelected
          ? "bg-[#10b981]/10 text-[#10b981]"
          : "text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]"
      )}
      style={{ paddingLeft: `${level * 12 + 8}px` }}
    >
      <span className="w-3 flex-shrink-0" />
      {node.icon}
      <span className="truncate flex-1 text-left">{node.name}</span>
      {node.lines && (
        <span className="text-[9px] text-[var(--text-secondary)] flex-shrink-0">{node.lines}L</span>
      )}
    </button>
  );
}

// Empty state is now imported from empty-states.tsx

/** Center pane when no file is open. While `loading`, subtitle is “Loading codebase” instead of the tree hint. */
function CodebaseViewerEmptyPrompt({ loading = false }: { loading?: boolean }) {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center max-w-md px-4">
        <div className="h-16 w-16 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-2">
          <FileCode className="h-7 w-7 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-medium text-[var(--text-primary)] mb-2">No file selected</h2>
        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          {loading ? "Loading codebase" : "Select a file from the tree to view its contents"}
        </p>
      </div>
    </div>
  );
}

/** Same row geometry as FileTreeItem: gap-2, py-1.5, paddingLeft = level * 12 + 8 */
function SkeletonTreeRow({
  level,
  kind,
  expanded,
  nameWidthClass,
}: {
  level: number;
  kind: "folder" | "file";
  expanded?: boolean;
  nameWidthClass: string;
}) {
  const sk = "bg-[var(--border-color)]/55 dark:bg-[var(--border-color)]/80";
  return (
    <div
      className="w-full flex items-center gap-2 px-2 py-1.5 text-xs rounded"
      style={{ paddingLeft: level * 12 + 8 }}
    >
      {kind === "folder" ? (
        expanded ? (
          <ChevronDown className="h-3 w-3 text-[var(--text-secondary)] shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 text-[var(--text-secondary)] shrink-0" />
        )
      ) : (
        <span className="w-3 shrink-0" aria-hidden />
      )}
      {kind === "folder" ? (
        <Folder className="h-3.5 w-3.5 text-primary/80 shrink-0" />
      ) : (
        <FileCode className="h-3.5 w-3.5 text-[var(--text-secondary)] shrink-0 opacity-80" />
      )}
      <Skeleton className={cn("h-3 rounded flex-1 min-w-0", nameWidthClass, sk)} />
      {kind === "folder" ? (
        <Skeleton className={cn("h-2.5 w-4 rounded shrink-0 ml-auto", sk)} />
      ) : (
        <Skeleton className={cn("h-2.5 w-7 rounded shrink-0", sk)} />
      )}
    </div>
  );
}

/** Loading shell: matches Codebase header, search+tree (FileTreeItem layout), and empty viewer pane. */
function CodebaseTabSkeleton() {
  const treeLayout: {
    level: number;
    kind: "folder" | "file";
    expanded?: boolean;
    nameW: string;
  }[] = [
    { level: 0, kind: "folder", expanded: true, nameW: "max-w-[5rem]" },
    { level: 1, kind: "folder", expanded: true, nameW: "max-w-[4.5rem]" },
    { level: 2, kind: "file", nameW: "max-w-[7rem]" },
    { level: 2, kind: "file", nameW: "max-w-[6rem]" },
    { level: 2, kind: "file", nameW: "max-w-[8rem]" },
    { level: 1, kind: "folder", expanded: false, nameW: "max-w-[5.5rem]" },
    { level: 1, kind: "folder", expanded: true, nameW: "max-w-[4rem]" },
    { level: 2, kind: "file", nameW: "max-w-[9rem]" },
    { level: 0, kind: "folder", expanded: false, nameW: "max-w-[6rem]" },
    { level: 0, kind: "file", nameW: "max-w-[6.5rem]" },
    { level: 0, kind: "file", nameW: "max-w-[5rem]" },
  ];

  return (
    <div className="h-full flex flex-col overflow-hidden bg-[var(--bg-primary)]">
      <div className="border-b border-[var(--border-color)] p-4 shrink-0">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Codebase</h2>
            <div className="flex items-center gap-1.5 mt-1 text-xs text-[var(--text-secondary)]">
              <Skeleton className="h-3 w-8 rounded bg-[var(--border-color)]/60" />
              <span className="opacity-40">•</span>
              <Skeleton className="h-3 w-14 rounded bg-[var(--border-color)]/60" />
              <span className="opacity-40">•</span>
              <Skeleton className="h-3 w-16 rounded bg-[var(--border-color)]/60" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div
              className="p-1.5 rounded-md border border-[var(--border-color)] text-[var(--text-secondary)] opacity-50"
              aria-hidden
            >
              <RefreshCw className="h-4 w-4" />
            </div>
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs border bg-[var(--bg-tertiary)] border-[var(--border-color)] text-[var(--text-secondary)]">
              <GitBranch className="h-3 w-3 shrink-0 opacity-70" />
              <Skeleton className="h-3 w-16 rounded bg-[var(--border-color)]/60" />
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 flex min-w-0 overflow-hidden">
        <div className="w-72 border-r border-[var(--border-color)] flex flex-col overflow-hidden bg-[var(--bg-primary)] shrink-0">
          <div className="p-3 border-b border-[var(--border-color)]">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-secondary)] pointer-events-none z-10" />
              <div className="h-7 w-full rounded-md border border-[var(--border-color)] bg-[var(--bg-secondary)] pl-7 pr-2 flex items-center">
                <Skeleton className="h-2.5 flex-1 max-w-[6.5rem] rounded-sm bg-[var(--border-color)]/55 dark:bg-[var(--border-color)]/80" />
              </div>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-0.5 thin-scrollbar">
            {treeLayout.map((row, i) => (
              <SkeletonTreeRow
                key={i}
                level={row.level}
                kind={row.kind}
                expanded={row.expanded}
                nameWidthClass={row.nameW}
              />
            ))}
          </div>
        </div>

        <div className="flex-1 min-w-0 flex flex-col overflow-hidden bg-[var(--bg-tertiary)]">
          <CodebaseViewerEmptyPrompt loading />
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function CodebaseTab({ projectId, threadId, mockData, hasProject = true, onAddRepository }: CodebaseTabProps) {
  const { prismTheme } = useSyntaxTheme();
  const indexing = useConsoleIndexing(projectId, hasProject);
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
    new Set(["services", "shared", "api"])
  );
  const [openTabs, setOpenTabs] = useState<OpenTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Tab bar scroll indicator
  const tabScrollRef = useRef<HTMLDivElement>(null);
  const [scrollIndicator, setScrollIndicator] = useState({ visible: false, left: 0, width: 0 });

  const updateScrollIndicator = useCallback(() => {
    const el = tabScrollRef.current;
    if (!el) return;
    const { scrollLeft, scrollWidth, clientWidth } = el;
    const isScrollable = scrollWidth > clientWidth;
    if (!isScrollable) {
      setScrollIndicator({ visible: false, left: 0, width: 0 });
      return;
    }
    const thumbWidth = Math.max((clientWidth / scrollWidth) * clientWidth * 0.5, 16);
    const maxScroll = scrollWidth - clientWidth;
    const thumbLeft = maxScroll > 0 ? (scrollLeft / maxScroll) * (clientWidth - thumbWidth) : 0;
    setScrollIndicator({ visible: true, left: thumbLeft, width: thumbWidth });
  }, []);

  useEffect(() => {
    updateScrollIndicator();
  }, [openTabs, updateScrollIndicator]);
  
  // Data fetching state
  const [codebaseData, setCodebaseData] = useState<CodebaseResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Track which source we're using so file content fetches use the same source
  const [codebaseSource, setCodebaseSource] = useState<"github" | "sandbox">("github");
  const [refreshKey, setRefreshKey] = useState(0);
  const pendingTabRefetchRef = useRef(false);
  const openTabsRef = useRef<OpenTab[]>([]);
  const [scrollRequest, setScrollRequest] = useState<{ path: string; line: number } | null>(null);
  const codeScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    openTabsRef.current = openTabs;
  }, [openTabs]);

  // The default (imported) branch — source of truth for the project
  const [defaultBranch, setDefaultBranch] = useState<string | null>(null);
  // The resolved git branch for the currently selected thread (if any)
  const [threadBranch, setThreadBranch] = useState<string | null>(null);
  // User explicitly chose to view the default branch while inside a thread
  const [forceDefaultView, setForceDefaultView] = useState(false);

  // Reset override when thread changes
  useEffect(() => { setForceDefaultView(false); }, [threadId]);

  // Derived: are we viewing a thread-specific branch (not the default)?
  const isViewingThreadBranch = !forceDefaultView && !!threadBranch && threadBranch !== defaultBranch;
  const displayBranch = isViewingThreadBranch ? threadBranch! : (defaultBranch || "main");

  // Helper: fetch tree from GitHub with optional branch override
  const fetchGitHubTree = useCallback(async (branch?: string | null, signal?: AbortSignal) => {
    const refParam = branch ? `?ref=${encodeURIComponent(branch)}` : "";
    const resp = await fetch(
      `${API_URL}/api/projects/${projectId}/codebase${refParam}`,
      { ...CODEBASE_FETCH_INIT, signal }
    );
    if (!resp.ok) return null;
    return resp.json();
  }, [projectId]);

  /** Reload file bodies for open tabs after the tree was refetched (same source/ref as new tree). */
  const refetchOpenTabContents = useCallback(
    async (ctx: { source: "github" | "sandbox"; branch: string | null }, tid: string | null | undefined, pid: string) => {
      const tabs = openTabsRef.current;
      if (tabs.length === 0) return;

      const results = await Promise.all(
        tabs.map(async (tab) => {
          try {
            let fileUrl: string;
            if (ctx.source === "sandbox" && tid) {
              fileUrl = `${API_URL}/api/threads/${tid}/workspace/file?path=${encodeURIComponent(tab.path)}`;
            } else {
              const refParam = ctx.branch ? `&ref=${encodeURIComponent(ctx.branch)}` : "";
              fileUrl = `${API_URL}/api/projects/${pid}/codebase/file?path=${encodeURIComponent(tab.path)}${refParam}`;
            }
            const response = await fetch(fileUrl, CODEBASE_FETCH_INIT);
            if (!response.ok) return { id: tab.id, content: null as string | null };
            const data = await response.json();
            return { id: tab.id, content: (data.content ?? "// File is empty") as string };
          } catch {
            return { id: tab.id, content: null as string | null };
          }
        })
      );

      setOpenTabs((prev) =>
        prev.map((tab) => {
          const r = results.find((x) => x.id === tab.id);
          if (r === undefined || r.content === null) return tab;
          return { ...tab, content: r.content };
        })
      );
    },
    []
  );

  // Demo thread branch mapping (unauthenticated mode)
  const DEMO_THREAD_BRANCHES: Record<string, string> = {
    "1": "patchapi/fix-intake-ws",
    "2": "patchapi/debug-ws-events",
  };

  // Fetch codebase: thread context → default branch
  // When a thread is selected, show its branch; otherwise show the imported branch.
  // Uses AbortController so that rapid thread switches cancel stale in-flight fetches
  // instead of letting them all complete and fight over state.
  useEffect(() => {
    const abortCtrl = new AbortController();
    const { signal } = abortCtrl;

    const fetchCodebase = async () => {
      if (mockData) {
        pendingTabRefetchRef.current = false;
        const baseBranch = mockData.branch || mockData.current_version || "main";
        setCodebaseData(
          refreshKey > 0 ? (structuredClone(mockData) as CodebaseResponse) : mockData
        );
        setCodebaseSource("github");
        setDefaultBranch(baseBranch);

        const demoBranch = threadId && !forceDefaultView ? DEMO_THREAD_BRANCHES[threadId] : null;
        setThreadBranch(demoBranch || null);
        setIsLoading(false);
        return;
      }

      if (!projectId) {
        pendingTabRefetchRef.current = false;
        setIsLoading(false);
        return;
      }

      let tabRefetchCtx: { source: "github" | "sandbox"; branch: string | null } | null = null;

      try {
        setIsLoading(true);
        setError(null);

        // Overlap GitHub tree + thread branch lookup — sequential was tree then branch,
        // which added full round-trips on every thread codebase load.
        const branchPromise =
          threadId && !forceDefaultView
            ? fetch(`${API_URL}/api/threads/${threadId}/workspace/branch`, {
                ...CODEBASE_FETCH_INIT,
                signal,
              })
                .then((r) => (signal.aborted ? null : r.ok ? r.json() : null))
                .catch(() => null)
            : Promise.resolve(null);

        const [defaultData, branchPayload] = await Promise.all([
          fetchGitHubTree(undefined, signal),
          branchPromise,
        ]);
        if (signal.aborted) return;

        const baseBranch = defaultData?.branch || defaultData?.current_version || "main";
        setDefaultBranch(baseBranch);

        if (threadId && !forceDefaultView) {
          const branchFromThread = branchPayload?.branch as string | null | undefined;
          const resolvedBranch =
            branchFromThread && branchFromThread !== baseBranch ? branchFromThread : null;
          if (signal.aborted) return;

          if (resolvedBranch) {
            const sandboxResp = await fetch(
              `${API_URL}/api/threads/${threadId}/workspace/tree`,
              { ...CODEBASE_FETCH_INIT, signal }
            );
            if (signal.aborted) return;

            if (sandboxResp.ok) {
              const data = await sandboxResp.json();
              tabRefetchCtx = { source: "sandbox", branch: resolvedBranch };
              setCodebaseData(data);
              setCodebaseSource("sandbox");
              setThreadBranch(resolvedBranch);
              return;
            }

            const data = await fetchGitHubTree(resolvedBranch, signal);
            if (signal.aborted) return;

            if (data) {
              tabRefetchCtx = { source: "github", branch: resolvedBranch };
              setThreadBranch(resolvedBranch);
              setCodebaseData(data);
              setCodebaseSource("github");
              return;
            }
          }
        }

        if (signal.aborted) return;

        setThreadBranch(null);
        if (defaultData) {
          setCodebaseData(defaultData);
        } else {
          setCodebaseData(null);
        }
        setCodebaseSource("github");
        tabRefetchCtx = { source: "github", branch: null };
      } catch (err) {
        if (signal.aborted) return;
        if (err instanceof Error && !err.message.includes('Unauthorized') && !err.message.includes('Forbidden')) {
          console.error("Failed to fetch codebase:", err);
          setError(err.message);
        } else {
          setCodebaseData(null);
        }
      } finally {
        if (!signal.aborted) {
          setIsLoading(false);
          if (pendingTabRefetchRef.current) {
            pendingTabRefetchRef.current = false;
            if (tabRefetchCtx) {
              void refetchOpenTabContents(tabRefetchCtx, threadId, projectId);
            }
          }
        }
      }
    };

    fetchCodebase();
    return () => abortCtrl.abort();
  }, [projectId, threadId, mockData, refreshKey, fetchGitHubTree, forceDefaultView, refetchOpenTabContents]);

  // Open file from thread (Write/Edit row or diff header) — scroll to edited line like Cursor
  useEffect(() => {
    const handler = (e: Event) => {
      const d = (e as CustomEvent).detail as { path?: string; scrollToLine?: number } | undefined;
      const path = d?.path;
      if (!path) return;
      const scrollToLine = Math.max(1, Number(d?.scrollToLine) || 1);

      window.dispatchEvent(new CustomEvent("switchMainTab", { detail: { tab: "code" } }));

      const existing = openTabs.find((t) => pathsMatch(t.path, path) || t.id === path);
      if (existing) {
        setActiveTabId(existing.id);
        setScrollRequest({ path, line: scrollToLine });
        return;
      }

      const openFromSandbox = () =>
        fetch(`${API_URL}/api/threads/${threadId}/workspace/file?path=${encodeURIComponent(path)}`, CODEBASE_FETCH_INIT)
          .then((r) => (r.ok ? r.json() : null))
          .then((data) => {
            if (!data) return;
            const name = path.includes("/") ? path.split("/").pop()! : path;
            const newTab: OpenTab = {
              id: path,
              name,
              path,
              content: data.content || "// File is empty",
              language: data.language || getLanguage(name),
            };
            setOpenTabs((prev) => [...prev, newTab]);
            setActiveTabId(path);
            setScrollRequest({ path, line: scrollToLine });
          })
          .catch(() => {});

      const openFromGitHub = () => {
        const refParam = threadBranch ? `&ref=${encodeURIComponent(threadBranch)}` : "";
        return fetch(
          `${API_URL}/api/projects/${projectId}/codebase/file?path=${encodeURIComponent(path)}${refParam}`,
          CODEBASE_FETCH_INIT
        )
          .then((r) => (r.ok ? r.json() : null))
          .then((data) => {
            if (!data) return;
            const name = path.includes("/") ? path.split("/").pop()! : path;
            const newTab: OpenTab = {
              id: path,
              name,
              path,
              content: data.content || "// File is empty",
              language: data.language || getLanguage(name),
            };
            setOpenTabs((prev) => [...prev, newTab]);
            setActiveTabId(path);
            setScrollRequest({ path, line: scrollToLine });
          })
          .catch(() => {});
      };

      if (threadId && codebaseSource === "sandbox") void openFromSandbox();
      else if (projectId) void openFromGitHub();
    };
    window.addEventListener("codebaseOpenFile", handler);
    return () => window.removeEventListener("codebaseOpenFile", handler);
  }, [threadId, projectId, openTabs, threadBranch, codebaseSource]);

  const fileTree = useMemo(
    () => (codebaseData ? buildFileTreeFromResponse(codebaseData) : []),
    [codebaseData]
  );

  useEffect(() => {
    const directoryIds = fileTree
      .filter((node) => node.type === "directory")
      .map((node) => node.id);
    if (directoryIds.length > 0) {
      setExpandedFolders((prev) => {
        const next = new Set(prev);
        directoryIds.forEach((id) => next.add(id));
        return next;
      });
    }
  }, [fileTree]);

  const filteredTree = useMemo(() => searchTree(fileTree, searchQuery), [fileTree, searchQuery]);
  const stats = useMemo(() => {
    if (codebaseData?.stats) {
      return {
        totalFiles: codebaseData.stats.total_files || 0,
        totalLines: codebaseData.stats.total_lines || 0,
        totalFolders: codebaseData.stats.total_folders || 0,
      };
    }
    return getFileStats(fileTree);
  }, [codebaseData, fileTree]);

  const activeTab = openTabs.find((tab) => tab.id === activeTabId);

  useEffect(() => {
    if (!scrollRequest || !activeTab) return;
    if (!pathsMatch(activeTab.path, scrollRequest.path)) return;
    const lineCount = Math.max(1, activeTab.content.split("\n").length);
    const line = Math.min(Math.max(1, scrollRequest.line), lineCount);

    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const root = codeScrollRef.current;
        const el = root?.querySelector(`#cb-line-${line}`);
        el?.scrollIntoView({ behavior: "smooth", block: "center" });
        setScrollRequest(null);
      });
    });
    return () => cancelAnimationFrame(raf);
  }, [scrollRequest, activeTabId, activeTab]);

  const handleToggleFolder = (id: string) => {
    const newExpanded = new Set(expandedFolders);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedFolders(newExpanded);
  };

  const handleFileSelect = async (node: FileTreeNode) => {
    if (node.type === "folder" || node.type === "directory") return;

    // Check if tab is already open
    const existingTab = openTabs.find((tab) => tab.id === node.id);
    if (existingTab) {
      setActiveTabId(node.id);
      return;
    }

    // Get content - either from node or fetch from API
    let content = node.content || "// Loading...";
    
    if (!node.content && (projectId || threadId)) {
      try {
        let fileUrl: string;
        if (codebaseSource === "sandbox" && threadId) {
          fileUrl = `${API_URL}/api/threads/${threadId}/workspace/file?path=${encodeURIComponent(node.path)}`;
        } else {
          const refParam = threadBranch ? `&ref=${encodeURIComponent(threadBranch)}` : "";
          fileUrl = `${API_URL}/api/projects/${projectId}/codebase/file?path=${encodeURIComponent(node.path)}${refParam}`;
        }
        const response = await fetch(fileUrl, CODEBASE_FETCH_INIT);
        if (response.ok) {
          const data = await response.json();
          content = data.content || "// File is empty";
        }
      } catch (err) {
        content = "// Failed to load file content";
      }
    }

    // Open new tab
    const newTab: OpenTab = {
      id: node.id,
      name: node.name,
      path: node.path,
      content,
      language: getLanguage(node.name),
      lines: node.lines,
      metadata: node.metadata,
    };

    setOpenTabs([...openTabs, newTab]);
    setActiveTabId(node.id);
  };

  const handleCloseTab = (id: string) => {
    const newTabs = openTabs.filter((tab) => tab.id !== id);
    setOpenTabs(newTabs);

    if (activeTabId === id) {
      setActiveTabId(newTabs.length > 0 ? newTabs[newTabs.length - 1].id : null);
    }
  };

  const handleCopy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRefresh = () => {
    pendingTabRefetchRef.current = true;
    setRefreshKey((k) => k + 1);
  };


  // Loading state
  // No project selected - show empty state
  if (!hasProject) {
    return withCodebaseIndexingSign(<NoProjectEmptyState />, indexing);
  }

  if (isLoading) {
    return withCodebaseIndexingSign(<CodebaseTabSkeleton />, indexing);
  }

  // Error state or empty state - both show the nice empty state
  // (Unauthorized errors in demo mode should show empty state, not error)
  if (error || !codebaseData || fileTree.length === 0) {
    return withCodebaseIndexingSign(<CodebaseEmptyState />, indexing);
  }

  return withCodebaseIndexingSign(
    <div className="h-full flex flex-col overflow-hidden bg-[var(--bg-primary)]">
      {/* Header */}
      <div className="border-b border-[var(--border-color)] p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">Codebase</h2>
              {onAddRepository && (
                <button
                  onClick={onAddRepository}
                  className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  Add Repository
                </button>
              )}
            </div>
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              {stats.totalFiles} files • {stats.totalLines.toLocaleString()} lines • {stats.totalFolders} folders
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRefresh}
              disabled={isLoading && refreshKey > 0}
              className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border border-[var(--border-color)] disabled:opacity-50"
              title="Reload tree and open files from the server"
            >
              <RefreshCw className={cn("h-4 w-4", isLoading && refreshKey > 0 && "animate-spin")} />
            </button>
            <div className={cn(
              "flex items-center gap-1.5 px-2 py-1 rounded-md text-xs border",
              isViewingThreadBranch
                ? "bg-primary/10 border-primary/30 text-primary"
                : "bg-[var(--bg-tertiary)] border-[var(--border-color)] text-[var(--text-secondary)]"
            )}>
              <GitBranch className="h-3 w-3" />
              <span className="font-mono text-[11px] truncate max-w-[160px]">{displayBranch}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Thread branch indicator bar — viewing agent branch */}
      {isViewingThreadBranch && (
        <div className="flex items-center justify-between px-4 py-1.5 bg-primary/5 border-b border-primary/15">
          <div className="flex items-center gap-2 text-[11px] text-primary">
            <AlertCircle className="h-3 w-3" />
            <span>
              Viewing agent changes on <code className="font-mono bg-primary/10 px-1 rounded text-[10px]">{threadBranch}</code>
            </span>
          </div>
          <button
            type="button"
            onClick={() => {
              pendingTabRefetchRef.current = true;
              setForceDefaultView(true);
              setRefreshKey((k) => k + 1);
            }}
            className="text-[10px] text-primary hover:text-primary/80 font-medium flex items-center gap-1 px-2 py-0.5 rounded hover:bg-primary/10 transition-colors"
          >
            <GitBranch className="h-3 w-3" />
            View {defaultBranch || "main"}
          </button>
        </div>
      )}

      {/* Indicator bar — forced to default while thread has a branch */}
      {forceDefaultView && threadBranch && threadBranch !== defaultBranch && (
        <div className="flex items-center justify-between px-4 py-1.5 bg-[var(--bg-secondary)] border-b border-[var(--border-color)]">
          <div className="flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">
            <GitBranch className="h-3 w-3" />
            <span>Viewing source branch <code className="font-mono bg-[var(--bg-tertiary)] px-1 rounded text-[10px]">{defaultBranch || "main"}</code></span>
          </div>
          <button
            type="button"
            onClick={() => {
              pendingTabRefetchRef.current = true;
              setForceDefaultView(false);
              setRefreshKey((k) => k + 1);
            }}
            className="text-[10px] text-primary hover:text-primary/80 font-medium flex items-center gap-1 px-2 py-0.5 rounded hover:bg-primary/10 transition-colors"
          >
            <GitBranch className="h-3 w-3" />
            View {threadBranch}
          </button>
        </div>
      )}

      {/* Main Content - Three Panels */}
      <div className="flex-1 flex min-w-0 overflow-hidden">
        {/* Left Panel - File Tree */}
        <div className="w-72 border-r border-[var(--border-color)] flex flex-col overflow-hidden bg-[var(--bg-primary)]">
          {/* Search */}
          <div className="p-3 border-b border-[var(--border-color)]">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-secondary)]" />
              <Input
                type="text"
                placeholder="Search files..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-7 pl-7 pr-7 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
          </div>

          {/* File Tree */}
          <div className="flex-1 overflow-y-auto p-2">
            {filteredTree.map((node) => (
              <FileTreeItem
                key={node.id}
                node={node}
                expandedFolders={expandedFolders}
                onToggle={handleToggleFolder}
                onFileSelect={handleFileSelect}
                selectedFileId={activeTabId || undefined}
                projectId={projectId}
                onRepoDisconnected={() => setRefreshKey((k) => k + 1)}
              />
            ))}
          </div>
        </div>

        {/* Center Panel - Code Viewer */}
        <div className="flex-1 min-w-0 flex flex-col overflow-hidden bg-[var(--bg-tertiary)]">
          {/* Tab Bar */}
          {openTabs.length > 0 && (
            <div className="flex-shrink-0 relative grid grid-cols-1 bg-[var(--bg-secondary)] border-b border-[var(--border-color)]">
              <div
                ref={tabScrollRef}
                onScroll={updateScrollIndicator}
                className="min-w-0 flex items-center px-2 gap-1 overflow-x-auto thin-scrollbar"
              >
                {openTabs.map((tab) => (
                  <div
                    key={tab.id}
                    className={cn(
                      "flex items-center gap-2 px-3 py-1.5 text-xs transition-colors cursor-pointer group flex-shrink-0",
                      activeTabId === tab.id
                        ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border-b-2 border-[var(--text-primary)]"
                        : "bg-transparent text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]"
                    )}
                    onClick={() => setActiveTabId(tab.id)}
                  >
                    <FileIcon filename={tab.name} size={12} />
                    <span className="whitespace-nowrap">{tab.name}</span>
                    {openTabs.length > 1 && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleCloseTab(tab.id);
                        }}
                        className="opacity-0 group-hover:opacity-100 hover:text-[var(--text-primary)] transition-opacity flex-shrink-0"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
              {/* Custom scroll indicator */}
              {scrollIndicator.visible && (
                <div className="absolute bottom-0 left-0 right-0 h-[2px]">
                  <div
                    className="absolute top-0 h-full rounded-full bg-[var(--text-secondary)] opacity-30 hover:opacity-60 transition-opacity"
                    style={{ left: scrollIndicator.left, width: scrollIndicator.width }}
                  />
                </div>
              )}
            </div>
          )}

          {/* Code Content */}
          {activeTab ? (
            <>
              {/* File Header */}
              <div className="border-b border-[var(--border-color)] px-4 py-2 flex items-center justify-between bg-[var(--bg-secondary)]">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <FileIcon filename={activeTab.name} size={16} />
                    <span className="text-xs font-medium text-[var(--text-primary)] font-mono truncate">
                      {activeTab.path}
                    </span>
                  </div>
                  {activeTab.lines && (
                    <Badge variant="outline" className="text-[9px] border-[var(--border-color)] text-[var(--text-secondary)]">
                      {activeTab.lines} lines
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleCopy(activeTab.content)}
                    className="h-6 px-2 text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  >
                    {copied ? (
                      <>
                        <Check className="h-3 w-3 mr-1" />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3 mr-1" />
                        Copy
                      </>
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-2 text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  >
                    <Download className="h-3 w-3 mr-1" />
                    Download
                  </Button>
                </div>
              </div>

              {/* Code Display — line ids for scroll-to-edit (Cursor-style) */}
              <div ref={codeScrollRef} className="flex-1 overflow-auto">
                <SyntaxHighlighter
                  language={getLanguage(activeTab.name)}
                  style={prismTheme}
                  showLineNumbers
                  lineNumberStyle={{
                    minWidth: "3em",
                    paddingRight: "1em",
                    color: "var(--text-secondary)",
                    opacity: 0.4,
                    fontSize: "11px",
                    userSelect: "none",
                  }}
                  lineProps={(lineNumber) => ({
                    id: `cb-line-${lineNumber}`,
                    style: { display: "block" },
                  })}
                  customStyle={{
                    margin: 0,
                    padding: "16px 0",
                    fontSize: "11px",
                    lineHeight: "1.6",
                    background: "var(--bg-secondary)",
                    borderRadius: 0,
                    height: "100%",
                    fontFamily: MONO_FONT,
                  }}
                  codeTagProps={{
                    style: {
                      fontFamily: MONO_FONT,
                      fontSize: "11px",
                    },
                  }}
                  wrapLines
                  wrapLongLines
                >
                  {activeTab.content}
                </SyntaxHighlighter>
              </div>
            </>
          ) : (
            <CodebaseViewerEmptyPrompt />
          )}
        </div>
      </div>
    </div>,
    indexing
  );
}

// For backward compatibility with old imports
export { CodebaseTab as GeneratedCodeTab };
