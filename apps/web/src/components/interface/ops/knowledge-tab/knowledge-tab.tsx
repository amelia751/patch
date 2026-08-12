"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  ChevronRight,
  ChevronDown,
  FileText,
  Folder,
  FolderOpen,
  Search,
  RefreshCw,
  BookOpen,
  AlertCircle,
  ArrowLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const FETCH_INIT: RequestInit = {
  credentials: "include",
  cache: "no-store",
};

interface TreeNode {
  path: string;
  name: string;
  isDir: boolean;
  size?: number;
  children?: TreeNode[];
}

interface SearchResult {
  path: string;
  matches: Array<{ line: number; text: string }>;
  snippet?: string;
}

interface KnowledgeTabProps {
  projectId: string;
  hasProject: boolean;
}

export function KnowledgeTab({ projectId, hasProject }: KnowledgeTabProps) {
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [fileLoading, setFileLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [healthy, setHealthy] = useState<boolean | null>(null);

  const checkHealth = useCallback(async () => {
    if (!projectId) return;
    try {
      const res = await fetch(
        `${API_URL}/api/projects/${projectId}/knowledge/health`,
        FETCH_INIT,
      );
      setHealthy(res.ok);
    } catch {
      setHealthy(false);
    }
  }, [projectId]);

  const loadTree = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/api/projects/${projectId}/knowledge/tree`,
        FETCH_INIT,
      );
      if (!res.ok) {
        if (res.status === 502 || res.status === 503) {
          setError("Knowledge service is unavailable.");
          setHealthy(false);
          return;
        }
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setTree(data);
      setHealthy(true);

      const topDirs = new Set<string>();
      for (const child of data?.children || []) {
        if (child.isDir) topDirs.add(child.path);
      }
      setExpandedDirs(topDirs);
    } catch (e: any) {
      setError(e.message || "Failed to load knowledge tree");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const loadFile = useCallback(
    async (path: string) => {
      setFileLoading(true);
      setSelectedFile(path);
      setSearchResults(null);
      try {
        const res = await fetch(
          `${API_URL}/api/projects/${projectId}/knowledge/file?path=${encodeURIComponent(path)}`,
          FETCH_INIT,
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const text = await res.text();
        setFileContent(text);
      } catch (e: any) {
        setFileContent(`_Error loading file: ${e.message}_`);
      } finally {
        setFileLoading(false);
      }
    },
    [projectId],
  );

  const doSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) {
        setSearchResults(null);
        return;
      }
      setSearchLoading(true);
      try {
        const res = await fetch(
          `${API_URL}/api/projects/${projectId}/knowledge/search?q=${encodeURIComponent(q)}`,
          FETCH_INIT,
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setSearchResults(data.results || []);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    },
    [projectId],
  );

  useEffect(() => {
    if (projectId && hasProject) {
      checkHealth();
      loadTree();
    }
  }, [projectId, hasProject, checkHealth, loadTree]);

  const toggleDir = (path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  if (!hasProject) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-8">
        <BookOpen className="w-12 h-12 text-[var(--text-secondary)] mb-4 opacity-40" />
        <h3 className="text-sm font-medium text-[var(--text-primary)] mb-2">
          No project selected
        </h3>
        <p className="text-xs text-[var(--text-secondary)] max-w-[280px]">
          Import a GitHub repository to start building your project knowledge base.
        </p>
      </div>
    );
  }

  if (healthy === false && !loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-8">
        <AlertCircle className="w-10 h-10 text-amber-500 mb-4 opacity-60" />
        <h3 className="text-sm font-medium text-[var(--text-primary)] mb-2">
          Knowledge service unavailable
        </h3>
        <p className="text-xs text-[var(--text-secondary)] max-w-[280px] mb-4">
          The knowledge base is currently offline. Run records and patterns will
          be written once the service recovers.
        </p>
        <Button
          size="sm"
          variant="outline"
          onClick={() => { checkHealth(); loadTree(); }}
        >
          <RefreshCw className="w-3 h-3 mr-1.5" />
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-[var(--bg-primary)]">
      {/* Search bar */}
      <div className="px-3 py-2 border-b border-[var(--border-color)]">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-secondary)]" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") doSearch(searchQuery);
              }}
              placeholder="Search knowledge base..."
              className="w-full h-7 pl-8 pr-3 text-[11px] bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-md text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--ring-color)]"
            />
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={() => { loadTree(); setSelectedFile(null); setSearchResults(null); }}
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Tree sidebar */}
        <div className="w-[200px] border-r border-[var(--border-color)] flex-shrink-0">
          <ScrollArea className="h-full">
            <div className="py-1">
              {loading ? (
                <div className="px-3 py-4 text-[11px] text-[var(--text-secondary)]">
                  Loading...
                </div>
              ) : error ? (
                <div className="px-3 py-4 text-[11px] text-red-400">
                  {error}
                </div>
              ) : tree?.children?.length ? (
                tree.children.map((node) => (
                  <TreeItem
                    key={node.path}
                    node={node}
                    depth={0}
                    expanded={expandedDirs}
                    onToggle={toggleDir}
                    selectedFile={selectedFile}
                    onSelect={loadFile}
                  />
                ))
              ) : (
                <div className="px-3 py-4 text-[11px] text-[var(--text-secondary)]">
                  No knowledge files yet. Run records will appear after agent turns.
                </div>
              )}
            </div>
          </ScrollArea>
        </div>

        {/* File viewer / search results */}
        <div className="flex-1 min-w-0">
          <ScrollArea className="h-full">
            {searchResults !== null ? (
              <SearchResultsView
                results={searchResults}
                loading={searchLoading}
                onFileClick={(path) => { loadFile(path); }}
                onBack={() => setSearchResults(null)}
              />
            ) : selectedFile ? (
              <div className="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-1.5"
                    onClick={() => setSelectedFile(null)}
                  >
                    <ArrowLeft className="w-3 h-3" />
                  </Button>
                  <span className="text-[11px] font-mono text-[var(--text-secondary)] truncate">
                    {selectedFile}
                  </span>
                </div>
                {fileLoading ? (
                  <p className="text-[11px] text-[var(--text-secondary)]">Loading...</p>
                ) : (
                  <article className="prose prose-sm prose-invert max-w-none text-[var(--text-primary)] [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-[13px] [&_p]:text-[12px] [&_li]:text-[12px] [&_code]:text-[11px] [&_td]:text-[11px] [&_th]:text-[11px] [&_pre]:text-[11px]">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {fileContent}
                    </ReactMarkdown>
                  </article>
                )}
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center p-8">
                <BookOpen className="w-8 h-8 text-[var(--text-secondary)] opacity-30 mb-3" />
                <p className="text-[11px] text-[var(--text-secondary)]">
                  Select a file to view its contents
                </p>
              </div>
            )}
          </ScrollArea>
        </div>
      </div>
    </div>
  );
}

function TreeItem({
  node,
  depth,
  expanded,
  onToggle,
  selectedFile,
  onSelect,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  selectedFile: string | null;
  onSelect: (path: string) => void;
}) {
  const isExpanded = expanded.has(node.path);
  const isSelected = selectedFile === node.path;
  const pl = 8 + depth * 14;

  if (node.isDir) {
    if (node.name === ".gitkeep") return null;
    return (
      <>
        <button
          className="w-full flex items-center gap-1.5 py-1 hover:bg-[var(--bg-secondary)] transition-colors text-left"
          style={{ paddingLeft: pl }}
          onClick={() => onToggle(node.path)}
        >
          {isExpanded ? (
            <ChevronDown className="w-3 h-3 text-[var(--text-secondary)] flex-shrink-0" />
          ) : (
            <ChevronRight className="w-3 h-3 text-[var(--text-secondary)] flex-shrink-0" />
          )}
          {isExpanded ? (
            <FolderOpen className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
          ) : (
            <Folder className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
          )}
          <span className="text-[11px] text-[var(--text-primary)] truncate">
            {node.name}
          </span>
        </button>
        {isExpanded &&
          (node.children || [])
            .filter((c) => c.name !== ".gitkeep")
            .map((child) => (
              <TreeItem
                key={child.path}
                node={child}
                depth={depth + 1}
                expanded={expanded}
                onToggle={onToggle}
                selectedFile={selectedFile}
                onSelect={onSelect}
              />
            ))}
      </>
    );
  }

  return (
    <button
      className={`w-full flex items-center gap-1.5 py-1 hover:bg-[var(--bg-secondary)] transition-colors text-left ${
        isSelected ? "bg-[var(--bg-secondary)]" : ""
      }`}
      style={{ paddingLeft: pl + 14 }}
      onClick={() => onSelect(node.path)}
    >
      <FileText className="w-3.5 h-3.5 text-[var(--text-secondary)] flex-shrink-0" />
      <span className="text-[11px] text-[var(--text-primary)] truncate">
        {node.name}
      </span>
    </button>
  );
}

function SearchResultsView({
  results,
  loading,
  onFileClick,
  onBack,
}: {
  results: SearchResult[];
  loading: boolean;
  onFileClick: (path: string) => void;
  onBack: () => void;
}) {
  return (
    <div className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <Button size="sm" variant="ghost" className="h-6 px-1.5" onClick={onBack}>
          <ArrowLeft className="w-3 h-3" />
        </Button>
        <span className="text-[11px] text-[var(--text-secondary)]">
          {loading ? "Searching..." : `${results.length} result${results.length !== 1 ? "s" : ""}`}
        </span>
      </div>
      {results.length === 0 && !loading && (
        <p className="text-[11px] text-[var(--text-secondary)]">No results found.</p>
      )}
      <div className="space-y-2">
        {results.map((r, i) => (
          <button
            key={`${r.path}-${i}`}
            className="w-full text-left p-2 rounded-md border border-[var(--border-color)] hover:bg-[var(--bg-secondary)] transition-colors"
            onClick={() => onFileClick(r.path)}
          >
            <div className="flex items-center gap-1.5 mb-1">
              <FileText className="w-3 h-3 text-[var(--text-secondary)]" />
              <span className="text-[11px] font-mono text-[var(--text-primary)] truncate">
                {r.path}
              </span>
            </div>
            {r.snippet && (
              <p className="text-[10px] text-[var(--text-secondary)] line-clamp-2">
                {r.snippet}
              </p>
            )}
            {r.matches?.length > 0 && (
              <p className="text-[10px] text-[var(--text-secondary)] line-clamp-2">
                {r.matches[0].text}
              </p>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
