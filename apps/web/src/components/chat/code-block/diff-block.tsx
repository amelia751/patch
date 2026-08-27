"use client";

import { useState, useCallback } from "react";
import { FileIcon } from "@/components/ui/file-icon";
import { ChevronDown } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { cn } from "@/lib/utils";
import { useSyntaxTheme, MONO_FONT } from "./syntax-theme";

interface DiffBlockProps {
  code: string;
  onCopy?: (code: string) => void;
  className?: string;
}

/** Workspace-relative path and first edited line in the new file (Cursor-style jump). */
function parseDiffOpenTarget(raw: string): { path: string; scrollToLine: number } | null {
  const lines = raw.split("\n");
  let oldPath = "";
  let newPath = "";
  for (const line of lines) {
    if (line.startsWith("--- ")) {
      const m = line.match(/^---\s+(.+?)\s*$/);
      if (m) oldPath = m[1].trim();
    } else if (line.startsWith("+++ ")) {
      const m = line.match(/^\+\+\+\s+(.+?)\s*$/);
      if (m) newPath = m[1].trim();
    }
  }
  if (!newPath || newPath === "/dev/null") return null;

  const strip = (p: string) =>
    p
      .replace(/\\/g, "/")
      .replace(/^(a\/|b\/)/, "")
      .replace(/^\/home\/user\/project-workspace\/?/, "");

  const path = strip(newPath);
  if (!path) return null;

  const isNewFile =
    oldPath === "/dev/null" ||
    oldPath === "a/dev/null" ||
    oldPath.endsWith("/dev/null");

  if (isNewFile) {
    return { path, scrollToLine: 1 };
  }

  const hunk = lines.find((l) => l.startsWith("@@"));
  if (hunk) {
    // @@ -10,7 +22,8 @@  → first changed line in new file is 22
    const m = hunk.match(/@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@/);
    if (m) {
      const start = parseInt(m[1], 10);
      if (!Number.isNaN(start) && start > 0) return { path, scrollToLine: start };
    }
  }

  return { path, scrollToLine: 1 };
}

/** Default visible lines before expanding */
const DEFAULT_LINES = 12;

// Infer Prism language from filename extension
const EXT_LANG: Record<string, string> = {
  py: "python", ts: "typescript", tsx: "tsx", js: "javascript", jsx: "jsx",
  rb: "ruby", go: "go", rs: "rust", java: "java", kt: "kotlin", swift: "swift",
  php: "php", cs: "csharp", cpp: "cpp", c: "c", h: "c", hpp: "cpp",
  yaml: "yaml", yml: "yaml", json: "json", toml: "toml", xml: "xml",
  html: "html", css: "css", scss: "scss", sql: "sql", sh: "bash",
  md: "markdown", txt: "text", dockerfile: "docker", tf: "hcl",
  graphql: "graphql", proto: "protobuf", lua: "lua", r: "r",
};

function getLangFromFilename(filename: string): string {
  const lower = filename.toLowerCase();
  if (lower === "dockerfile") return "docker";
  if (lower === "makefile") return "makefile";
  const ext = lower.split(".").pop() || "";
  return EXT_LANG[ext] || "text";
}

