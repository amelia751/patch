"use client";

import { useEffect, useState } from "react";
import {
  BadgeCheck,
  Bot,
  ChevronRight,
  Eye,
  FileEdit as FileEditIcon,
  FileText,
  FolderSearch,
  Globe,
  Layers,
  Loader2,
  ScanSearch,
  Search,
  Shield,
  Terminal,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { uiTheme } from "@/lib/ui-theme";
import type { ActiveToolInfo } from "@/hooks/useThreadStream";
import { FormattedMessage } from "./formatted-message";
import type { WorklogEntry } from "./thread-types";

const TOOL_CHROME: Record<
  string,
  { icon: React.ComponentType<{ className?: string }>; color: string; label: string }
> = {
  Bash: { icon: Terminal, color: "text-amber-500", label: "Bash" },
  BashTool: { icon: Terminal, color: "text-amber-500", label: "Bash" },
  Read: { icon: Eye, color: "text-sky-400", label: "Read" },
  FileRead: { icon: Eye, color: "text-sky-400", label: "Read" },
  FileReadTool: { icon: Eye, color: "text-sky-400", label: "Read" },
  Write: { icon: FileText, color: "text-emerald-400", label: "Write" },
  FileWrite: { icon: FileText, color: "text-emerald-400", label: "Write" },
  FileWriteTool: { icon: FileText, color: "text-emerald-400", label: "Write" },
  Edit: { icon: FileEditIcon, color: "text-violet-400", label: "Edit" },
  FileEdit: { icon: FileEditIcon, color: "text-violet-400", label: "Edit" },
  FileEditTool: { icon: FileEditIcon, color: "text-violet-400", label: "Edit" },
  Grep: { icon: Search, color: uiTheme.toolSearch, label: "Search" },
  GrepTool: { icon: Search, color: uiTheme.toolSearch, label: "Search" },
  Glob: { icon: FolderSearch, color: uiTheme.toolSearch, label: "Find" },
  GlobTool: { icon: FolderSearch, color: uiTheme.toolSearch, label: "Find" },
  WebSearch: { icon: ScanSearch, color: "text-blue-400", label: "Web Search" },
  WebFetch: { icon: Globe, color: "text-blue-400", label: "Fetch" },
  Task: { icon: Bot, color: "text-purple-400", label: "Agent" },
  AgentTool: { icon: Bot, color: "text-purple-400", label: "Agent" },
  Normalize: { icon: Layers, color: "text-sky-400", label: "Normalize" },
  Evaluate: { icon: Shield, color: "text-amber-400", label: "Evaluate" },
  Verify: { icon: BadgeCheck, color: "text-emerald-400", label: "Verify" },
};

const DEFAULT_CHROME = { icon: Wrench, color: "text-[var(--text-secondary)]", label: "" };

function getToolChrome(toolType?: string) {
  if (!toolType) return null;
  return TOOL_CHROME[toolType] || DEFAULT_CHROME;
}

export function ActivitySpinner({ activeTool }: { activeTool: ActiveToolInfo }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - activeTool.startedAt) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [activeTool.startedAt]);

  const timeStr = elapsed > 0 ? `${elapsed}s` : "";

  return (
    <div className="flex items-center gap-2 mt-2 py-1">
      <Loader2 className="h-3 w-3 text-primary animate-spin flex-shrink-0" />
      <span className="text-[11px] text-[var(--text-secondary)]">
        {activeTool.verb}
        {activeTool.detail && (
          <span className="text-[var(--text-tertiary)] ml-1">
            {activeTool.detail.length > 50 ? activeTool.detail.slice(0, 47) + "..." : activeTool.detail}
          </span>
        )}
      </span>
      {timeStr && (
        <span className="text-[10px] text-[var(--text-tertiary)] tabular-nums">{timeStr}</span>
      )}
    </div>
  );
}

