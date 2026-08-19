"use client";

import { useEffect, useState, type ReactNode } from "react";
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
import { TerminalBlock } from "@/components/chat/code-block/terminal-block";
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

const CALL_RE =
  /^(Read|Write|Edit|Bash|Normalize|Evaluate|Verify|Search|Find|Grep|Glob|Web Search|Fetch)\(([\s\S]+)\)$/;

function parseCall(text: string): { name?: string; detail: string } {
  const trimmed = text.trim();
  const match = trimmed.match(CALL_RE);
  if (match) {
    let detail = match[2].trim();
    if (
      (detail.startsWith("`") && detail.endsWith("`")) ||
      (detail.startsWith('"') && detail.endsWith('"'))
    ) {
      detail = detail.slice(1, -1);
    }
    return { name: match[1], detail };
  }
  const readFile = trimmed.match(/^read_file\s+(.+)$/);
  if (readFile) return { name: "Read", detail: readFile[1] };
  if (trimmed === "apply_patch" || trimmed.startsWith("apply_patch ")) {
    return { name: "Bash", detail: trimmed };
  }
  if (/^(pnpm|npm|npx|yarn|uv|pytest|cargo|go)\b/.test(trimmed)) {
    return { name: "Bash", detail: trimmed };
  }
  const last = trimmed.split(/\s+/).pop() ?? "";
  if (trimmed.includes("/") && /\.\w{1,8}$/.test(last)) {
    return { name: "Read", detail: trimmed };
  }
  return { detail: trimmed };
}

function namedToolType(name?: string): string | undefined {
  if (!name) return undefined;
  if (name === "Search") return "Grep";
  if (name === "Find") return "Glob";
  if (name === "Web Search") return "WebSearch";
  if (name === "Fetch") return "WebFetch";
  return name;
}

export function inferToolType(entry: Pick<WorklogEntry, "toolType" | "text">): string | undefined {
  if (entry.toolType) return entry.toolType;
  return namedToolType(parseCall(entry.text).name);
}

function isShellTool(toolType?: string, text?: string): boolean {
  if (toolType === "Bash" || toolType === "BashTool") return true;
  if (!text) return false;
  const parsed = parseCall(text);
  return parsed.name === "Bash";
}

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
  const preview = content.split("\n")[0]?.trim() ?? "";

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 max-w-full text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
      >
        <span className="shrink-0">Thought{durationStr ? ` for ${durationStr}` : ""}</span>
        <ChevronRight
          className={cn("h-2.5 w-2.5 shrink-0 transition-transform", expanded && "rotate-90")}
        />
        {!expanded && preview && (
          <span className="min-w-0 truncate opacity-70">{preview}</span>
        )}
      </button>
      {expanded && (
        <div className="mt-1 pl-4 text-[11px] text-[var(--text-tertiary)] leading-relaxed opacity-60">
          <FormattedMessage content={content} />
        </div>
      )}
    </div>
  );
}

function ToolCallRow({ entry }: { entry: WorklogEntry }) {
  const toolType = inferToolType(entry);
  const chrome = getToolChrome(toolType);
  const Icon = chrome?.icon || Wrench;
  const parsed = parseCall(entry.text);
  const label = chrome?.label || parsed.name || "Tool";
  const detail = parsed.detail || entry.filePath || "";
  const isFileAction = Boolean(entry.filePath || parsed.name === "Read" || parsed.name === "Edit" || parsed.name === "Write");

  return (
    <div
      className={cn(
        "flex items-start gap-2 min-w-0",
        isFileAction && entry.filePath && "cursor-pointer hover:bg-[var(--bg-secondary)] rounded-md -mx-1 px-1 py-0.5 transition-colors",
      )}
      onClick={
        entry.filePath
          ? () =>
              window.dispatchEvent(
                new CustomEvent("codebaseOpenFile", {
                  detail: { path: entry.filePath, scrollToLine: 1 },
                }),
              )
          : undefined
      }
    >
      <Icon className={cn("mt-1 h-3.5 w-3.5 shrink-0", chrome?.color || "text-[var(--text-secondary)]")} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn("text-[13px] font-medium shrink-0", chrome?.color || "text-[var(--text-primary)]")}>
            {label}
          </span>
          {detail && (
            <code className="min-w-0 truncate px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[12px] font-mono text-[var(--text-primary)]">
              {detail}
            </code>
          )}
        </div>
        {entry.result && (
          <div className="mt-1 flex items-start gap-2 text-[12px] text-[var(--text-tertiary)]">
            <span className="mt-0.5 select-none leading-none">⎿</span>
            <span className="leading-relaxed">{entry.result}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function shellFence(entries: WorklogEntry[]): string {
  const lines: string[] = [];
  for (const entry of entries) {
    lines.push(`$ ${parseCall(entry.text).detail}`);
    if (entry.result) {
      for (const line of entry.result.replace(/\r\n/g, "\n").split("\n")) {
        lines.push(line);
      }
    }
  }
  return lines.join("\n");
}

export function WorklogView({
  entries,
  idPrefix = "wl",
}: {
  entries: WorklogEntry[];
  idPrefix?: string;
}) {
  if (entries.length === 0) return null;

  const nodes: ReactNode[] = [];
  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    const key = `${idPrefix}-${index}`;

    if (entry.kind === "thinking") {
      nodes.push(<ThinkingBlock key={key} content={entry.text} durationMs={entry.durationMs} />);
      continue;
    }
    if (entry.kind === "collapsed_group") {
      nodes.push(<CollapsedGroup key={key} entry={entry} />);
      continue;
    }
    if (entry.kind === "action" && isShellTool(inferToolType(entry), entry.text)) {
      const command = { ...entry };
      if (index + 1 < entries.length && entries[index + 1].kind === "result" && !command.result) {
        command.result = entries[index + 1].text;
        index += 1;
      }
      nodes.push(
        <TerminalBlock
          key={key}
          className="!my-0"
          code={shellFence([command])}
          onCopy={(code) => navigator.clipboard.writeText(code)}
        />,
      );
      continue;
    }
    if (entry.kind === "action") {
      nodes.push(<ToolCallRow key={key} entry={entry} />);
      continue;
    }
    if (entry.kind === "result") {
      nodes.push(
        <div key={key} className="flex items-start gap-2 pl-5">
          <span className="mt-[5px] text-[var(--text-tertiary)] text-[12px] leading-none select-none shrink-0">
            ⎿
          </span>
          <p className="min-w-0 flex-1 text-[12px] leading-relaxed text-[var(--text-secondary)]">
            {entry.text}
          </p>
        </div>,
      );
      continue;
    }
    if (entry.kind === "block") {
      const fence = entry.text.trim().match(/^```(?:terminal|bash|sh)\n([\s\S]*?)\n```$/);
      if (fence) {
        nodes.push(
          <TerminalBlock
            key={key}
            className="!my-0"
            code={fence[1]}
            onCopy={(code) => navigator.clipboard.writeText(code)}
          />,
        );
        continue;
      }
    }
    if (entry.kind === "response" || entry.kind === "block") {
      nodes.push(
        <div key={key}>
          <FormattedMessage content={entry.text} />
        </div>,
      );
      continue;
    }
    nodes.push(
      <p key={key} className="text-[13px] leading-relaxed text-[var(--text-secondary)]">
        {entry.text}
      </p>,
    );
  }

  return <div className="space-y-2.5">{nodes}</div>;
}