export function DiffBlock({ code, className }: DiffBlockProps) {
  const [isHeaderHovered, setIsHeaderHovered] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const { prismTheme, isDark } = useSyntaxTheme();
  const lines = code.split("\n");

  // Extract filename and line counts from diff headers
  let filename = "";
  let addedLines = 0;
  let removedLines = 0;

  lines.forEach((line) => {
    if (line.startsWith("---")) {
      const match = line.match(/---\s+(.+)/);
      if (match) filename = match[1].replace("a/", "").replace("b/", "");
    } else if (line.startsWith("+++")) {
      const match = line.match(/\+\+\+\s+(.+)/);
      if (match) filename = match[1].replace("a/", "").replace("b/", "");
    } else if (line.startsWith("+") && !line.startsWith("+++")) {
      addedLines++;
    } else if (line.startsWith("-") && !line.startsWith("---")) {
      removedLines++;
    }
  });

  const displayFilename = filename.split("/").pop() || "diff";
  const lang = getLangFromFilename(displayFilename);

  const handleHeaderClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const target = parseDiffOpenTarget(code);
      if (!target) return;
      window.dispatchEvent(
        new CustomEvent("codebaseOpenFile", {
          detail: { path: target.path, scrollToLine: target.scrollToLine },
        })
      );
    },
    [code]
  );

  // Build stripped code and per-line metadata (skip diff headers like ---, +++, @@)
  const linesMeta: Array<{ type: "add" | "del" | "normal" }> = [];
  const strippedLines: string[] = [];

  for (const line of lines) {
    const isAdd = line.startsWith("+") && !line.startsWith("+++");
    const isDel = line.startsWith("-") && !line.startsWith("---");
    const isHeader = line.startsWith("@@") || line.startsWith("---") || line.startsWith("+++");

    if (isAdd || isDel) {
      strippedLines.push(line.substring(1));
      linesMeta.push({ type: isAdd ? "add" : "del" });
    } else if (!isHeader) {
      strippedLines.push(line);
      linesMeta.push({ type: "normal" });
    }
  }

  const capped = strippedLines.length > DEFAULT_LINES;
  const showAll = isExpanded || !capped;
  const visibleLines = showAll ? strippedLines : strippedLines.slice(0, DEFAULT_LINES);
  const visibleMeta = showAll ? linesMeta : linesMeta.slice(0, DEFAULT_LINES);
  const visibleCode = visibleLines.join("\n");
  const hiddenCount = strippedLines.length - DEFAULT_LINES;

  // Theme-aware diff colors (balanced green/red — GitHub style)
  const addBg = isDark ? "rgba(46, 160, 67, 0.18)" : "rgba(46, 160, 67, 0.22)";
  const delBg = isDark ? "rgba(248, 81, 73, 0.18)" : "rgba(248, 81, 73, 0.20)";

  return (
    <div className={cn("my-3 rounded-lg overflow-hidden border border-[var(--border-color)] max-w-full relative group not-prose", className)}>
      {/* Header — click filename / +N (Cursor: open file at edit location) */}
      <button
        type="button"
        className="w-full bg-[var(--bg-tertiary)] px-2 py-1.5 flex items-center gap-2 text-xs text-[var(--text-secondary)] border-b border-[var(--border-color)] cursor-pointer hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)] transition-colors text-left"
        onClick={handleHeaderClick}
        onMouseEnter={() => setIsHeaderHovered(true)}
        onMouseLeave={() => setIsHeaderHovered(false)}
      >
        <div className="w-3 h-3 flex items-center justify-center flex-shrink-0">
          {isHeaderHovered ? (
            <ChevronDown className="h-3 w-3 text-[var(--text-secondary)]" />
          ) : (
            <FileIcon filename={displayFilename} size={12} />
          )}
        </div>
        <span className="truncate text-left">{displayFilename}</span>
        {addedLines > 0 && (
          <span className="text-[10px] flex-shrink-0" style={{ color: isDark ? "#3fb950" : "#1a7f37" }}>+{addedLines}</span>
        )}
        {removedLines > 0 && (
          <span className="text-[10px] flex-shrink-0" style={{ color: isDark ? "#f85149" : "#cf222e" }}>-{removedLines}</span>
        )}
      </button>

      {/* Code lines — capped at MAX_LINES */}
      <SyntaxHighlighter
        language={lang}
        style={prismTheme}
        showLineNumbers
        lineNumberStyle={{ display: "none" }}
        wrapLines
        wrapLongLines
        lineProps={(lineNumber: number) => {
          const meta = visibleMeta[lineNumber - 1];
          const style: React.CSSProperties = {
            display: "block",
            paddingLeft: "12px",
            paddingRight: "12px",
            paddingTop: "1px",
            paddingBottom: "1px",
          };
          if (meta?.type === "add") {
            style.backgroundColor = addBg;
          } else if (meta?.type === "del") {
            style.backgroundColor = delBg;
          }
          return { style };
        }}
        customStyle={{
          margin: 0,
          padding: "4px 0",
          fontSize: "11px",
          lineHeight: "1.5",
          backgroundColor: "var(--bg-secondary)",
          borderRadius: 0,
          overflow: "auto",
          fontFamily: MONO_FONT,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
        codeTagProps={{
          style: {
            fontFamily: MONO_FONT,
            fontSize: "11px",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word" as const,
          },
        }}
      >
        {visibleCode}
      </SyntaxHighlighter>

      {capped && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full bg-[var(--bg-tertiary)] px-3 py-1 text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors border-t border-[var(--border-color)] text-center"
        >
          {isExpanded ? "Show less" : `Show ${hiddenCount} more lines`}
        </button>
      )}
    </div>
  );
}