function CollapsedGroup({ entry }: { entry: WorklogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const chrome = getToolChrome(entry.toolType);
  const Icon = chrome?.icon || Eye;

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left hover:bg-[var(--bg-secondary)] rounded px-1 -mx-1 py-0.5 transition-colors group"
      >
        <Icon className={cn("h-3 w-3 flex-shrink-0", chrome?.color || "text-[var(--text-secondary)]")} />
        <span className="text-[13px] text-[var(--text-primary)]">{entry.text}</span>
        <ChevronRight
          className={cn(
            "h-3 w-3 text-[var(--text-tertiary)] flex-shrink-0 transition-transform",
            expanded && "rotate-90",
          )}
        />
      </button>
      {expanded && entry.items && (
        <div className="ml-5 mt-1 space-y-0.5">
          {entry.items.map((item, idx) => {
            const itemChrome = getToolChrome(item.tool);
            const label =
              itemChrome?.label === "Search"
                ? "Grepped"
                : itemChrome?.label === "Find"
                  ? "Found"
                  : itemChrome?.label || item.tool;
            const detail = item.detail
              .replace(/^(Read|Search|Find|Grep|Glob)\(`?/, "")
              .replace(/`?\)$/, "");
            return (
              <div key={idx} className="flex items-start gap-2 text-[12px] text-[var(--text-secondary)]">
                <span className="mt-[5px] text-[var(--text-tertiary)] text-[11px] leading-none select-none flex-shrink-0">
                  ⎿
                </span>
                <span
                  className={cn(
                    "flex-shrink-0 whitespace-nowrap",
                    itemChrome?.color || "text-[var(--text-secondary)]",
                  )}
                >
                  {label}
                </span>
                <span className="truncate text-[var(--text-tertiary)]">{detail}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function ThinkingBlock({ content, durationMs }: { content: string; durationMs?: number }) {
  const [expanded, setExpanded] = useState(false);
  const durationStr =
    durationMs && durationMs > 0
      ? durationMs >= 60000
        ? `${Math.round(durationMs / 60000)}m`
        : `${Math.round(durationMs / 1000)}s`
      : null;

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
      >
        <span>Thought{durationStr ? ` for ${durationStr}` : ""}</span>
        <ChevronRight
          className={cn("h-2.5 w-2.5 transition-transform", expanded && "rotate-90")}
        />
      </button>
      {expanded && (
        <div className="mt-1 pl-4 text-[11px] text-[var(--text-tertiary)] leading-relaxed opacity-60">
          <FormattedMessage content={content} />
        </div>
      )}
    </div>
  );
}

export function WorklogView({
  entries,
  idPrefix = "wl",
}: {
  entries: WorklogEntry[];
  idPrefix?: string;
}) {
  if (entries.length === 0) return null;

  return (
    <div className="space-y-2">
      {entries.map((entry, index) => {
        const key = `${idPrefix}-${index}`;
        if (entry.kind === "thinking") {
          return <ThinkingBlock key={key} content={entry.text} durationMs={entry.durationMs} />;
        }
        if (entry.kind === "collapsed_group") {
          return <CollapsedGroup key={key} entry={entry} />;
        }
        if (entry.kind === "action") {
          const chrome = getToolChrome(entry.toolType);
          const Icon = chrome?.icon;
          const isFileAction = !!entry.filePath;
          const handleFileClick = isFileAction
            ? () => {
                window.dispatchEvent(
                  new CustomEvent("codebaseOpenFile", {
                    detail: { path: entry.filePath, scrollToLine: 1 },
                  }),
                );
              }
            : undefined;
          return (
            <div
              key={key}
              className={cn(
                "flex items-start gap-2",
                isFileAction && "cursor-pointer hover:bg-[var(--bg-secondary)] rounded -mx-1 px-1 transition-colors",
              )}
              onClick={handleFileClick}
            >
              {Icon ? (
                <Icon className={cn("mt-[10px] h-3 w-3 flex-shrink-0", chrome.color)} />
              ) : (
                <span className="mt-[12px] h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
              )}
              <div className="min-w-0 flex-1 text-[13px] text-[var(--text-primary)] [&>div>div:first-child]:mt-1">
                <FormattedMessage content={entry.text} />
                {entry.result && (
                  <span className="ml-2 text-[12px] text-[var(--text-tertiary)]">{entry.result}</span>
                )}
              </div>
            </div>
          );
        }
        if (entry.kind === "result") {
          return (
            <div key={key} className="flex items-start gap-2 pl-4">
              <span className="mt-[7px] text-[var(--text-tertiary)] text-[12px] leading-none select-none flex-shrink-0">
                ⎿
              </span>
              <div className="min-w-0 flex-1 text-[13px] text-[var(--text-secondary)] [&>div>div:first-child]:mt-1">
                <FormattedMessage content={entry.text} />
              </div>
            </div>
          );
        }
        if (entry.kind === "response") {
          return (
            <div key={key}>
              <FormattedMessage content={entry.text} />
            </div>
          );
        }
        if (entry.kind === "block") {
          return (
            <div key={key} className="pl-4">
              <FormattedMessage content={entry.text} />
            </div>
          );
        }
        return (
          <div key={key} className="flex items-start gap-2">
            <span className="mt-[12px] h-1.5 w-1.5 rounded-full bg-[var(--text-primary)] flex-shrink-0" />
            <div className="min-w-0 flex-1 text-[13px] text-[var(--text-primary)] [&>div>div:first-child]:mt-1">
              <FormattedMessage content={entry.text} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
