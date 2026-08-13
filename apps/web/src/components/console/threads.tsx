"use client";

import Link from "next/link";
import React, { useState, useRef, useLayoutEffect, useEffect, useCallback, useMemo } from "react";
import {
  ChevronRight,
  ChevronDown,
  CheckCircle2,
  Loader2,
  Circle,
  AlertTriangle,
  MoreHorizontal,
  MoreVertical,
  Trash2,
  XCircle,
  Send,
  Paperclip,
  Omega,
  ArrowLeft,
  X,
  FileImage,
  Copy,
  Check,
  Terminal,
  FileText,
  FileEdit as FileEditIcon,
  Search,
  Globe,
  Key,
  Eye,
  Bot,
  Wrench,
  FolderSearch,
  ClipboardCopy,
  ScanSearch,
  GitBranch,
  Cloud,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { UserAvatar } from "@/components/interface/shared/user-avatar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { uiTheme } from "@/lib/ui-theme";
import { useAuth } from "@/lib/auth-context";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DiffBlock } from "@/components/chat/code-block/diff-block";
import { CodeBlock } from "@/components/chat/code-block/code-block";
import { ApprovalDialog } from "@/components/agent/approval-dialog";
import { FormattedMessage } from "./formatted-message";
import { useThreadStream } from "@/hooks/useThreadStream";
import { useProjectStream, type AgentEvent } from "@/hooks/useProjectStream";
import { useDemoOptional } from "@/lib/demo-context";
import { useTestGoogleSession } from "@/lib/test-google-session-context";
import { deriveThreadTitleFromMessage } from "@/lib/thread-title";
import {
  GoogleTestSessionContinueButton,
  THREAD_CALLOUT_ACTION_BUTTON_CLASS,
} from "@/components/interface/ops/configure-tab/google-test-session-continue-button";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import type {
  RawMessage,
  RawThread,
  StoredEvent,
  ToolCall,
  Activity,
  RuntimeTodo,
  Clarification,
  Thread,
  Message,
  WorklogEntry,
  ThreadsProps,
  ThreadEvent,
  ThreadTask,
  ThreadTodo,
  ActiveToolInfo,
  ThreadWaitingState,
} from "./thread-types";
import { wAction, wResult, wNarration, wBlock, pairActionResults, collapseWorklogEntries } from "./thread-worklog";
import { formatTaskEvents } from "./format-task-events";

// ============================================================================
// MOCK DATA IMPORTS
// ============================================================================

// import MOCK_THREADS_DATA from "./mock-data/mock_threads.json";
// import MOCK_DEPLOYMENT_DATA from "./mock-data/mock_deployment.json";
import MOCK_ACTIVITIES_DATA from "./mock-data/mock_activities.json";
import MOCK_CLARIFICATION_DATA from "./mock-data/mock_clarification.json";
import MOCK_MESSAGES_DATA from "./mock-data/mock_messages.json";
import MOCK_ANALYSIS_DATA from "./mock-data/mock_analysis.json";
// Real thread data removed — unauthenticated users see welcome thread only


// Types imported from ./thread-types

// ============================================================================
// MOCK DATA (imported from JSON files)
// ============================================================================

// const MOCK_THREADS: Thread[] = MOCK_THREADS_DATA as Thread[];
// const MOCK_DEPLOYMENT = MOCK_DEPLOYMENT_DATA as {
//   ticketId: string;
//   title: string;
//   status: "in_progress";
//   openedAt: string;
// };

const MOCK_ACTIVITIES: Activity[] = MOCK_ACTIVITIES_DATA as Activity[];
const MOCK_CLARIFICATION: Clarification = MOCK_CLARIFICATION_DATA as Clarification;

// Process MOCK_MESSAGES to replace placeholders with actual references
const MOCK_MESSAGES: Message[] = (MOCK_MESSAGES_DATA as unknown as RawMessage[]).map((msg: RawMessage) => ({
  id: msg.id,
  author: (msg.role === "user" ? "user" : "agent") as Message["author"],
  content: msg.content || "",
  timestamp: msg.created_at,
  tool_calls: msg.tool_calls,
  worklog: undefined,
  activities: msg.activities === "__MOCK_ACTIVITIES__" ? MOCK_ACTIVITIES : typeof msg.activities === "string" ? undefined : msg.activities,
  clarification: msg.clarification === "__MOCK_CLARIFICATION__" ? MOCK_CLARIFICATION : typeof msg.clarification === "string" ? undefined : msg.clarification,
}));

// Mock analysis data - shows the full streaming + completion flow for demo
// const MOCK_ANALYSIS_THREAD: Thread = MOCK_ANALYSIS_DATA.thread as Thread;
const MOCK_ANALYSIS_ACTIVITIES: Activity[] = MOCK_ANALYSIS_DATA.streamingActivities as Activity[];

// ============================================================================
const _rawAnalysisMsg = MOCK_ANALYSIS_DATA.finalMessage as unknown as RawMessage;
const MOCK_ANALYSIS_MESSAGE: Message = {
  id: _rawAnalysisMsg.id,
  author: (_rawAnalysisMsg.role === "user" ? "user" : "agent") as Message["author"],
  content: _rawAnalysisMsg.content || "",
  timestamp: _rawAnalysisMsg.created_at,
  activities: MOCK_ANALYSIS_ACTIVITIES,  // Replace placeholder with actual activities
};

// Real thread data removed — unauthenticated users see welcome thread only

// ============================================================================
// UI STATE CONSTANTS (not mock data, these are actual app states)
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const normalizeThreadStatus = (status: string | null | undefined): Thread["status"] => {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "closed" || normalized === "archived") return "closed";
  if (normalized === "in_progress") return "in_progress";
  return "open";
};

/** Coerce API content into a plain string. Handles Claude-style content-block arrays. */
function normalizeContent(raw: unknown): string {
  if (!raw) return "";
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw)) {
    return raw
      .map((block) => {
        if (typeof block === "string") return block;
        if (block && typeof block === "object") {
          const b = block as Record<string, unknown>;
          return (b.text ?? b.content ?? b.message ?? "") as string;
        }
        return "";
      })
      .join("\n");
  }
  if (typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    return ((obj.text ?? obj.content ?? obj.message ?? "") as string) || JSON.stringify(raw);
  }
  return String(raw);
}

const WELCOME_THREAD: Thread = {
  id: "0",
  threadNumber: 0,
  title: "Welcome",
  status: "open",
  createdAt: "Just now",
  updatedAt: "Just now",
  messageCount: 1,
  activityCount: 0,
  preview: "Welcome. PatchAPI finds API breakages, verifies a migration, and opens a PR for review.",
};

const MOCK_GOOGLE_TEST_SESSION_THREAD_ID = "mock-google-test-session";
/** Signed-out demo: agent asks for a secret — CTA opens Add New Secret (`AddSecretDialog`). */
const MOCK_SECRET_REQUIREMENT_THREAD_ID = "mockSecretRequirement";
/** Signed-out demo: agent asks for GCP — CTA opens Connect via Service Account (same modal as Configure → Connection). */
const MOCK_GCP_CONNECTION_THREAD_ID = "mockGcpConnection";

/** Local-only threads for signed-out users (not persisted; survives until refresh). */
const GUEST_THREAD_ID_PREFIX = "guest-";

/** Provisional title before the backend streams `thread_title` (ChatGPT-style). */
const PLACEHOLDER_CHAT_TITLE = "New chat";

function isGuestThreadId(id: string): boolean {
  return id.startsWith(GUEST_THREAD_ID_PREFIX);
}

function detectTaskType(message: string): string {
  const lower = message.toLowerCase();
  const testPatterns = /\b(test|exercise|verify|run .*(flow|workflow|end.to.end)|e2e|smoke test|integration test|check .*(endpoint|api|workflow))\b/;
  const debugPatterns = /\b(debug|fix|broken|fails?|crash|error|bug|not working|doesn.t work|investigate)\b/;
  const understandPatterns = /\b(explain|describe|what (is|does|happens)|how (does|do)|show me|list .*(endpoint|route|api)|architecture|understand)\b/;
  if (testPatterns.test(lower)) return "test";
  if (debugPatterns.test(lower)) return "debug";
  if (understandPatterns.test(lower)) return "understand";
  return "backend_chat";
}

/** Backend-persisted thread (UUID-style id), not demo/local rows. */
function isPersistedBackendThreadId(id: string): boolean {
  if (!id || id === "0" || id === "new" || id === "analyzing") return false;
  if (id.startsWith("provisional-") || isGuestThreadId(id)) return false;
  if (id === MOCK_GOOGLE_TEST_SESSION_THREAD_ID) return false;
  return id.includes("-");
}

const DEMO_THREADS: Thread[] = [
  {
    id: MOCK_GOOGLE_TEST_SESSION_THREAD_ID,
    threadNumber: 4,
    title: "Connect Google test session",
    status: "open",
    createdAt: "Just now",
    updatedAt: "Just now",
    messageCount: 1,
    activityCount: 0,
    preview: "Save a test Google session for authenticated runs",
  },
  {
    id: MOCK_SECRET_REQUIREMENT_THREAD_ID,
    threadNumber: 5,
    title: "Needs DATABASE_URL for migrations",
    status: "open",
    createdAt: "Just now",
    updatedAt: "Just now",
    messageCount: 2,
    activityCount: 0,
    preview: "Add DATABASE_URL under Configure → Secrets",
  },
  {
    id: MOCK_GCP_CONNECTION_THREAD_ID,
    threadNumber: 6,
    title: "Link GCP for Vertex deploy",
    status: "open",
    createdAt: "Just now",
    updatedAt: "Just now",
    messageCount: 2,
    activityCount: 0,
    preview: "Connect your GCP project to continue",
  },
  {
    id: "1",
    threadNumber: 1,
    title: "Test intake workflow end-to-end",
    status: "open",
    createdAt: "2 hours ago",
    updatedAt: "1 hour ago",
    messageCount: 4,
    activityCount: 3,
    preview: "Testing the intake workflow...",
    branch: "patchapi/fix-intake-ws",
  },
  {
    id: "2",
    threadNumber: 2,
    title: "Debug WebSocket live_update events",
    status: "in_progress",
    createdAt: "30 min ago",
    updatedAt: "Just now",
    messageCount: 2,
    activityCount: 1,
    preview: "Investigating missing live_update events...",
    branch: "patchapi/debug-ws-events",
  },
  {
    id: "3",
    threadNumber: 3,
    title: "What does the signup flow look like?",
    status: "open",
    createdAt: "Yesterday",
    updatedAt: "Yesterday",
    messageCount: 3,
    activityCount: 0,
    preview: "Understanding the signup flow...",
  },
];

// const ANALYZING_THREAD: Thread = {
//   id: "analyzing",
//   threadNumber: 1,  // Will be replaced with real thread number once created
//   title: "Analyzing Project",
//   status: "in_progress",
//   createdAt: "Just now",
//   updatedAt: "Just now",
//   messageCount: 1,
//   activityCount: 6,
//   preview: "Analyzing your code and designing the architecture...",
// };

const NO_PROJECT_MESSAGE: Message = {
  id: "msg-no-project",
  author: "agent",
  content: `Welcome. PatchAPI is Dependabot for APIs: when a provider deprecates a model or endpoint, it finds the affected code, verifies a migration in isolation, and opens an evidence-backed pull request for normal human review. It stops there — it never merges or deploys.

To get started, import a GitHub repository so I can:

- Inventory the APIs this codebase actually calls
- Show those files in the Codebase tab
- Trace a provider change to the call sites it would break
- Prepare a verified pull request without touching production

Use the project menu to import a project.`,
  timestamp: "Just now",
};

const ANALYZING_MESSAGE: Message = {
  id: "msg-analyzing",
  author: "agent",
  content: `I'm indexing this repository for API usage so a provider change can be traced to real call sites.

This includes:
- Scanning source for SDK and HTTP API usage
- Recording model IDs, endpoints, and versions
- Preparing the inventory the Change and Impact agents will use

This usually takes a few seconds depending on repository size.`,
  timestamp: "Just now",
  // Activities will be populated from streaming
  activities: [],
};

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

// function StatusBadge({ status }: { status: string }) {
//   const config: Record<string, { label: string; class: string }> = {
//     in_progress: { label: "In Progress", class: "bg-amber-500/10 text-amber-500 dark:text-amber-400 border-amber-500/30" },
//     completed: { label: "Completed", class: "bg-[#10b981]/10 text-[#10b981] border-[#10b981]/30" },
//     failed: { label: "Failed", class: "bg-red-500/20 text-red-400 border-red-500/30" },
//   };
//   const { label, class: cls } = config[status] || config.in_progress;
//   return (
//     <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-medium border", cls)}>
//       {label}
//     </span>
//   );
// }

function ActivityRow({ activity, isExpanded, onToggle }: {
  activity: Activity;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const hasDetails = activity.logs || activity.summary || activity.content;
  const isInProgress = activity.status === "in_progress";
  
  // For in_progress tasks, always show content (streaming mode)
  // For completed tasks, content is hidden behind expand toggle
  const showContent = isInProgress || isExpanded;

  const statusIcon = {
    completed: <CheckCircle2 className="h-3.5 w-3.5 text-[#10b981] flex-shrink-0" />,
    in_progress: <Loader2 className="h-3.5 w-3.5 text-primary animate-spin flex-shrink-0" />,
    pending: <Circle className="h-3.5 w-3.5 text-[var(--text-secondary)] flex-shrink-0" />,
    failed: <XCircle className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />,
    needs_input: <AlertTriangle className="h-3.5 w-3.5 text-amber-500 flex-shrink-0 animate-pulse" />,
    cancelled: <X className="h-3.5 w-3.5 text-[var(--text-secondary)] flex-shrink-0" />,
  };

  return (
    <div className={cn(
      isInProgress && "bg-[var(--bg-secondary)] -mx-2 px-2 py-1 rounded-md"
    )}>
      <button
        onClick={hasDetails && !isInProgress ? onToggle : undefined}
        className={cn(
          "w-full flex items-center gap-2 py-1 text-left",
          hasDetails && !isInProgress && "hover:bg-[var(--bg-secondary)] -mx-1 px-1 rounded cursor-pointer",
          (!hasDetails || isInProgress) && "cursor-default"
        )}
      >
        {/* Expand toggle - only for completed tasks with details */}
        {hasDetails && !isInProgress && (
          isExpanded 
            ? <ChevronDown className="h-3 w-3 text-[var(--text-secondary)]" />
            : <ChevronRight className="h-3 w-3 text-[var(--text-secondary)]" />
        )}
        {(!hasDetails || isInProgress) && <div className="w-3" />}
        
        {statusIcon[activity.status]}

        <span className={cn(
          "flex-1 text-[12px]",
          activity.status === "pending" && "text-[var(--text-secondary)]",
          activity.status === "needs_input" && "text-amber-500",
          activity.status === "in_progress" && "text-[var(--text-primary)] font-medium",
          activity.status === "cancelled" && "text-[var(--text-secondary)] line-through",
          activity.status !== "pending" && activity.status !== "needs_input" && activity.status !== "in_progress" && activity.status !== "cancelled" && "text-[var(--text-tertiary)]"
        )}>
          {activity.title}
        </span>
        
        {activity.duration && (
          <span className="text-[10px] text-[var(--text-secondary)]">
            {activity.duration}
          </span>
        )}
      </button>
      
      {/* Content - always visible for in_progress, toggle for completed */}
      {showContent && hasDetails && (
        <div className="mt-2 mb-2 ml-[5px] pl-2 border-l border-[var(--border-color)]">
          {activity.content ? (
            <div className="text-[12px] leading-relaxed prose max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ ...props }) => (
                    <div className="my-1 text-[12px] text-[var(--text-secondary)]" {...props} />
                  ),
                  ul: ({ ...props }) => (
                    <ul className="list-disc pl-4 my-1.5 space-y-0.5 text-[var(--text-secondary)]" {...props} />
                  ),
                  li: ({ ...props }) => (
                    <li className="text-[11px]" {...props} />
                  ),
                  strong: ({ ...props }) => (
                    <strong className="font-semibold text-[var(--text-primary)]" {...props} />
                  ),
                  code: ({ inline, className, children, ...props }: { inline?: boolean; className?: string; children?: React.ReactNode }) => {
                    const match = /language-(\w+)/.exec(className || '');
                    const language = match ? match[1] : 'code';
                    const code = String(children).replace(/\n$/, '');

                    if (inline) {
                      return (
                        <code className="px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-primary)] text-[10px] font-mono" {...props}>
                          {children}
                        </code>
                      );
                    }

                    const isDiff = language === 'diff' || code.includes('\n+') || code.includes('\n-') || code.startsWith('---') || code.startsWith('+++');

                    if (isDiff) {
                      return <DiffBlock code={code} onCopy={() => navigator.clipboard.writeText(code)} />;
                    }

                    return <CodeBlock code={code} language={language} onCopy={() => navigator.clipboard.writeText(code)} />;
                  },
                }}
              >
                {activity.content}
              </ReactMarkdown>
            </div>
          ) : (
            <>
              {activity.summary && (
                <p className="text-[11px] text-[var(--text-secondary)] mb-1">
                  {activity.summary}
                </p>
              )}
              {activity.logs && (
                <div className="bg-[var(--bg-tertiary)] rounded p-2 space-y-0.5">
                  {activity.logs.map((log, idx) => (
                    <div key={idx} className="text-[10px] font-mono text-[var(--text-secondary)]">
                      {log}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ClarificationBlock({ clarification, onSelect }: {
  clarification: Clarification;
  onSelect: (option: string) => void;
}) {
  const [customInput, setCustomInput] = useState("");

  const handleCustomSubmit = () => {
    if (customInput.trim()) {
      onSelect(customInput.trim());
      setCustomInput("");
    }
  };

  const handleCustomKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleCustomSubmit();
    }
  };

  return (
    <div className="mt-3 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="text-[12px] text-[var(--text-tertiary)] font-medium">
            {clarification.question}
          </p>
          {clarification.context && (
            <p className="text-[11px] text-[var(--text-secondary)] mt-1">
              {clarification.context}
            </p>
          )}
          <div className="flex flex-col gap-1.5 mt-3">
            {clarification.options.map((option, idx) => (
              <button
                key={idx}
                onClick={() => onSelect(option)}
                className="px-3 py-1.5 rounded-md bg-[var(--bg-tertiary)] hover:bg-[var(--bg-secondary)] text-left text-[var(--text-primary)] transition-colors border border-[var(--border-color)] text-[12px]"
              >
                {option}
              </button>
            ))}
            <input
              type="text"
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              onKeyDown={handleCustomKeyPress}
              placeholder="Other - Type what you want us to do differently"
              className="w-full px-3 py-1.5 rounded-md bg-[var(--bg-tertiary)] hover:bg-[var(--bg-secondary)] text-left text-[var(--text-primary)] transition-colors border border-[var(--border-color)] text-[12px] placeholder:text-[var(--text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--border-color)]"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// formatTaskEvents imported from ./format-task-events

// WorklogEntry type and helpers imported from ./thread-worklog

// ---------------------------------------------------------------------------
// Tool chrome: icon + color per tool type
// ---------------------------------------------------------------------------
const TOOL_CHROME: Record<string, { icon: React.ComponentType<{ className?: string }>; color: string; label: string }> = {
  Bash:       { icon: Terminal,       color: "text-amber-500",  label: "Bash" },
  BashTool:   { icon: Terminal,       color: "text-amber-500",  label: "Bash" },
  Read:       { icon: Eye,            color: "text-sky-400",    label: "Read" },
  FileRead:   { icon: Eye,            color: "text-sky-400",    label: "Read" },
  FileReadTool: { icon: Eye,          color: "text-sky-400",    label: "Read" },
  Write:      { icon: FileText,       color: "text-emerald-400", label: "Write" },
  FileWrite:  { icon: FileText,       color: "text-emerald-400", label: "Write" },
  FileWriteTool: { icon: FileText,    color: "text-emerald-400", label: "Write" },
  Edit:       { icon: FileEditIcon,   color: "text-violet-400", label: "Edit" },
  FileEdit:   { icon: FileEditIcon,   color: "text-violet-400", label: "Edit" },
  FileEditTool: { icon: FileEditIcon, color: "text-violet-400", label: "Edit" },
  Grep:       { icon: Search,         color: uiTheme.toolSearch, label: "Search" },
  GrepTool:   { icon: Search,         color: uiTheme.toolSearch, label: "Search" },
  Glob:       { icon: FolderSearch,   color: uiTheme.toolSearch, label: "Find" },
  GlobTool:   { icon: FolderSearch,   color: uiTheme.toolSearch, label: "Find" },
  WebSearch:  { icon: ScanSearch,     color: "text-blue-400",   label: "Web Search" },
  WebFetch:   { icon: Globe,          color: "text-blue-400",   label: "Fetch" },
  Task:       { icon: Bot,            color: "text-purple-400", label: "Agent" },
  AgentTool:  { icon: Bot,            color: "text-purple-400", label: "Agent" },
};
const DEFAULT_CHROME = { icon: Wrench, color: "text-[var(--text-secondary)]", label: "" };

function getToolChrome(toolType?: string) {
  if (!toolType) return null;
  return TOOL_CHROME[toolType] || DEFAULT_CHROME;
}

// Collapsed read/search grouping moved to ./thread-worklog

// Worklog collapse functions imported from ./thread-worklog

// ---------------------------------------------------------------------------
// Activity spinner component
// ---------------------------------------------------------------------------
function ActivitySpinner({ activeTool }: { activeTool: ActiveToolInfo }) {
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

// ---------------------------------------------------------------------------
// Collapsed group component (expandable)
// ---------------------------------------------------------------------------
function CollapsedGroup({ entry }: { entry: WorklogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const chrome = getToolChrome(entry.toolType);
  const Icon = chrome?.icon || Eye;

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left hover:bg-[var(--bg-secondary)] rounded px-1 -mx-1 py-0.5 transition-colors group"
      >
        <Icon className={cn("h-3 w-3 flex-shrink-0", chrome?.color || "text-[var(--text-secondary)]")} />
        <span className="text-[13px] text-[var(--text-primary)]">{entry.text}</span>
        <ChevronRight className={cn(
          "h-3 w-3 text-[var(--text-tertiary)] flex-shrink-0 transition-transform",
          expanded && "rotate-90"
        )} />
      </button>
      {expanded && entry.items && (
        <div className="ml-5 mt-1 space-y-0.5">
          {entry.items.map((item, idx) => {
            const itemChrome = getToolChrome(item.tool);
            const label = itemChrome?.label === "Search" ? "Grepped" : itemChrome?.label === "Find" ? "Found" : itemChrome?.label || item.tool;
            const detail = item.detail
              .replace(/^(Read|Search|Find|Grep|Glob)\(`?/, "")
              .replace(/`?\)$/, "");
            return (
              <div key={idx} className="flex items-start gap-2 text-[12px] text-[var(--text-secondary)]">
                <span className="mt-[5px] text-[var(--text-tertiary)] text-[11px] leading-none select-none flex-shrink-0">⎿</span>
                <span className={cn("flex-shrink-0 whitespace-nowrap", itemChrome?.color || "text-[var(--text-secondary)]")}>
                  {label}
                </span>
                <span className="truncate text-[var(--text-tertiary)]">
                  {detail}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Thinking block (expandable, Cursor-style "Thought for Xs")
// ---------------------------------------------------------------------------
function ThinkingBlock({ content, durationMs }: { content: string; durationMs?: number }) {
  const [expanded, setExpanded] = useState(false);
  const durationStr = durationMs && durationMs > 0
    ? durationMs >= 60000
      ? `${Math.round(durationMs / 60000)}m`
      : `${Math.round(durationMs / 1000)}s`
    : null;

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
      >
        <span>Thought{durationStr ? ` for ${durationStr}` : ""}</span>
        <ChevronRight className={cn(
          "h-2.5 w-2.5 transition-transform",
          expanded && "rotate-90"
        )} />
      </button>
      {expanded && (
        <div className="mt-1 pl-4 text-[11px] text-[var(--text-tertiary)] leading-relaxed opacity-60">
          <FormattedMessage content={content} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Message copy dropdown
// ---------------------------------------------------------------------------
function MessageCopyMenu({ message, onClose }: { message: Message; onClose: () => void }) {
  const [copied, setCopied] = useState<string | null>(null);

  const copyText = useCallback(async (text: string, label: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => {
      setCopied(null);
      onClose();
    }, 800);
  }, [onClose]);

  const items: { label: string; value: string; icon: React.ComponentType<{ className?: string }> }[] = [];
  if (message.content) {
    items.push({ label: "Copy message", value: message.content, icon: Copy });
  }

  // Extract file paths and commands from worklog
  const worklog = message.worklog || [];
  const paths = new Set<string>();
  const commands = new Set<string>();
  for (const entry of worklog) {
    const pathMatch = entry.text.match(/`([^`]+\.\w+)`/);
    if (pathMatch) paths.add(pathMatch[1]);
    const cmdMatch = entry.text.match(/Bash\(`([^`]+)`\)/);
    if (cmdMatch) commands.add(cmdMatch[1]);
  }
  if (paths.size > 0) {
    items.push({ label: "Copy path", value: [...paths][0], icon: ClipboardCopy });
  }
  if (commands.size > 0) {
    items.push({ label: "Copy command", value: [...commands][0], icon: Terminal });
  }

  if (items.length === 0) return null;

  return (
    <div className="absolute right-0 top-6 z-20 bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-lg shadow-lg py-1 min-w-[160px]">
      {items.map((item) => {
        const ItemIcon = item.icon;
        return (
          <button
            key={item.label}
            onClick={() => copyText(item.value, item.label)}
            className="flex items-center gap-2 w-full px-3 py-1.5 text-[12px] text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors"
          >
            {copied === item.label ? (
              <Check className="h-3 w-3 text-emerald-400" />
            ) : (
              <ItemIcon className="h-3 w-3 text-[var(--text-secondary)]" />
            )}
            <span>{copied === item.label ? "Copied!" : item.label}</span>
          </button>
        );
      })}
    </div>
  );
}

const MOCK_SECRET_REQUIREMENT_MESSAGES: Message[] = [
  {
    id: "msg-secret-req-user",
    author: "user",
    content: "Run the migration and deploy the API to staging.",
    timestamp: "Just now",
  },
  {
    id: "msg-secret-req-agent",
    author: "agent",
    content:
      "I need `DATABASE_URL` to run migrations against the staging database. Add it under Configure → Secrets so I can connect safely.",
    timestamp: "Just now",
    clientAttachment: "configure_secrets",
  },
];

const MOCK_GCP_CONNECTION_MESSAGES: Message[] = [
  {
    id: "msg-gcp-req-user",
    author: "user",
    content: "Prepare the Vertex AI pipeline deployment for AI Content Studio.",
    timestamp: "Just now",
  },
  {
    id: "msg-gcp-req-agent",
    author: "agent",
    content:
      "I need a GCP project linked before I can provision Vertex AI resources. Connect a service account under Configure → Connection.",
    timestamp: "Just now",
    clientAttachment: "configure_gcp_connection",
  },
];

function ConfigureSecretsFromThreadCta() {
  const open = () => {
    window.dispatchEvent(
      new CustomEvent("switchMainTab", {
        detail: {
          tab: "configure",
          configureSection: "secrets",
          openCredentialModal: "secret",
        },
      }),
    );
  };
  return (
    <div className="mt-3 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
      <div className="flex items-start gap-2">
        <Key className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-[12px] text-[var(--text-tertiary)] font-medium">Secret required</p>
          <p className="text-[11px] text-[var(--text-secondary)] mt-1 leading-relaxed">
            Paste a <code className="text-[10px]">KEY=value</code> pair, bulk-add multiple variables, or upload a{" "}
            <code className="text-[10px]">.env</code> file — scoped to a workspace (
            <span className="font-medium text-[var(--text-primary)]">/</span>,{" "}
            <span className="font-medium text-[var(--text-primary)]">api/</span>, etc.).
          </p>
          <div className="flex flex-col gap-1.5 mt-3">
            <button
              type="button"
              onClick={open}
              className={cn(
                "inline-flex w-full items-center justify-center rounded-md font-medium",
                THREAD_CALLOUT_ACTION_BUTTON_CLASS,
                "h-9 text-xs",
              )}
            >
              <Key className="h-4 w-4 mr-2 shrink-0 opacity-80" aria-hidden />
              Add New Secret
            </button>
          </div>
          <p className="text-[10px] text-[var(--text-secondary)] mt-2">
            Or deep-link{" "}
            <Link
              href="/?configureSection=secrets&openCredentialModal=secret"
              className="font-medium text-[var(--text-primary)] hover:underline underline-offset-2"
            >
              Add New Secret
            </Link>
            .
          </p>
        </div>
      </div>
    </div>
  );
}

function ConfigureGcpConnectionFromThreadCta() {
  const open = () => {
    window.dispatchEvent(
      new CustomEvent("demoProjectChanged", {
        detail: { slug: "ai-content-studio" },
      }),
    );
    window.dispatchEvent(
      new CustomEvent("switchMainTab", {
        detail: {
          tab: "configure",
          configureSection: "connection",
          openCredentialModal: "gcp",
        },
      }),
    );
  };
  return (
    <div className="mt-3 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
      <div className="flex items-start gap-2">
        <Cloud className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-[12px] text-[var(--text-tertiary)] font-medium">GCP connection required</p>
          <p className="text-[11px] text-[var(--text-secondary)] mt-1 leading-relaxed">
            Upload or drag-and-drop a service account JSON key, choose a region and environment, then validate the connection.
          </p>
          <div className="flex flex-col gap-1.5 mt-3">
            <button
              type="button"
              onClick={open}
              className={cn(
                "inline-flex w-full items-center justify-center rounded-md font-medium",
                THREAD_CALLOUT_ACTION_BUTTON_CLASS,
                "h-9 text-xs",
              )}
            >
              <Cloud className="h-4 w-4 mr-2 shrink-0 opacity-80" aria-hidden />
              Connect via Service Account
            </button>
          </div>
          <p className="text-[10px] text-[var(--text-secondary)] mt-2">
            Or deep-link{" "}
            <Link
              href="/?configureSection=connection&openCredentialModal=gcp"
              className="font-medium text-[var(--text-primary)] hover:underline underline-offset-2"
            >
              Connect via Service Account
            </Link>
            .
          </p>
        </div>
      </div>
    </div>
  );
}

function GoogleTestSessionChatCta() {
  const { google, startGoogleTestSignIn, openTestSignInLearnMore } = useTestGoogleSession();

  if (google.status === "connected") {
    return (
      <div className="mt-3 p-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)]">
        <div className="flex items-start gap-2">
          <CheckCircle2 className="h-4 w-4 text-[#10b981] flex-shrink-0 mt-0.5" aria-hidden />
          <div className="flex-1 min-w-0">
            <p className="text-[12px] text-[var(--text-primary)] font-medium">
              Google session connected
            </p>
            {(google.sessionDisplayName || google.connectedAs) && (
              <p className="text-[11px] text-[var(--text-secondary)] mt-1 truncate">
                {[google.sessionDisplayName, google.connectedAs]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )}
            {google.capturedAt && (
              <p className="text-[10px] text-[var(--text-secondary)] mt-1">
                Captured {google.capturedAt}
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (google.status === "connecting") {
    return (
      <div className="mt-3 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
        <div className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 text-amber-400 animate-spin flex-shrink-0" />
          <p className="text-[12px] text-[var(--text-secondary)] font-medium">
            Signing in&hellip;
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
      <div className="flex items-start gap-2">
        <Key className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="text-[12px] text-[var(--text-tertiary)] font-medium">
            Test sign-in required
          </p>
          <p className="text-[11px] text-[var(--text-secondary)] mt-1 leading-relaxed">
            For features behind login, tests need a real session—same as
            opening your app in a browser while signed in.
          </p>

          <button
            type="button"
            onClick={() => openTestSignInLearnMore()}
            className="text-[11px] font-medium text-amber-600 dark:text-amber-400/90 hover:underline underline-offset-2 mt-1.5"
          >
            Learn more
          </button>

          <div className="flex flex-col gap-1.5 mt-3">
            <GoogleTestSessionContinueButton
              onClick={startGoogleTestSignIn}
              className="h-9 text-xs"
              iconSize={16}
            />
          </div>

          <p className="text-[10px] text-[var(--text-secondary)] mt-2">
            Or connect from{" "}
            <Link
              href="/?configureSection=auth"
              className="font-medium text-[var(--text-primary)] hover:underline underline-offset-2"
            >
              Configure → Auth
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

class ThreadErrorBoundary extends React.Component<
  { children: React.ReactNode; onRetry?: () => void },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ThreadErrorBoundary]", error, info.componentStack);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full gap-3 p-6 text-center">
          <p className="text-sm text-[var(--text-secondary)]">Something went wrong rendering this thread.</p>
          <button
            onClick={() => {
              this.setState({ hasError: false });
              this.props.onRetry?.();
            }}
            className="px-3 py-1.5 text-xs bg-neutral-800 dark:bg-neutral-200 text-white dark:text-black rounded-md hover:opacity-90"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function MessageBlock({
  message,
  onSelectClarification,
  userAvatar,
  userName,
  streamActivities,
  streamTodos,
  streamWorklog,
  streamContent,
  isStreaming,
  isAnalyzingMessage,
  currentThought,
  activeTool,
  waitingState,
}: {
  message: Message;
  onSelectClarification: (option: string) => void;
  userAvatar?: string | null;
  userName?: string;
  streamActivities?: ThreadTask[];
  streamTodos?: ThreadTodo[];
  streamWorklog?: WorklogEntry[];
  streamContent?: string;
  isStreaming?: boolean;
  isAnalyzingMessage?: boolean;
  currentThought?: string | null;
  activeTool?: ActiveToolInfo | null;
  waitingState?: ThreadWaitingState | null;
}) {
  const isAgent = message.author === "agent";
  const [showCopyMenu, setShowCopyMenu] = useState(false);

  // Runtime todos are separate from execution activities.
  const staticTodos = (message.todos || []).map(todo => ({
    id: todo.id,
    status: todo.status === "cancelled" ? "cancelled" as const : todo.status,
    title: todo.content,
  }));

  const streamingTodoItems: Activity[] = (streamTodos || []).map(todo => ({
    id: todo.id,
    status: todo.status === "cancelled" ? "cancelled" as const : todo.status,
    title: todo.content,
  }));

  const taskItems = isStreaming && streamingTodoItems.length > 0
    ? streamingTodoItems
    : staticTodos;

  // Activities remain the execution/activity log.
  const staticActivities = message.activities || [];
  
  // Convert streaming execution activities to Activity format
  const streamingActivities: Activity[] = (streamActivities || []).map(task => ({
    id: task.id,
    status: task.status === "waiting" ? "needs_input" : task.status,
    title: task.title,
    duration: task.duration,
    content: task.events.length > 0 ? formatTaskEvents(task.events) : undefined,
  }));

  // Use streaming activities if we have them and are streaming, otherwise use static
  const activities = isStreaming && streamingActivities.length > 0 
    ? streamingActivities 
    : staticActivities;
  
  // During analysis, show intro content ABOVE tasks
  // After completion, show tasks first, then summary content BELOW
  const showContentAboveTasks = isAnalyzingMessage;

  const rawWorklog: WorklogEntry[] = isStreaming && (streamWorklog || []).length > 0
    ? (streamWorklog || [])
    : (message.worklog && message.worklog.length > 0
      ? message.worklog
      : activities
          .filter((activity) => {
            const t = (activity.title || "").trim();
            return t !== "Working" && t !== "Responding";
          })
          .map((activity): WorklogEntry | null => {
            const text = activity.content || (activity.title ? `**${activity.title}**` : "");
            return text ? wNarration(text) : null;
          })
          .filter((e): e is WorklogEntry => !!e));

  // Insert persisted thinking entries from message
  const withThinking: WorklogEntry[] = message.thinking
    ? [{ kind: "thinking" as const, text: message.thinking }, ...rawWorklog]
    : rawWorklog;

  // Pair action entries with their corresponding result entries, then collapse groups
  const worklogEntries = collapseWorklogEntries(pairActionResults(withThinking));

  const getTodoIcon = (status: Activity["status"]) => {
    const dot = (className: string) => (
      <span className={cn("mt-1.5 h-1.5 w-1.5 rounded-full flex-shrink-0", className)} />
    );
    if (status === "completed") {
      return dot("bg-[var(--text-secondary)]");
    }
    if (status === "in_progress" || status === "needs_input") {
      return <Loader2 className="h-3.5 w-3.5 text-[var(--text-primary)] flex-shrink-0 mt-0.5 animate-spin" />;
    }
    if (status === "failed") {
      return <XCircle className="h-3.5 w-3.5 text-red-400 flex-shrink-0 mt-0.5" />;
    }
    if (status === "cancelled") {
      return dot("bg-[var(--text-tertiary)]/50");
    }
    return dot("bg-[var(--text-tertiary)]");
  };

  return (
    <div className="flex flex-col @lg:flex-row @lg:gap-3">
      {/* Small screen: Avatar + Header inline */}
      <div className="flex items-center gap-2 mb-2 @lg:hidden">
        {/* Avatar */}
        <div className={cn(
          "w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-medium flex-shrink-0 overflow-hidden",
          isAgent ? "bg-primary text-primary-foreground" : "bg-[#c026a6] text-white"
        )}>
          {isAgent ? (
            <Omega className="h-2.5 w-2.5" />
          ) : (
            <UserAvatar src={userAvatar} name={userName || "You"} fallback="Y" />
          )}
        </div>

        <span className="text-[12px] font-medium text-[var(--text-tertiary)]">
          {isAgent ? "Agent" : (userName || "You")}
        </span>
        <span className="text-[10px] text-[var(--text-secondary)]">
          {message.timestamp}
        </span>
        <div className="relative ml-auto">
          <button
            onClick={() => setShowCopyMenu(!showCopyMenu)}
            className="p-1 hover:bg-[var(--bg-secondary)] rounded"
          >
            <MoreHorizontal className="h-3 w-3 text-[var(--text-secondary)]" />
          </button>
          {showCopyMenu && (
            <MessageCopyMenu message={message} onClose={() => setShowCopyMenu(false)} />
          )}
        </div>
      </div>

      {/* Large screen: Avatar column */}
      <div className={cn(
        "hidden @lg:flex w-7 h-7 rounded-full items-center justify-center text-[11px] font-medium flex-shrink-0 overflow-hidden",
        isAgent ? "bg-primary text-primary-foreground" : "bg-[#c026a6] text-white"
      )}>
        {isAgent ? (
          <Omega className="h-3.5 w-3.5" />
        ) : (
          <UserAvatar src={userAvatar} name={userName || "You"} fallback="Y" />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Header - large screen only */}
        <div className="hidden @lg:flex items-center gap-2 mb-2">
          <span className="text-[12px] font-medium text-[var(--text-tertiary)]">
            {isAgent ? "Agent" : (userName || "You")}
          </span>
          <span className="text-[10px] text-[var(--text-secondary)]">
            {message.timestamp}
          </span>
          <div className="relative ml-auto">
            <button
              onClick={() => setShowCopyMenu(!showCopyMenu)}
              className="p-1 hover:bg-[var(--bg-secondary)] rounded"
            >
              <MoreHorizontal className="h-3 w-3 text-[var(--text-secondary)]" />
            </button>
            {showCopyMenu && (
              <MessageCopyMenu message={message} onClose={() => setShowCopyMenu(false)} />
            )}
          </div>
        </div>

        {/* During analysis: show intro message ABOVE tasks */}
        {showContentAboveTasks && message.content && (
          <FormattedMessage content={message.content} />
        )}

        {taskItems.length > 0 && (
          <div className="mt-3 space-y-1.5">
            <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              To do
            </div>
            {taskItems.map((item) => (
              <div key={item.id} className="flex items-start gap-2 text-[13px]">
                {getTodoIcon(item.status)}
                <span className={cn(
                  "text-[var(--text-tertiary)]",
                  item.status === "completed" && "line-through text-[var(--text-secondary)]",
                  item.status === "cancelled" && "line-through text-[var(--text-secondary)]",
                  item.status === "in_progress" && "text-[var(--text-primary)]",
                  item.status === "failed" && "text-red-400"
                )}>
                  {item.title}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Waiting/thinking — show live thinking shimmer; once thinking ends it collapses into ThinkingBlock */}
        {isStreaming &&
          !message.content?.trim() &&
          (currentThought || waitingState?.message || (!activeTool && worklogEntries.length === 0)) && (
          <div className="mt-3 flex items-start gap-2 py-1.5">
            <span className="mt-2 h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0 animate-pulse" />
            <p className={cn(
              "text-[11px] leading-relaxed",
              waitingState
                ? "text-[var(--text-tertiary)]"
                : currentThought && currentThought !== "Thinking..."
                  ? "text-[var(--text-secondary)] italic"
                  : "shimmer-text",
            )}>
              {currentThought || waitingState?.message || "Thinking\u2026"}
            </p>
          </div>
        )}

        {worklogEntries.length > 0 && (
          <div className="mt-3 space-y-2">
            {worklogEntries.map((entry, index) => {
              if (entry.kind === "thinking") {
                return (
                  <ThinkingBlock key={`${message.id}-wl-${index}`} content={entry.text} durationMs={entry.durationMs} />
                );
              }
              if (entry.kind === "collapsed_group") {
                return (
                  <CollapsedGroup key={`${message.id}-wl-${index}`} entry={entry} />
                );
              }
              if (entry.kind === "action") {
                const chrome = getToolChrome(entry.toolType);
                const Icon = chrome?.icon;
                const isFileAction = !!entry.filePath;
                const handleFileClick = isFileAction ? () => {
                  window.dispatchEvent(
                    new CustomEvent("codebaseOpenFile", { detail: { path: entry.filePath, scrollToLine: 1 } })
                  );
                } : undefined;
                return (
                  <div
                    key={`${message.id}-wl-${index}`}
                    className={cn("flex items-start gap-2", isFileAction && "cursor-pointer hover:bg-[var(--bg-secondary)] rounded -mx-1 px-1 transition-colors")}
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
                  <div key={`${message.id}-wl-${index}`} className="flex items-start gap-2 pl-4">
                    <span className="mt-[7px] text-[var(--text-tertiary)] text-[12px] leading-none select-none flex-shrink-0">⎿</span>
                    <div className="min-w-0 flex-1 text-[13px] text-[var(--text-secondary)] [&>div>div:first-child]:mt-1">
                      <FormattedMessage content={entry.text} />
                    </div>
                  </div>
                );
              }
              if (entry.kind === "response") {
                return (
                  <div key={`${message.id}-wl-${index}`}>
                    <FormattedMessage content={entry.text} />
                  </div>
                );
              }
              if (entry.kind === "block") {
                return (
                  <div key={`${message.id}-wl-${index}`} className="pl-4">
                    <FormattedMessage content={entry.text} />
                  </div>
                );
              }
              return (
                <div key={`${message.id}-wl-${index}`} className="flex items-start gap-2">
                  <span className="mt-[12px] h-1.5 w-1.5 rounded-full bg-[var(--text-primary)] flex-shrink-0" />
                  <div className="min-w-0 flex-1 text-[13px] text-[var(--text-primary)] [&>div>div:first-child]:mt-1">
                    <FormattedMessage content={entry.text} />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Activity spinner — shows current tool verb + elapsed time */}
        {isStreaming && activeTool && (
          <ActivitySpinner activeTool={activeTool} />
        )}

        {/* Response text — only show separately if worklog doesn't already contain interleaved response blocks */}
        {!showContentAboveTasks && !worklogEntries.some(e => e.kind === "response") && (message.content || streamContent) && (
          <FormattedMessage content={message.content || streamContent || ""} />
        )}

        {/* Clarification */}
        {message.clarification && (
          <ClarificationBlock
            clarification={message.clarification}
            onSelect={onSelectClarification}
          />
        )}

        {message.clientAttachment === "google_test_session" && isAgent && <GoogleTestSessionChatCta />}
        {message.clientAttachment === "configure_secrets" && isAgent && <ConfigureSecretsFromThreadCta />}
        {message.clientAttachment === "configure_gcp_connection" && isAgent && (
          <ConfigureGcpConnectionFromThreadCta />
        )}
      </div>
    </div>
  );
}


// ThreadsProps imported from ./thread-types

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export function Threads({ project, onAnalysisComplete, initialThreadId, onThreadSelect }: ThreadsProps) {
  const { user, isAuthenticated } = useAuth();
  const [view, setView] = useState<"threads" | "detail">("threads");
  const [selectedThreadId, _setSelectedThreadId] = useState<string | null>(null);

  const setSelectedThreadId = useCallback((id: string | null) => {
    _setSelectedThreadId(id);
    onThreadSelect?.(id);
  }, [onThreadSelect]);
  const [commentInput, setCommentInput] = useState("");
  const [pendingApprovals, setPendingApprovals] = useState<any[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [sortBy] = useState<"newest" | "oldest">("newest");
  const [hasProject, setHasProject] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [awaitingGeneratedTitleForId, setAwaitingGeneratedTitleForId] = useState<string | null>(null);
  const [titleReveal, setTitleReveal] = useState<{ threadId: string; display: string } | null>(null);

  const selectedThreadIdRef = useRef<string | null>(null);
  const pendingTitleContextRef = useRef<{ threadId: string; prompt: string } | null>(null);
  const titleRevealIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Demo context for full demo experience
  const demo = useDemoOptional();
  const { google } = useTestGoogleSession();

  const mockGoogleSessionMessages = useMemo((): Message[] => {
    const content =
      google.status === "connected"
        ? "Your Google test session is active — I can now run authenticated test scenarios against your app."
        : "I noticed your app has routes that require authentication. I'll need a test session to exercise those flows.";

    return [
      {
        id: "msg-google-test-session",
        author: "agent",
        content,
        timestamp: "Just now",
        clientAttachment: "google_test_session",
      },
    ];
  }, [google.status]);

  // Demo project tracking (for unauthenticated demo mode)
  const [demoProject, setDemoProject] = useState<string | null>(null);

  useEffect(() => {
    const handleWorkspaceStarterPrompt = (
      e: CustomEvent<{ title?: string; prompt: string }>
    ) => {
      setSelectedThreadId("new");
      setView("detail");
      const title = e.detail.title?.trim();
      const prompt = e.detail.prompt || "";
      setCommentInput(title ? `${title}\n\n${prompt}`.trim() : prompt);
    };

    window.addEventListener(
      "workspaceStarterPrompt",
      handleWorkspaceStarterPrompt as EventListener
    );

    return () => {
      window.removeEventListener(
        "workspaceStarterPrompt",
        handleWorkspaceStarterPrompt as EventListener
      );
    };
  }, []);
  
  // Compute effective demo project - defaults to "ecommerce" for unauthenticated users
  const effectiveDemoProject = !isAuthenticated 
    ? (demoProject || "ecommerce") 
    : undefined;
  
  // When demo mode starts or thread changes, auto-open the demo thread
  useEffect(() => {
    if (demo?.isDemo && demo?.currentThread) {
      // Auto-select and show demo thread
      setSelectedThreadId(demo.currentThread.id);
      setView("detail");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demo?.isDemo, demo?.currentThread?.id]);
  
  // Reset demo state when demo ends
  useEffect(() => {
    if (!demo?.isDemo && (selectedThreadId?.startsWith("demo-") || selectedThreadId?.startsWith("live-"))) {
      // Demo ended, go back to threads
      setSelectedThreadId(null);
      setView("threads");
    }
  }, [demo?.isDemo, selectedThreadId]);

  // Handle initialThreadId prop - auto-open thread when set from outside
  // Works like Cursor's deep-link: ?thread=<id> opens that thread directly
  useEffect(() => {
    if (!initialThreadId) return;
    
      setSelectedThreadId(initialThreadId);
      setView("detail");

    if (["new", "analyzing", "0"].includes(initialThreadId)) {
      return;
    }
      
    // Fetch the thread directly by ID (works even without a current project)
    // This enables deep-linking to any thread via ?thread=<id>
    fetch(`${API_URL}/api/threads/${initialThreadId}`, {
      credentials: "include",
    })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data) {
          const threadData: Thread = {
            id: data.id,
            threadNumber: data.thread_number || 0,
            title: data.title || "Untitled Thread",
            status: data.status === "active" ? "open" : data.status,
            createdAt: new Date(data.created_at).toLocaleDateString(),
            updatedAt: new Date(data.updated_at).toLocaleDateString(),
            messageCount: data.total_messages || 0,
            activityCount: 0,
            preview: "",
          };
          
          // Add this thread to the list (or replace if already there)
          setThreads(prev => {
            const exists = prev.some(t => t.id === threadData.id);
            return exists ? prev : [threadData, ...prev];
          });
          
          // Also fetch messages for this thread
          const msgs = data.messages;
          if (msgs && Array.isArray(msgs) && msgs.length > 0) {
            const apiMessages: Message[] = msgs
              .filter((m: RawMessage) => !m.metadata?.incremental && !m.metadata?.session_marker)
              .map((m: RawMessage) => ({
                id: m.id,
                author: m.role === "user" ? "user" : "agent",
                content: m.content || "",
                timestamp: new Date(m.created_at).toLocaleDateString(),
                tool_calls: m.tool_calls,
                worklog: getPreferredWorklog(m),
                todos: getPreferredTodos(m),
                activities: getPreferredActivities(m),
              }));
            setThreadMessages(prev => ({
              ...prev,
              [initialThreadId]: apiMessages,
            }));
          }
        }
      })
      .catch(err => console.error("Failed to fetch thread:", err));
    
    // Also refresh thread list if we have a project
      if (project?.id && isAuthenticated && user) {
        fetch(`${API_URL}/api/threads/project/${project.id}`, {
          credentials: "include",
        })
          .then(res => res.ok ? res.json() : null)
          .then(data => {
            if (data?.threads?.length > 0) {
              const apiThreads: Thread[] = data.threads.map((t: RawThread) => ({
                id: t.id,
                threadNumber: t.thread_number || 0,
                title: t.title || "Untitled Thread",
                status: normalizeThreadStatus(t.status),
                createdAt: new Date(t.created_at).toLocaleDateString(),
                updatedAt: new Date(t.updated_at).toLocaleDateString(),
                messageCount: t.total_messages || 0,
                activityCount: 0,
                preview: "",
              }));
              setThreads(apiThreads);
            }
          })
          .catch(() => {});
      }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialThreadId, project?.id, isAuthenticated, user]);
  
  // Initialize and listen for demo project changes and DevOps thread open events
  useEffect(() => {
    // Initialize demoProject from URL on mount (for demo mode)
    if (!isAuthenticated) {
      const params = new URLSearchParams(window.location.search);
      const urlDemoProject = params.get("demoProject") || "ecommerce"; // Default to ecommerce for demo
      setDemoProject(urlDemoProject);
    }
    
    const handleDemoProjectChange = (e: CustomEvent<{ slug: string }>) => {
      setDemoProject(e.detail.slug);
    };
    
    window.addEventListener("demoProjectChanged", handleDemoProjectChange as EventListener);
    
    return () => {
      window.removeEventListener("demoProjectChanged", handleDemoProjectChange as EventListener);
    };
  }, [isAuthenticated]);

  // Track previous project ID to detect project changes/deletions
  const prevProjectIdRef = useRef<string | null>(null);
  
  // Reset console state when project changes (switch or delete)
  useEffect(() => {
    const currentProjectId = project?.id || null;
    const prevProjectId = prevProjectIdRef.current;
    
    // If project changed (including being deleted or switched)
    if (prevProjectId !== null && currentProjectId !== prevProjectId) {
      console.log(`[Threads] Project changed from ${prevProjectId} to ${currentProjectId}, resetting console state`);
      
      // Clear thread-specific state
      setCommentInput("");
      setAnalysisJustCompleted(false);
      
      // Reset thread messages (keep defaults)
      setThreadMessages({
        "0": [NO_PROJECT_MESSAGE],
        "1": [ANALYZING_MESSAGE],
      });
      
      // If no project (deleted), show welcome thread
      if (!currentProjectId) {
        setThreads([WELCOME_THREAD]);
        setSelectedThreadId("0");
        setView("detail");  // Show welcome message
      } else {
        // Switching to another project - go to threads list
        setSelectedThreadId(null);
        setView("threads");
      }
    }
    
    // Update ref for next comparison
    prevProjectIdRef.current = currentProjectId;
  }, [project?.id]);

  // Track real thread info from project status (when analyzing)
  const [analysisThreadInfo, setAnalysisThreadInfo] = useState<{ threadId?: string; threadNumber?: number } | null>(null);
  
  // Refs to avoid stale closures in callbacks (always have latest values)
  const analysisThreadInfoRef = useRef(analysisThreadInfo);
  const projectRef = useRef(project);
  useEffect(() => { analysisThreadInfoRef.current = analysisThreadInfo; }, [analysisThreadInfo]);
  useEffect(() => { projectRef.current = project; }, [project]);
  
  // Import/analysis in progress — from /status (drives project SSE in this panel only; no synthetic "Analyzing…" thread list)
  const refetchProjectImportStatus = useCallback(async () => {
    if (!project?.id) return null;

    setHasProject(true);

    try {
      const res = await fetch(`${API_URL}/api/projects/${project.id}/status`, {
        credentials: "include",
      });
      const data = res.ok ? await res.json() : null;
      if (data) {
        const shouldAnalyze = data.status === "pending" || data.status === "analyzing";
        console.log(`[Threads] Project ${project.id} status: ${data.status}, shouldAnalyze: ${shouldAnalyze}`);
        setIsAnalyzing(shouldAnalyze);
        if (data.thread_id) {
          setAnalysisThreadInfo({
            threadId: data.thread_id,
            threadNumber: data.thread_number || 1,
          });
        }
        return data;
      }
      const shouldAnalyze = project.status === "pending" || project.status === "analyzing";
      setIsAnalyzing(shouldAnalyze);
    } catch (err) {
      console.log("Failed to fetch project status:", err);
      const shouldAnalyze = project.status === "pending" || project.status === "analyzing";
      setIsAnalyzing(shouldAnalyze);
    }
    return null;
  }, [project?.id, project?.status]);

  useEffect(() => {
    if (project?.id) {
      void refetchProjectImportStatus();
    } else if (!project) {
      setHasProject(false);
      setIsAnalyzing(false);
      setAnalysisThreadInfo(null);
    }
  }, [project?.id, project?.status, refetchProjectImportStatus]);

  // Pending-actions polling is deferred until after useThreadStream is defined
  // (see the effect below that uses threadHasActiveRun)

  // Fetch real threads from API when project changes
  const [threads, setThreads] = useState<Thread[]>([]);
  // const [isLoadingThreads, setIsLoadingThreads] = useState(false);
  
  // Fetch threads from the API
  useEffect(() => {
    const fetchThreads = async () => {
      // If a deep-linked thread is set, skip normal thread loading —
      // the initialThreadId handler manages its own thread state
      if (initialThreadId) return;
      
      // Demo mode: show demo threads when active
      if (demo?.isDemo && demo.threads.length > 0) {
        const demoThreads: Thread[] = demo.threads.map(t => ({
          id: t.id,
          threadNumber: t.thread_number,
          title: t.title,
          status: t.status === "streaming" ? "in_progress" as const : t.status === "completed" ? "open" as const : "open" as const,
          createdAt: "Just now",
          updatedAt: "Just now",
          messageCount: 1,
          activityCount: demo.tasks.length,
          preview: demo.isStreaming ? "Streaming..." : "Completed",
        }));
        setThreads(demoThreads);
        return;
      }
      
      // Signed-out: demo threads + any local guest threads (re-merge so effect re-runs don't drop them)
      if (!isAuthenticated) {
        setThreads((prev) => {
          const guestCreated = prev.filter((t) => isGuestThreadId(t.id));
          return [...guestCreated, ...DEMO_THREADS];
        });
        return;
      }
      
      if (!project?.id || !user) {
        // No project or user - show welcome thread
        setThreads([WELCOME_THREAD]);
        return;
      }

      // setIsLoadingThreads(true);
      try {
        const response = await fetch(`${API_URL}/api/threads/project/${project.id}`, {
          credentials: "include",
        });

        if (response.ok) {
          const data = await response.json();
          const apiThreads: Thread[] = (data.threads || []).map((t: RawThread) => ({
            id: t.id,
            threadNumber: t.thread_number || 0,  // Human-readable #1, #2, #3
            title: t.title || "Untitled Thread",
            status: normalizeThreadStatus(t.status),
            createdAt: new Date(t.created_at).toLocaleDateString(),
            updatedAt: new Date(t.updated_at).toLocaleDateString(),
            messageCount: t.total_messages || 0,
            activityCount: 0,
            preview: "", // Would need to fetch last message
          }));

          // If no threads exist, show welcome thread
          if (apiThreads.length === 0) {
            setThreads([WELCOME_THREAD]);
          } else {
            setThreads(apiThreads);
          }
        } else {
          // Fallback to welcome thread on error
          setThreads([WELCOME_THREAD]);
        }
      } catch (err) {
        console.error("Failed to fetch threads:", err);
        setThreads([WELCOME_THREAD]);
      } finally {
        // setIsLoadingThreads(false);
      }
    };

    fetchThreads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id, user, hasProject, isAnalyzing, analysisThreadInfo?.threadId, analysisThreadInfo?.threadNumber, project?.threadId, project?.threadNumber, project?.name, effectiveDemoProject, isAuthenticated, demo?.isDemo, demo?.threads, demo?.isStreaming, demo?.tasks.length, initialThreadId]);

  // Resolve workspace branches for threads (adds branch badges)
  useEffect(() => {
    if (!isAuthenticated || threads.length === 0) return;
    const realThreads = threads.filter(
      (t) =>
        !["0", "new"].includes(t.id) &&
        !t.id.startsWith("demo-") &&
        !t.id.startsWith("mock") &&
        t.id.includes("-"),
    );
    if (realThreads.length === 0) return;

    let cancelled = false;
    const resolveBranches = async () => {
      const updates: Record<string, string> = {};
      await Promise.allSettled(
        realThreads.map(async (t) => {
          try {
            const resp = await fetch(`${API_URL}/api/threads/${t.id}/workspace/branch`, {
              credentials: "include",
            });
            if (resp.ok) {
              const { branch } = await resp.json();
              if (branch) updates[t.id] = branch;
            }
          } catch { /* ignore */ }
        })
      );
      if (cancelled || Object.keys(updates).length === 0) return;
      setThreads(prev => prev.map(t =>
        updates[t.id] ? { ...t, branch: updates[t.id] } : t
      ));
    };
    void resolveBranches();
    return () => { cancelled = true; };
  }, [threads.length, isAuthenticated]);

  const [threadMessages, setThreadMessages] = useState<Record<string, Message[]>>({
    "0": [NO_PROJECT_MESSAGE],
    "1": [ANALYZING_MESSAGE],
  });
  const [isRefreshingThreadMessages, setIsRefreshingThreadMessages] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [showCloseDialog, setShowCloseDialog] = useState(false);
  const [showReopenDialog, setShowReopenDialog] = useState(false);
  const [threadDeleteDialog, setThreadDeleteDialog] = useState<
    { type: "idle" } | { type: "confirm"; id: string; title: string }
  >({ type: "idle" });
  const [isDeletingThread, setIsDeletingThread] = useState(false);
  const commentTextareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Track if analysis just completed (to keep showing tasks while fetching messages)
  const [analysisJustCompleted, setAnalysisJustCompleted] = useState(false);
  
  // Store completed streaming activities to attach to the final message
  const completedActivitiesRef = useRef<Activity[]>([]);

  const isViewingAnalysisThread = false;

  const mapApiMessages = useCallback((messages: RawMessage[]): Message[] => {
    return messages
      .filter((m: RawMessage) => !m.metadata?.incremental && !m.metadata?.session_marker)
      .map((m: RawMessage) => ({
        id: m.id,
        author: m.role === "user" ? "user" : "agent",
        content: normalizeContent(m.content),
        timestamp: new Date(m.created_at).toLocaleDateString(),
        tool_calls: m.tool_calls,
        worklog: getPreferredWorklog(m),
        todos: getPreferredTodos(m),
        activities: getPreferredActivities(m),
      }));
  }, []);

  const fetchThreadMessagesWithRetry = useCallback(async (
    threadId: string,
    retries = 4,
    delayMs = 250,
    options?: {
      minCount?: number;
      requireLastAgent?: boolean;
    },
  ): Promise<Message[]> => {
    let bestResult: Message[] = [];
    for (let attempt = 0; attempt < retries; attempt++) {
      try {
        const response = await fetch(`${API_URL}/api/threads/${threadId}/messages`, {
          credentials: "include",
        });
        if (response.ok) {
          const data = await response.json();
          const apiMessages = mapApiMessages(data.messages || []);
          if (apiMessages.length > 0) {
            bestResult = apiMessages;
          }
          const meetsMinCount = apiMessages.length >= (options?.minCount ?? 1);
          const hasExpectedLastMessage = !options?.requireLastAgent
            || apiMessages[apiMessages.length - 1]?.author === "agent";
          if (meetsMinCount && hasExpectedLastMessage) {
            return apiMessages;
          }
        }
      } catch (err) {
        console.error(`[thread-complete] Fetch attempt ${attempt + 1} failed:`, err);
      }

      if (attempt < retries - 1) {
        await new Promise(resolve => setTimeout(resolve, delayMs));
      }
    }

    return bestResult;
  }, [mapApiMessages]);
  
  // Convert project stream events to activities for analyzing view
  // Defined as a stable function to be used in onComplete callback
  const projectEventsToActivities = useCallback((events: AgentEvent[], isComplete: boolean): Activity[] => {
    // Group events into logical tasks based on task_started/task_completed or action events.
    // Uses a Map to deduplicate by task_id — if an activity is retried (e.g. after
    // server restart), the latest attempt replaces the previous one.
    const activitiesMap = new Map<string, Activity>();
    const activitiesOrder: string[] = [];  // Track insertion order
    let currentActivityId: string | null = null;
    let eventBuffer: string[] = [];

    const flushCurrent = (status: Activity["status"]) => {
      if (currentActivityId) {
        const act = activitiesMap.get(currentActivityId);
        if (act) {
          act.status = status;
          act.content = eventBuffer.join("\n\n");
        }
      }
    };
    
    for (const event of events) {
      if (event.type === "task_started" || event.type === "action") {
        // Start a new activity - mark previous one as completed
        flushCurrent("completed");

        // Safely extract title from content (might be string or object)
        const titleContent = typeof event.content === "string" ? event.content : 
                            (event.content?.title || event.content?.message || event.metadata?.title || "Processing");
        const actId = event.metadata?.task_id || `activity-${activitiesMap.size}`;
        
        // Replace previous activity with same id (activity retry) or create new
        activitiesMap.set(actId, {
          id: actId,
          status: "in_progress",
          title: titleContent,
        });
        // Track order: add only if new, otherwise keep original position
        if (!activitiesOrder.includes(actId)) {
          activitiesOrder.push(actId);
        }
        currentActivityId = actId;
        eventBuffer = [];
      } else if (event.type === "task_completed") {
        if (currentActivityId) {
          if (event.content) {
            const completedMsg = typeof event.content === "string" ? event.content : 
                                (event.content?.message || event.content?.result || JSON.stringify(event.content));
            eventBuffer.push(`✓ ${completedMsg}`);
          }
          flushCurrent("completed");
          currentActivityId = null;
          eventBuffer = [];
        }
      } else if (event.type === "task_failed") {
        if (currentActivityId) {
          const errorMsg = typeof event.content === "string" ? event.content : 
                          (event.content?.error || event.content?.message || JSON.stringify(event.content));
          eventBuffer.push("**Error:** " + errorMsg);
          flushCurrent("failed");
          currentActivityId = null;
          eventBuffer = [];
        }
      } else if (event.type === "complete") {
        // Final completion event - wrap up any in-progress activity
        flushCurrent("completed");
        currentActivityId = null;
      } else if (event.type === "error") {
        if (currentActivityId) {
          const errorContent = typeof event.content === "string" ? event.content : 
                              (event.content?.error || event.content?.message || JSON.stringify(event.content));
          eventBuffer.push("**Error:** " + errorContent);
          flushCurrent("failed");
          currentActivityId = null;
        }
      } else if ((event.type as string) === "browser_action") {
        if (!currentActivityId) {
          const initId = "activity-browser";
          activitiesMap.set(initId, { id: initId, status: "in_progress", title: "Browser" });
          if (!activitiesOrder.includes(initId)) activitiesOrder.push(initId);
          currentActivityId = initId;
          eventBuffer = [];
        }
        const ba = typeof event.content === "object" && event.content ? event.content as Record<string, unknown> : {};
        const label = typeof ba.label === "string" ? ba.label : String(ba.action || "browser");
        const status = typeof ba.status === "string" ? ba.status : "";
        if (status === "started") {
          eventBuffer.push(`${label}...`);
        } else if (status === "completed") {
          const pageTitle = typeof ba.page_title === "string" ? ba.page_title : "";
          const url = typeof ba.url === "string" ? ba.url : "";
          const extra = pageTitle ? ` — ${pageTitle}` : url ? ` — ${url}` : "";
          eventBuffer.push(`✓ ${label}${extra}`);
        } else if (status === "error") {
          eventBuffer.push(`✗ ${label}`);
        }
      } else if (event.type === "thinking" || event.type === "thought" || event.type === "progress" || event.type === "tool_result" || event.type === "tool_call") {
        // If no activity exists yet, create a default one for early events
        if (!currentActivityId) {
          const initId = "activity-init";
          activitiesMap.set(initId, {
            id: initId,
            status: "in_progress",
            title: "Initializing",
          });
          if (!activitiesOrder.includes(initId)) {
            activitiesOrder.push(initId);
          }
          currentActivityId = initId;
          eventBuffer = [];
        }
        // Add event to current activity - filter out verbose/noisy messages
        // Safely extract content as string
        const rawContent = event.content;
        const content = typeof rawContent === "string" ? rawContent : 
                       (rawContent?.message || rawContent?.content || rawContent?.text || "");
        const contentLower = content.toLowerCase();
        
        // Skip verbose messages (file-by-file noise)
        const isVerboseMessage = 
          contentLower.startsWith("reading ") ||
          contentLower.startsWith("skipping ") ||
          contentLower.includes(" for api calls") ||
          contentLower.includes("- no api patterns") ||
          contentLower.includes("no api patterns") ||
          /^analyzing .+\.(tsx?|jsx?|vue|py|go)$/i.test(contentLower);
        
        if (isVerboseMessage) {
          // Skip this event entirely - too noisy
          continue;
        }
        
        // Thinking is ephemeral — handled by StreamingIndicator's shimmer, not persisted in task content
        if (event.type === "thinking" || event.type === "thought") {
          continue;
        } else if (event.type === "progress") {
          const progress = event.metadata?.current && event.metadata?.total 
            ? `[${event.metadata.current}/${event.metadata.total}] ` 
            : "";
          eventBuffer.push(`${progress}${content}`);
        } else if (event.type === "tool_result") {
          eventBuffer.push(`✓ ${content}`);
        } else if (event.type === "tool_call") {
          eventBuffer.push(`> ${content}`);
        } else if (event.type === "file_read") {
          // Only show summary file info, not per-file reads
          if (content.toLowerCase().startsWith("found ")) {
            eventBuffer.push(content);
          }
        } else if (event.type === "contract") {
          eventBuffer.push(content);
        }
      }
    }
    
    // Handle remaining activity 
    if (currentActivityId) {
      const act = activitiesMap.get(currentActivityId);
      if (act) {
        act.status = isComplete ? "completed" : "in_progress";
        act.content = eventBuffer.join("\n\n");
      }
    }
    
    // Return activities in insertion order (deduplicated)
    return activitiesOrder
      .map(id => activitiesMap.get(id))
      .filter((a): a is Activity => a !== undefined);
  }, []);
  
  // Project streaming - connect when analyzing a project
  // This uses /api/projects/{project_id}/stream endpoint
  useEffect(() => {
    console.log(`[Threads] Stream conditions - isAnalyzing: ${isAnalyzing}, viewingAnalysisThread: ${isViewingAnalysisThread}, project: ${project?.id || 'null'}, enabled: ${isViewingAnalysisThread && !!project?.id}`);
  }, [isAnalyzing, isViewingAnalysisThread, project?.id]);

  const {
    events: projectStreamEvents,
    tasks: projectStreamTasks,
    isConnected: isProjectStreamConnected,
    isComplete: isProjectStreamComplete,
  } = useProjectStream(
    isViewingAnalysisThread && project?.id ? project.id : null,
    {
      enabled: isViewingAnalysisThread && !!project?.id,
      onComplete: async (allEvents: AgentEvent[]) => {
        // Mark analysis as just completed - keeps showing completed tasks while we fetch
        setAnalysisJustCompleted(true);
        
        // Capture the final streaming activities.
        // First try deriving from events; if the events were trimmed and we lost
        // early task_started events, fall back to the separately-tracked tasks state
        // which is never trimmed.
        let finalActivities = projectEventsToActivities(allEvents, true);
        
        // Sanity check: if tasks state has more items, prefer it
        const tasksSnapshot = projectStreamTasks;
        if (tasksSnapshot.length > finalActivities.length) {
          finalActivities = tasksSnapshot.map(task => ({
            id: task.id,
            status: task.status === "in_progress" ? "completed" as const : task.status,
            title: task.name,
            content: task.events.length > 0
              ? task.events.map(e => {
                  // Safely extract content as string
                  const contentStr = typeof e.content === "string" ? e.content : 
                                    (e.content?.message || e.content?.content || e.content?.result || JSON.stringify(e.content));
                  if (e.type === "tool_result") return `✓ ${contentStr}`;
                  return contentStr;
                }).filter(Boolean).join("\n\n")
              : undefined,
          }));
        }
        completedActivitiesRef.current = finalActivities;
        
        console.log(`[onComplete] Captured ${finalActivities.length} activities from ${allEvents.length} events, ${tasksSnapshot.length} tasks`);
        
        // Extract thread_id from the complete event's metadata (most reliable source)
        const completeEvent = allEvents.find(e => e.type === "complete");
        const threadIdFromEvent = completeEvent?.metadata?.thread_id;
        // const threadNumberFromEvent = completeEvent?.metadata?.thread_number;
        
        // Use refs to get latest values (avoid stale closures)
        const currentAnalysisInfo = analysisThreadInfoRef.current;
        const currentProject = projectRef.current;
        
        // Priority: complete event metadata > analysisThreadInfo > project.threadId
        const threadId = threadIdFromEvent || currentAnalysisInfo?.threadId || currentProject?.threadId;
        
        console.log(`[onComplete] threadId: ${threadId} (from event: ${threadIdFromEvent}, analysisInfo: ${currentAnalysisInfo?.threadId}, project: ${currentProject?.threadId})`);
        
        if (!threadId) {
          // No thread ID available - this shouldn't happen, but create a fallback
          console.error("[onComplete] No threadId available! Using fallback");
          // Store under a synthetic ID so UI doesn't go blank
          const fallbackThreadId = `analysis-${currentProject?.id || 'unknown'}-${Date.now()}`;
          const fallbackMessage: Message = {
            id: `analysis-fallback-${Date.now()}`,
            author: "agent",
            content: `I've reviewed your **${currentProject?.name || "project"}** repository and prepared the backend plan.\n\nYou can now review the API endpoints, deployment architecture, and integration guidance before deploying.`,
            timestamp: new Date().toLocaleDateString(),
            activities: completedActivitiesRef.current,
          };
          setThreadMessages(prev => ({
            ...prev,
            [fallbackThreadId]: [fallbackMessage],
          }));
          setSelectedThreadId(fallbackThreadId);
        } else if (threadId) {
          // Helper to fetch messages with retry (handles race condition with DB commit)
          const fetchMessagesWithRetry = async (retries = 3, delay = 500): Promise<Message[]> => {
            for (let i = 0; i < retries; i++) {
              try {
                const response = await fetch(`${API_URL}/api/threads/${threadId}/messages`, {
                  credentials: "include",
                });
                
                if (response.ok) {
                  const data = await response.json();
                  if (data.messages && data.messages.length > 0) {
                    return (data.messages || []).map((m: RawMessage, idx: number) => {
                      // Prefer streaming activities (live), fallback to parsed tool_calls (from DB)
                      let activities: Activity[] | undefined;
                      
                      if (m.role === "assistant" && idx === 0 && completedActivitiesRef.current.length > 0) {
                        // We have live streaming activities - use them
                        activities = completedActivitiesRef.current;
                      } else {
                        activities = getPreferredActivities(m);
                      }
                      
                      return {
                        id: m.id,
                        author: m.role === "user" ? "user" : "agent",
                        content: m.content || "",
                        timestamp: new Date(m.created_at).toLocaleDateString(),
                        tool_calls: m.tool_calls,
                        worklog: getPreferredWorklog(m),
                        todos: getPreferredTodos(m),
                        activities,
                      };
                    });
                  }
                }
              } catch (err) {
                console.error(`[onComplete] Fetch attempt ${i + 1} failed:`, err);
              }
              
              // Wait before retry (except on last attempt)
              if (i < retries - 1) {
                await new Promise(resolve => setTimeout(resolve, delay));
              }
            }
            return [];
          };

          const apiMessages = await fetchMessagesWithRetry();
          
          if (apiMessages.length > 0) {
            // Store messages AND ensure selectedThreadId points to the real thread
            console.log(`[onComplete] Storing ${apiMessages.length} messages for threadId: ${threadId}`);
            setThreadMessages(prev => ({
              ...prev,
              [threadId]: apiMessages,
            }));
            // Update selectedThreadId to match where we stored messages
            setSelectedThreadId(threadId);
            console.log(`[onComplete] Set selectedThreadId to: ${threadId}`);
          } else {
            // Fallback: API returned empty (race condition) - create synthetic message
            // This ensures the UI doesn't go blank during transition
            console.log("[onComplete] API returned empty, using captured activities as fallback");
            const fallbackMessage: Message = {
              id: `analysis-fallback-${Date.now()}`,
              author: "agent",
              content: `I've reviewed your **${currentProject?.name || "project"}** repository and prepared the backend plan.\n\nYou can now review the API endpoints, deployment architecture, and integration guidance before deploying.`,
              timestamp: new Date().toLocaleDateString(),
              activities: completedActivitiesRef.current,
            };
            setThreadMessages(prev => ({
              ...prev,
              [threadId]: [fallbackMessage],
            }));
            setSelectedThreadId(threadId);
          }
        }
        
        // Refresh /status so isAnalyzing matches the server; then clear transition flag
        console.log("[onComplete] Starting 100ms timeout before refetch + clearing analysisJustCompleted");
        setTimeout(() => {
          void refetchProjectImportStatus().then(() => {
            console.log("[onComplete] Refetched project import status");
          });
          setAnalysisJustCompleted(false);
          onAnalysisComplete?.();
        }, 100);
      },
    }
  );

  useEffect(() => {
    selectedThreadIdRef.current = selectedThreadId;
  }, [selectedThreadId]);

  const clearTitleRevealTimers = useCallback(() => {
    if (titleRevealIntervalRef.current) {
      clearInterval(titleRevealIntervalRef.current);
      titleRevealIntervalRef.current = null;
    }
  }, []);

  const beginTitleReveal = useCallback(
    (threadId: string, fullTitle: string) => {
      clearTitleRevealTimers();
      setAwaitingGeneratedTitleForId((id) => (id === threadId ? null : id));
      const trimmed = fullTitle.trim();
      if (!trimmed) {
        setTitleReveal(null);
        return;
      }
      const perTick = trimmed.length > 48 ? 3 : trimmed.length > 24 ? 2 : 1;
      const ms = trimmed.length > 48 ? 14 : 20;
      let i = Math.min(perTick, trimmed.length);
      setTitleReveal({ threadId, display: trimmed.slice(0, i) });
      if (i >= trimmed.length) {
        setThreads((prev) =>
          prev.map((t) => (t.id === threadId ? { ...t, title: trimmed } : t)),
        );
        setTitleReveal(null);
        return;
      }
      titleRevealIntervalRef.current = setInterval(() => {
        i = Math.min(trimmed.length, i + perTick);
        const slice = trimmed.slice(0, i);
        setTitleReveal((prev) =>
          prev && prev.threadId === threadId ? { threadId, display: slice } : prev,
        );
        if (i >= trimmed.length) {
          if (titleRevealIntervalRef.current) {
            clearInterval(titleRevealIntervalRef.current);
            titleRevealIntervalRef.current = null;
          }
          setThreads((prev) =>
            prev.map((t) => (t.id === threadId ? { ...t, title: trimmed } : t)),
          );
          setTitleReveal(null);
        }
      }, ms);
    },
    [clearTitleRevealTimers],
  );

  useEffect(() => () => clearTitleRevealTimers(), [clearTitleRevealTimers]);

  useEffect(() => {
    setTitleReveal((prev) => {
      if (!prev || !selectedThreadId || prev.threadId === selectedThreadId) {
        return prev;
      }
      clearTitleRevealTimers();
      return null;
    });
    setAwaitingGeneratedTitleForId((id) => {
      if (!id) return null;
      if (!selectedThreadId || id !== selectedThreadId) return null;
      return id;
    });
  }, [selectedThreadId, clearTitleRevealTimers]);

  useEffect(() => {
    if (!awaitingGeneratedTitleForId) return;
    const tid = awaitingGeneratedTitleForId;
    const t = window.setTimeout(() => {
      const ctx = pendingTitleContextRef.current;
      if (!ctx || ctx.threadId !== tid) return;
      pendingTitleContextRef.current = null;
      setAwaitingGeneratedTitleForId((x) => (x === tid ? null : x));
      const fb =
        deriveThreadTitleFromMessage(ctx.prompt) || PLACEHOLDER_CHAT_TITLE;
      beginTitleReveal(tid, fb);
    }, 35000);
    return () => window.clearTimeout(t);
  }, [awaitingGeneratedTitleForId, beginTitleReveal]);

  const handleStreamThreadTitle = useCallback(
    (title: string, metaTid?: string) => {
      const tid = metaTid || selectedThreadIdRef.current;
      if (!tid || !title.trim()) return;
      pendingTitleContextRef.current = null;
      beginTitleReveal(tid, title.trim());
    },
    [beginTitleReveal],
  );

  // Thread streaming - connect when viewing a thread in detail (not analyzing)
  const {
    events: threadStreamEvents,
    tasks: threadStreamTasks,
    todos: threadStreamTodos,
    isStreaming: isThreadStreaming,
    hasActiveRun: threadHasActiveRun,
    currentThought: threadCurrentThought,
    activeTool: threadActiveTool,
    waitingState: threadWaitingState,
    connect: connectThreadStream,
    disconnect: disconnectThreadStream,
    clear: clearThreadStream,
  } = useThreadStream(
    // Real persisted threads only (UUID-style), not mock ids or local guest-* threads
    (() => {
      const id = selectedThreadId;
      const isStreamable =
        !!id &&
        id !== "0" &&
        id !== "new" &&
        id !== "analyzing" &&
        !id.startsWith("provisional-") &&
        id.includes("-") &&
        !isGuestThreadId(id);
      return view === "detail" && isStreamable ? id : null;
    })(),
    {
      enabled: (() => {
        const id = selectedThreadId;
        return (
          view === "detail" &&
          !!id &&
          id !== "0" &&
          id !== "new" &&
          id !== "analyzing" &&
          !id.startsWith("provisional-") &&
          id.includes("-") &&
          !isGuestThreadId(id)
        );
      })(),
      onComplete: async () => {
        const tid = selectedThreadIdRef.current;
        if (!tid || tid === "0" || tid === "new" || tid === "analyzing" || tid.startsWith("provisional-") || isGuestThreadId(tid)) {
          return;
        }

        setIsRefreshingThreadMessages(true);
        try {
          const apiMessages = await fetchThreadMessagesWithRetry(tid, 8, 300, {
            minCount: 1,
            requireLastAgent: true,
          });
          if (apiMessages.length > 0) {
            setThreadMessages(prev => ({
              ...prev,
              [tid]: apiMessages,
            }));
          }
        } catch (err) {
          console.error("[thread-complete] Failed to refresh messages:", err);
        } finally {
          setIsRefreshingThreadMessages(false);
        }

        // Refresh thread metadata to catch title updates that arrived after SSE closed
        try {
          const res = await fetch(`${API_URL}/api/threads/${tid}?include_messages=false`, {
            credentials: "include",
          });
          if (res.ok) {
            const data = await res.json();
            const newTitle = data?.title?.trim();
            if (newTitle && newTitle !== PLACEHOLDER_CHAT_TITLE) {
              setThreads(prev => prev.map(t =>
                t.id === tid && (t.title === PLACEHOLDER_CHAT_TITLE || !t.title?.trim())
                  ? { ...t, title: newTitle }
                  : t
              ));
              if (awaitingGeneratedTitleForId === tid) {
                beginTitleReveal(tid, newTitle);
              }
            }
          }
        } catch {
          // Title refresh is best-effort
        }
      },
      onThreadTitle: handleStreamThreadTitle,
    }
  );

  const restartThreadStream = useCallback(() => {
    disconnectThreadStream();
    clearThreadStream();
    setTimeout(() => {
      connectThreadStream();
    }, 0);
  }, [clearThreadStream, connectThreadStream, disconnectThreadStream]);
  const [isPrimingThreadRun, setIsPrimingThreadRun] = useState(false);

  useEffect(() => {
    if (threadHasActiveRun || isRefreshingThreadMessages) {
      setIsPrimingThreadRun(false);
    }
  }, [isRefreshingThreadMessages, threadHasActiveRun]);

  const prevSelectedThreadIdRef = useRef(selectedThreadId);
  useEffect(() => {
    const prev = prevSelectedThreadIdRef.current;
    prevSelectedThreadIdRef.current = selectedThreadId;
    // Clear priming when navigating away, but not when switching
    // from "new"/provisional to a real thread ID (just-created thread).
    if (prev !== "new" && !prev?.startsWith("provisional-")) {
      setIsPrimingThreadRun(false);
    }
  }, [selectedThreadId]);

  // Only poll pending-actions while the agent is actively running
  useEffect(() => {
    if (!selectedThreadId || selectedThreadId === "0" || selectedThreadId === "new" || !isAuthenticated) {
      setPendingApprovals([]);
      return;
    }
    if (!threadHasActiveRun && !isThreadStreaming) {
      setPendingApprovals([]);
      return;
    }

    let cancelled = false;
    const loadPendingApprovals = async () => {
      try {
        const response = await fetch(`${API_URL}/api/threads/${selectedThreadId}/pending-actions`, {
          credentials: "include",
        });
        if (!response.ok) return;
        const data = await response.json();
        if (!cancelled) {
          setPendingApprovals(Array.isArray(data.pending) ? data.pending : []);
        }
      } catch {
        if (!cancelled) {
          setPendingApprovals([]);
        }
      }
    };

    void loadPendingApprovals();
    const interval = setInterval(loadPendingApprovals, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [selectedThreadId, isAuthenticated, threadHasActiveRun, isThreadStreaming]);

  // Use appropriate stream based on whether we're analyzing
  const isStreaming = isViewingAnalysisThread ? isProjectStreamConnected && !isProjectStreamComplete : isThreadStreaming;

  // Fetch messages from API when a thread is selected
  useEffect(() => {
    if (!selectedThreadId) return;
    if (selectedThreadId === "0" || selectedThreadId === "new" || selectedThreadId === "analyzing") return;
    if (isGuestThreadId(selectedThreadId)) return;
    
    // Skip during analysis transition - onComplete handles fetching
    if (isViewingAnalysisThread || analysisJustCompleted) return;
    
    // Skip if we already have messages for this thread
    if (threadMessages[selectedThreadId]?.length > 0) return;

    // Authenticated users: fetch from API
    if (!user) return;

    let cancelled = false;
    const fetchMessages = async () => {
      try {
        const response = await fetch(`${API_URL}/api/threads/${selectedThreadId}/messages`, {
          credentials: "include",
        });
        
        if (cancelled) return;
        if (response.ok) {
          const data = await response.json();
          const apiMessages = mapApiMessages(data.messages || []);

          setThreadMessages(prev => ({
            ...prev,
            [selectedThreadId]: apiMessages.length > 0 ? apiMessages : [],
          }));
        }
      } catch (err) {
        if (!cancelled) console.error("Failed to fetch messages:", err);
      }
    };

    fetchMessages();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedThreadId, user, isAuthenticated, isAnalyzing, analysisJustCompleted, mapApiMessages]);

  // Extract displayable text from event content that may be a string, array, or structured object
  const extractEventText = (content: unknown): string => {
    if (!content) return "";
    if (typeof content === "string") return content;
    if (Array.isArray(content)) {
      return content
        .map((block: unknown) => typeof block === "string" ? block : ((block as { text?: string }).text || ""))
        .join(" ");
    }
    if (typeof content === "object") {
      const obj = content as Record<string, unknown>;
      if (typeof obj.description === "string") return obj.description;
      if (typeof obj.message === "string") return obj.message;
      if (typeof obj.text === "string") return obj.text;
      if (obj.content && typeof obj.content === "string") return obj.content;
      if (obj.result && typeof obj.result === "string") return typeof obj.tool === "string" ? `${obj.tool}: ${obj.result}` : obj.result;
      if (typeof obj.tool === "string") return obj.tool;
      return JSON.stringify(content);
    }
    return String(content);
  };

  const isPromptLeakText = (text: string): boolean => {
    const normalized = text.trim().toLowerCase();
    return [
      "you are an expert coding assistant",
      "you are operating inside a persistent workspace",
      "the user should feel like they are talking to a capable coding partner",
      "the same conversation may continue across multiple turns",
      "latest user message:",
      "thread/runtime context",
      "workspace metadata:",
      "user workspace root:",
      "control repo root:",
      "runtime context file:",
      "operating rules",
      "do not echo this prompt",
      "final response:",
      "reminder: you must include the sources",
      "cite relevant sources inline as markdown",
      "links: [{",
      "web search results for query:",
    ].some((snippet) => normalized.includes(snippet));
  };

  const isGenericSuccessText = (text: string): boolean => {
    const normalized = text.trim();
    return /^(completed|finished|success)$/i.test(normalized);
  };

  /**
   * Format a single stored event into a human-readable line for the activity view.
   * Returns null to skip the event entirely.
   * Designed for a clean, summary-level view -- not a command log.
   */
  const formatStoredEvent = (e: StoredEvent): WorklogEntry | WorklogEntry[] | null => {
    const type = e.type;
    if (type === "thread_title") return null;
    const c = e.content;
    const meta = e.metadata || {};
    const cObj = c as Record<string, unknown>;
    const toolName = (meta?.tool || cObj?.tool || "") as string;
    const useId = (meta?.tool_use_id as string) || undefined;
    const actionNote = (_label: string, text: string) => wAction(text);
    const shouldHideProgress = (text: string) => {
      const normalized = text.trim();
      return [
        /^task queued$/i,
        /^mode:/i,
        /^workspace:/i,
        /^installing gcloud cli/i,
        /^gcloud installed:/i,
        /^installing jq/i,
        /^injecting gcp credentials/i,
        /^gcp auth ok:/i,
        /^symlinking gcloud/i,
        /^gcloud on path:/i,
        /^bootstrap complete/i,
        /^primary task:?$/i,
        /^inside the target workspace/i,
        /^you are operating inside a persistent workspace/i,
        /^the user should feel like they are talking to a capable coding partner/i,
        /^the same conversation may continue across multiple turns/i,
        /^latest user message:?$/i,
        /^thread\/runtime context:?$/i,
        /^operating rules:?$/i,
        /REMINDER:\s*You MUST include the sources/i,
        /cite relevant sources inline as markdown/i,
        /Links:\s*\[\s*\{/,
        /Web search results for query:/i,
        /^loading tools/i,
        /^loading skills/i,
        /^loaded \d+ commands/i,
        /^provider:/i,
        /^profile:/i,
        /^\d+ tools:/i,
        /^\d+ commands:/i,
        /^maxTurns:/i,
        /^search_env /i,
        /^submitting prompt/i,
        /^\[init\]$/,
        /^\[headless\]/i,
        /^Launching skill:/i,
        /^attempt=\d+\/\d+\s+wait=/i,
        /^\[api_retry\]/i,
        /^registered skills dir:/i,
        /^connecting to \d+ MCP/i,
        /^MCP: \d+ connected/i,
        /^Skill: /i,
        /^submitting:/i,
      ].some((pattern) => pattern.test(normalized));
    };
    const shouldHideToolResult = (text: string) => {
      const normalized = text.trim();
      return [
        /^updated task #/i,
        /^task #\S+ created successfully:/i,
        /^tool loaded\. you can now use the tool\./i,
        /^you can now use the tool\./i,
        /^\{"type":"tool_reference"/i,
        /^\{[\s\S]*"project_id":/i,
        /^no tasks found$/i,
        /^file created successfully at:/i,
        /^file updated successfully/i,
        /^Web search results for query:/i,
        /^Links:\s*\[\s*\{/,
        /REMINDER:\s*You MUST include the sources/i,
        /^\[tool_result\]/i,
        /^\[tool_error\]/i,
        /^Launching skill:/i,
        /^Exit code \d+$/i,
      ].some((pattern) => pattern.test(normalized));
    };

    if (type === "message") {
      const text = normalizeContent(c);
      if (!text) return null;
      return { kind: "response" as const, text };
    }

    if (type === "thinking" || type === "thought") {
      const text = normalizeContent(c);
      if (!text || text === "Thinking..." || text === "Thinking\u2026") return null;
      const durationMs = typeof meta?.duration_ms === "number" ? meta.duration_ms : undefined;
      return { kind: "thinking" as const, text, durationMs };
    }

    if (type === "progress") {
      const text = normalizeContent(c);
      const prefix = (cObj?.current != null && cObj?.total != null) ? `[${cObj.current}/${cObj.total}] ` : "";
      const fullText = `${prefix}${text}`.trim();
      if (!fullText || shouldHideProgress(fullText) || isPromptLeakText(fullText)) return null;
      if (/^\w+\([\{"]/.test(fullText)) return null;
      if (/^\w+\(["']/.test(fullText)) return null;
      return actionNote("Status", fullText);
    }

    if (type === "browser_action") {
      const ba = typeof c === "object" && c ? c as Record<string, unknown> : {};
      const label = typeof ba.label === "string" ? ba.label : String(ba.action || "browser");
      const status = typeof ba.status === "string" ? ba.status : "";
      const pageTitle = typeof ba.page_title === "string" ? ba.page_title : "";
      const url = typeof ba.url === "string" ? ba.url : "";
      if (status === "started") {
        return wAction(label, "Browser", useId);
      }
      if (status === "completed") {
        const extra = pageTitle ? ` — ${pageTitle}` : url ? ` — ${url}` : "";
        return actionNote("Browser", `${label}${extra}`);
      }
      if (status === "error") {
        return actionNote("Browser", `Failed: ${label}`);
      }
      return null;
    }

    if (type === "tool_call") {
      const hiddenTools = ["Write", "Edit", "TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskStop", "ToolSearch"];
      if (hiddenTools.includes(toolName)) {
        return null;
      }
      if (toolName === "Bash" || toolName === "BashTool") {
        return null;
      }
      if (toolName.startsWith("mcp__playwright__")) {
        return null;
      }
      const args = (typeof cObj.arguments === "object" && cObj.arguments) ? cObj.arguments as Record<string, unknown> : {};
      const stripWorkspace = (s: string) => s.replace(/\/home\/user\/project-workspace\/?/g, "");
      const rawDesc = typeof cObj.description === "string" ? stripWorkspace(cObj.description.trim()) : "";
      if (rawDesc && !rawDesc.endsWith(" invoked")) {
        return wAction(rawDesc, toolName, useId);
      }
      if (toolName === "Read" || toolName === "FileRead") {
        const filePath = typeof args.file_path === "string" ? args.file_path : "";
        const shortPath = filePath ? stripWorkspace(filePath).replace(/\\/g, "/").split("/").slice(-3).join("/") : "";
        return wAction(`Read(\`${shortPath}\`)`, "Read", useId);
      }
      if (toolName === "Grep" || toolName === "GrepTool") {
        const pattern = typeof args.pattern === "string" ? args.pattern : "";
        return wAction(`Search(\`${pattern}\`)`, "Grep", useId);
      }
      if (toolName === "Glob" || toolName === "GlobTool") {
        const pattern = typeof args.pattern === "string" ? args.pattern : "";
        return wAction(`Find(\`${pattern}\`)`, "Glob", useId);
      }
      if (toolName === "WebSearch") {
        const query = typeof args.search_term === "string"
          ? args.search_term
          : typeof args.query === "string"
            ? args.query
            : "";
        return query ? wAction(`Web Search("${query}")`, "WebSearch", useId) : wAction("Web Search", "WebSearch", useId);
      }
      if (toolName === "WebFetch" && typeof args.url === "string") {
        return wAction(`Fetch(${args.url})`, "WebFetch", useId);
      }
      if (toolName === "Skill") {
        const skillName = typeof args.skill === "string" ? args.skill : "";
        return skillName ? wAction(`Activating **${skillName}**`, "Skill", useId) : null;
      }
      return toolName ? wAction(toolName, toolName, useId) : null;
    }

    if (type === "tool_result") {
      if (toolName === "Bash" || toolName === "ToolSearch") {
        return null;
      }
      if (toolName.startsWith("mcp__playwright__")) {
        return null;
      }
      if (toolName === "TodoWrite" || toolName === "TaskCreate" || toolName === "TaskUpdate" || toolName === "TaskList") {
        return null;
      }
      if (toolName === "Read" || toolName === "FileRead") {
        return null;
      }
      if (toolName === "Skill" || toolName === "agent") {
        return null;
      }
      if (toolName === "Grep" || toolName === "GrepTool") {
        const resultStr = typeof c === "string" ? c : typeof cObj?.result === "string" ? cObj.result : "";
        if (resultStr) {
          const matchCount = (resultStr.match(/\n/g) || []).length;
          const fileMatches = resultStr.match(/^[^\n:]+:/gm);
          const uniqueFiles = fileMatches ? new Set(fileMatches.map(m => m.replace(/:$/, ""))).size : 0;
          if (matchCount > 0) {
            return wResult(`${matchCount} match${matchCount !== 1 ? "es" : ""} in ${uniqueFiles} file${uniqueFiles !== 1 ? "s" : ""}`, "Grep", useId);
          }
        }
        return wResult("No matches", "Grep", useId);
      }
      if (toolName === "Glob" || toolName === "GlobTool") {
        const resultStr = typeof c === "string" ? c : typeof cObj?.result === "string" ? cObj.result : "";
        if (resultStr) {
          const files = resultStr.split("\n").filter(l => l.trim()).length;
          return wResult(`${files} file${files !== 1 ? "s" : ""} found`, "Glob", useId);
        }
        return wResult("No files found", "Glob", useId);
      }
      if (toolName === "WebSearch") {
        const resultStr = typeof c === "string" ? c : typeof cObj?.result === "string" ? cObj.result : "";
        const sourceCount = (resultStr.match(/^- \[/gm) || []).length;
        if (sourceCount > 0) {
          return wResult(`Found ${sourceCount} source${sourceCount !== 1 ? "s" : ""}`, "WebSearch", useId);
        }
        return null;
      }
      if (typeof c === "string") {
        if (shouldHideToolResult(c)) return null;
        return wResult(c, toolName, useId);
      }
      if (typeof c === "object" && c) {
        if (cObj.error) return wResult(`✗ ${String(cObj.error)}`, toolName, useId);
        if (cObj.success === false) return wResult(`✗ ${cObj.tool || "Command"} failed`, toolName, useId);
        if (typeof cObj.result === "string" && cObj.result.trim()) {
          if (shouldHideToolResult(cObj.result)) return null;
          return wResult(cObj.result, toolName, useId);
        }
      }
      return null;
    }

    if (type === "file_read") {
      return null;
    }

    if (type === "file_create" || type === "file_write") {
      const filename = typeof c === "object" ? (cObj?.filename || cObj?.filepath) as string : meta?.filename as string;
      const fileContent = typeof c === "object" && typeof cObj?.content === "string" ? cObj.content : null;
      if (filename) {
        const normalizedPath = filename.replace(/\\/g, '/');
        const shortPath = normalizedPath.split('/').slice(-3).join('/');
        const relPath = normalizedPath.replace(/^\/home\/user\/project-workspace\/?/, "");
        if (fileContent) {
          const contentLines = fileContent.split('\n');
          const displayLines = contentLines.slice(0, 30);
          const diffContent = displayLines.map((l: string) => `+${l}`).join('\n');
          const truncation = contentLines.length > 30 ? `\n+... ${contentLines.length - 30} more lines` : '';
          return [
            wAction(`Write(\`${shortPath}\`)`, "Write", undefined, relPath),
            wBlock(`\`\`\`diff\n--- /dev/null\n+++ b/${shortPath}\n${diffContent}${truncation}\n\`\`\``),
          ];
        }
        return wAction(`Write(\`${shortPath}\`)`, "Write", undefined, relPath);
      }
      return null;
    }

    if (type === "code_diff") {
      const filename = (typeof c === "object" ? cObj?.filename : meta?.filename || "") as string;
      const desc = (typeof c === "object" ? cObj?.description : "") as string;
      const oldContent = (typeof c === "object" ? cObj?.old : "") as string;
      const newContent = (typeof c === "object" ? cObj?.new : "") as string;
      const normalizedPath = (filename || "").replace(/\\/g, '/');
      const shortPath = normalizedPath.split('/').slice(-3).join('/');
      const relPath = normalizedPath.replace(/^\/home\/user\/project-workspace\/?/, "");
      let diffText = desc ? `${desc}\n\n` : "";
      const removedLines = (oldContent || "").split("\n").map((l: string) => `-${l}`).join("\n");
      const addedLines = (newContent || "").split("\n").map((l: string) => `+${l}`).join("\n");
      diffText += `\`\`\`diff\n--- a/${shortPath}\n+++ b/${shortPath}\n${removedLines}\n${addedLines}\n\`\`\``;
      return [
        wAction(`Edit(\`${shortPath}\`)`, "Edit", undefined, relPath),
        wBlock(diffText),
      ];
    }

    if (type === "cli_command") {
      const command = typeof c === "object" ? (cObj?.command as string) : "";
      const workingDir = typeof c === "object" ? (cObj?.working_dir as string) : "";
      const output = typeof c === "object" ? (cObj?.output as string) : "";
      const stripWs = (s: string) => s.replace(/\/home\/user\/project-workspace\/?/g, "");
      const cleanOutput = output ? stripWs(output.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim()) : "";
      const cleanCommand = command ? stripWs(command) : "";
      if (!cleanCommand && !cleanOutput) return null;
      if (cleanOutput.startsWith("{") && cleanOutput.includes('"project_id"')) return null;
      if (/^updated task #/i.test(cleanOutput)) return null;
      const lines = cleanOutput ? cleanOutput.split("\n") : [];
      const displayLines = lines.length > 20 ? [...lines.slice(0, 8), `... ${lines.length - 12} more lines ...`, ...lines.slice(-4)] : lines;
      const truncated = displayLines.join("\n");
      let block = "```terminal\n";
      if (workingDir) block += `# ${stripWs(workingDir)}\n`;
      if (cleanCommand) block += `$ ${cleanCommand}\n`;
      if (truncated) block += `${truncated}\n`;
      block += "```";
      return wBlock(block);
    }
    if (type === "cli_output") {
      return null;
    }
    if (type === "cli_complete") {
      const exitCode = typeof c === "object" ? cObj?.exit_code : c;
      if (exitCode !== 0 && exitCode != null) return wResult(`✗ Command failed (exit code ${exitCode})`);
      return null;
    }
    if (type === "command_run") {
      const cmd = (typeof c === "object" ? (cObj?.command as string) : (c as string)) || (meta?.command as string) || "";
      if (!cmd) return null;
      if (meta?.output) {
        return wResult(String(meta.output));
      }
      return wAction(`Bash(${cmd})`);
    }

    // --- Resource events ---
    if (type === "resource_create" || type === "resource_creating") {
      const rt = typeof c === "object" ? cObj?.resource_type : meta?.resource_type;
      const name = typeof c === "object" ? cObj?.name : meta?.name;
      return rt ? actionNote("Resource", `Creating ${rt}: ${name}`) : null;
    }
    if (type === "resource_verify" || type === "resource_verified") {
      const rt = typeof c === "object" ? cObj?.resource_type : meta?.resource_type;
      const name = typeof c === "object" ? cObj?.name : meta?.name;
      return rt ? actionNote("Resource", `${rt}: ${name}`) : null;
    }

    // --- Phase events: show phase name and brief description ---
    if (type === "phase") {
      const name = (typeof c === "object" ? cObj?.name : c || "") as string;
      const desc = (typeof c === "object" ? cObj?.description : "") as string;
      if (!name && !desc) return null;
      // Truncate description to first line to avoid wall of text
      const firstLine = desc ? desc.split('\n')[0] : "";
      return firstLine ? actionNote("Phase", `${name}: ${firstLine}`) : actionNote("Phase", name);
    }

    // --- Status events ---
    if (type === "success") {
      const msg = typeof c === "string" ? c : ((cObj?.message || "Completed") as string);
      if (!msg || isGenericSuccessText(msg)) return null;
      return wResult(`✓ ${msg}`);
    }
    if (type === "failure" || type === "error") {
      const msg = typeof c === "string" ? c : ((cObj?.error || cObj?.message || "Failed") as string);
      return wResult(`✗ ${msg}`);
    }

    const text = extractEventText(c);
    if (!text) return null;
    if (text.startsWith("{") || text.startsWith("[")) return null;
    if (text.split("\n").length > 4) return null;
    if (text.length > 300) return null;
    return wNarration(text);
  };

  const mergeCliEvents = (events: StoredEvent[]): StoredEvent[] => {
    const mergedEvents: StoredEvent[] = [];
    let i = 0;

    while (i < events.length) {
      const ev = events[i];
      if (!ev) break;

      if (ev.type === "thinking" || ev.type === "thought") {
        let text = normalizeContent(ev.content);
        const startMs = ev.timestamp ? new Date(ev.timestamp).getTime() : Date.now();
        let endMs = startMs;
        i++;
        while (i < events.length) {
          const next = events[i];
          if (next && (next.type === "thinking" || next.type === "thought")) {
            const nextText = normalizeContent(next.content);
            if (nextText && nextText !== "Thinking..." && nextText !== "Thinking\u2026") {
              text = nextText;
            }
            if (next.timestamp) endMs = new Date(next.timestamp).getTime();
            i++;
            continue;
          }
          if (next?.timestamp) endMs = new Date(next.timestamp).getTime();
          break;
        }
        const isTrailingThinking = i >= events.length;
        if (!isTrailingThinking && text && text !== "Thinking..." && text !== "Thinking\u2026") {
          mergedEvents.push({
            ...ev,
            type: "thinking" as StoredEvent["type"],
            content: text,
            metadata: { ...ev.metadata, duration_ms: endMs - startMs },
          });
        }
        continue;
      }

      if (ev.type === "browser_action") {
        const ba = typeof ev.content === "object" && ev.content ? ev.content as Record<string, unknown> : {};
        if (ba.status === "started") {
          const next = events[i + 1];
          if (next?.type === "tool_call") { i++; }
          const afterTool = events[i + 1];
          if (afterTool?.type === "tool_result") { i++; }
          const completion = events[i + 1];
          if (completion?.type === "browser_action") {
            const cba = typeof completion.content === "object" && completion.content ? completion.content as Record<string, unknown> : {};
            if (cba.status === "completed" || cba.status === "error") {
              i++;
              mergedEvents.push({ ...completion });
              i++;
              continue;
            }
          }
        }
        mergedEvents.push(ev);
        i++;
        continue;
      }

      if (ev.type === "tool_call") {
        const evContent = typeof ev.content === "object" && ev.content ? ev.content as Record<string, unknown> : {};
        const evTool = (ev.metadata?.tool || evContent.tool || "") as string;
        if (evTool.startsWith("mcp__playwright__")) {
          i++;
          continue;
        }
        if (evTool === "Bash" || evTool === "BashTool") {
          const next = events[i + 1];
          if (next && next.type === "cli_command") {
            i++;
            continue;
          }
        }
      }

      if (ev.type === "cli_command") {
        const content: Record<string, unknown> = (typeof ev.content === "object" && ev.content)
          ? { ...(ev.content as Record<string, unknown>) }
          : { command: ev.content };
        let output = typeof content.output === "string" ? content.output : "";
        let exitCode = content.exit_code as number | null | undefined;
        i++;

        while (i < events.length) {
          const next = events[i];
          if (!next) break;

          if (next.type === "cli_output") {
            const nextContent = typeof next.content === "object" && next.content
              ? next.content as Record<string, unknown>
              : { output: next.content };
            if (typeof nextContent.output === "string") {
              output += nextContent.output;
            }
            i++;
            continue;
          }

          if (next.type === "tool_result" || next.type === "todo_update") {
            i++;
            continue;
          }

          if (next.type === "cli_complete") {
            const nextContent = typeof next.content === "object" && next.content
              ? next.content as Record<string, unknown>
              : {};
            const stdout = typeof nextContent.stdout === "string" ? nextContent.stdout : "";
            if (typeof nextContent.exit_code === "number") {
              exitCode = nextContent.exit_code;
            }
            if (stdout && !/^updated task #/i.test(stdout.trim())) {
              output = stdout;
            }
            i++;
            continue;
          }

          break;
        }

        mergedEvents.push({
          ...ev,
          content: {
            ...content,
            output,
            exit_code: exitCode,
          },
        });
        continue;
      }

      if (ev.type === "message") {
        let text = typeof ev.content === "string" ? ev.content : "";
        i++;
        while (i < events.length && events[i]?.type === "message") {
          const next = events[i]!;
          text += typeof next.content === "string" ? next.content : "";
          i++;
        }
        if (text.trim()) {
          mergedEvents.push({ ...ev, content: text });
        }
        continue;
      }

      if (ev.type !== "cli_output" && ev.type !== "cli_complete" && ev.type !== "todo_update") {
        mergedEvents.push(ev);
      }
      i++;
    }

    return mergedEvents;
  };

  // Helper to parse tool_calls JSON into activities (if available)
  // This reconstructs the tasks view from saved database data
  const parseToolCallsToActivities = (toolCallsJson: string | object): Activity[] | undefined => {
    try {
      // Handle both string (from DB) and already-parsed object
      const toolCalls = typeof toolCallsJson === 'string' 
        ? JSON.parse(toolCallsJson) 
        : toolCallsJson;
      
      if (!Array.isArray(toolCalls) || toolCalls.length === 0) return undefined;

      return toolCalls.map((tc: ToolCall, idx: number) => {
        let content = "";
        if (tc.events && Array.isArray(tc.events)) {
          const mergedEvents = mergeCliEvents(tc.events as StoredEvent[]);

          content = mergedEvents
            .flatMap((e: StoredEvent) => {
              const result = formatStoredEvent(e);
              if (!result) return [];
              return Array.isArray(result) ? result : [result];
            })
            .map((entry) => entry.text)
            .join("\n\n");
        }

        return {
          id: `activity-${idx}`,
          title: tc.name || "Task",
          status: (tc.status || "completed") as Activity["status"],
          content: content || undefined,
        };
      });
    } catch (err) {
      console.error("Failed to parse tool_calls:", err);
      return undefined;
    }
  };

  const parseToolCallsToWorklog = (toolCallsJson: string | object): WorklogEntry[] | undefined => {
    try {
      const toolCalls = typeof toolCallsJson === "string"
        ? JSON.parse(toolCallsJson)
        : toolCallsJson;

      if (!Array.isArray(toolCalls) || toolCalls.length === 0) return undefined;

      const mergedEvents = (toolCalls as ToolCall[]).flatMap((tc) => mergeCliEvents((tc.events || []) as StoredEvent[]));

      const entries = mergedEvents
        .flatMap((event) => {
          const result = formatStoredEvent(event);
          if (!result) return [];
          return Array.isArray(result) ? result : [result];
        });

      return entries.length > 0 ? entries : undefined;
    } catch (err) {
      console.error("Failed to parse worklog tool_calls:", err);
      return undefined;
    }
  };

  const parseToolCallsToTodos = (toolCallsJson: string | object): RuntimeTodo[] | undefined => {
    try {
      const toolCalls = typeof toolCallsJson === "string"
        ? JSON.parse(toolCallsJson)
        : toolCallsJson;

      if (!Array.isArray(toolCalls)) return undefined;

      let latestTodos: RuntimeTodo[] | undefined;
      for (const toolCall of toolCalls as ToolCall[]) {
        for (const event of toolCall.events || []) {
          if (event.type !== "todo_update") continue;
          const rawTodos = typeof event.content === "object" && event.content
            ? (event.content as { todos?: unknown[] }).todos
            : undefined;
          if (!Array.isArray(rawTodos)) continue;
          latestTodos = rawTodos
            .map((todo: unknown) => {
              if (!todo || typeof todo !== "object") return null;
              const item = todo as Record<string, unknown>;
              const id = String(item.id || "").trim();
              const content = String(item.content || item.subject || "").trim();
              const status = String(item.status || "pending").trim() as RuntimeTodo["status"];
              if (!id || !content) return null;
              return {
                id,
                content,
                status: status === "in_progress" || status === "completed" || status === "failed" || status === "cancelled"
                  ? status
                  : "pending",
              };
            })
            .filter((todo): todo is RuntimeTodo => !!todo);
        }
      }

      return latestTodos;
    } catch (err) {
      console.error("Failed to parse todo tool_calls:", err);
      return undefined;
    }
  };

  const getPreferredTodos = (message: RawMessage): RuntimeTodo[] | undefined => {
    if (Array.isArray(message.todos)) {
      return message.todos;
    }
    if (message.tool_calls) {
      return parseToolCallsToTodos(message.tool_calls);
    }
    return undefined;
  };

  const getPreferredActivities = (message: RawMessage): Activity[] | undefined => {
    if (message.activities && typeof message.activities !== "string") {
      return message.activities;
    }
    if (message.tool_calls) {
      return parseToolCallsToActivities(message.tool_calls);
    }
    return undefined;
  };

  const getPreferredWorklog = (message: RawMessage): WorklogEntry[] | undefined => {
    if (message.tool_calls) {
      return parseToolCallsToWorklog(message.tool_calls);
    }
    return undefined;
  };

  const threadStreamWorklog = mergeCliEvents(
    threadStreamEvents
      .filter((event) => !["task_started", "task_progress", "task_completed", "task_failed", "todo_update", "complete", "thread_title"].includes(event.type)) as unknown as StoredEvent[]
  ).flatMap((event) => {
      const result = formatStoredEvent(event);
      if (!result) return [];
      return Array.isArray(result) ? result : [result];
    });

  const threadStreamContent = threadStreamEvents
    .filter((event) => event.type === "message")
    .map((event) => typeof event.content === "string" ? event.content : "")
    .join("")
    .trim();

  // Sort threads - closed always at bottom, then by date
  const sortedThreads = [...threads].sort((a, b) => {
    // First sort by status - closed threads go to bottom
    if (a.status === "closed" && b.status !== "closed") return 1;
    if (a.status !== "closed" && b.status === "closed") return -1;

    // Within same status group, sort by thread number
    const aNum = a.threadNumber || 0;
    const bNum = b.threadNumber || 0;
    return sortBy === "newest" ? bNum - aNum : aNum - bNum;
  });

  // Pagination constants
  const ITEMS_PER_PAGE = 10;
  const totalPages = Math.ceil(sortedThreads.length / ITEMS_PER_PAGE);
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const endIndex = startIndex + ITEMS_PER_PAGE;
  const paginatedThreads = sortedThreads.slice(startIndex, endIndex);

  // Get first name from display_name
  const firstName = user?.display_name?.split(' ')[0];

  // Get status colors
  const getStatusColors = (status: Thread["status"]) => {
    switch (status) {
      case "open":
        return {
          icon: "text-primary",
          badge: "bg-primary/10 text-primary",
          label: "open",
        };
      case "in_progress":
        return {
          icon: "text-pink-400",
          badge: "bg-pink-400/10 text-pink-500 dark:text-pink-300",
          label: "working",
        };
      case "closed":
        return {
          icon: "text-[var(--text-secondary)]",
          badge: "bg-[var(--bg-tertiary)] text-[var(--text-secondary)]",
          label: "closed",
        };
      default:
        return {
          icon: "text-[var(--text-secondary)]",
          badge: "bg-[var(--bg-tertiary)] text-[var(--text-secondary)]",
          label: status || "unknown",
        };
    }
  };

  // Auto-grow comment textarea
  useLayoutEffect(() => {
    const el = commentTextareaRef.current;
    if (!el) return;
    const maxHeight = typeof window !== "undefined" ? window.innerHeight * 0.4 : 350;
    el.style.height = "auto";
    const scrollHeight = el.scrollHeight;
    const newHeight = Math.min(scrollHeight, maxHeight);
    el.style.height = `${newHeight}px`;
    el.style.overflowY = scrollHeight > maxHeight ? "auto" : "hidden";
  }, [commentInput]);

  const handleClarificationSelect = (option: string) => {
    console.log("Selected:", option);
  };

  const openThread = (threadId: string) => {
    setSelectedThreadId(threadId);
    setView("detail");
  };

  const goBackToThreads = () => {
    setView("threads");
    setSelectedThreadId(null);
    setCommentInput("");
  };

  const createNewThread = () => {
    // Create a new blank thread
    setSelectedThreadId("new");
    setView("detail");
    setCommentInput("");
  };

  const handleCloseThread = async () => {
    if (!selectedThreadId || selectedThreadId === "new") return;

    try {
      const response = await fetch(`${API_URL}/api/threads/${selectedThreadId}`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ status: "closed" }),
      });
      if (!response.ok) {
        throw new Error("Failed to close thread");
      }

      setThreads(prev => prev.map(thread =>
        thread.id === selectedThreadId
          ? { ...thread, status: "closed" as const }
          : thread
      ));

      setShowCloseDialog(false);
      goBackToThreads();
    } catch (error) {
      console.error("Failed to close thread:", error);
    }
  };

  const handleReopenThread = async () => {
    if (!selectedThreadId || selectedThreadId === "new") return;

    try {
      const response = await fetch(`${API_URL}/api/threads/${selectedThreadId}`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ status: "open" }),
      });
      if (!response.ok) {
        throw new Error("Failed to reopen thread");
      }

      setThreads(prev => prev.map(thread =>
        thread.id === selectedThreadId
          ? { ...thread, status: "open" as const }
          : thread
      ));

      setShowReopenDialog(false);
    } catch (error) {
      console.error("Failed to reopen thread:", error);
    }
  };

  const performDeleteThread = async () => {
    if (threadDeleteDialog.type !== "confirm") return;
    const { id: deletedId } = threadDeleteDialog;
    setIsDeletingThread(true);
    try {
      const response = await fetch(`${API_URL}/api/threads/${deletedId}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error("Failed to delete thread");
      }

      setThreads((prev) => prev.filter((t) => t.id !== deletedId));
      setThreadMessages((prev) => {
        const next = { ...prev };
        delete next[deletedId];
        return next;
      });
      setAwaitingGeneratedTitleForId((tid) => (tid === deletedId ? null : tid));
      if (pendingTitleContextRef.current?.threadId === deletedId) {
        pendingTitleContextRef.current = null;
      }

      if (selectedThreadId === deletedId) {
        goBackToThreads();
      } else if (initialThreadId === deletedId) {
        setSelectedThreadId(null);
      }

      setThreadDeleteDialog({ type: "idle" });
    } catch (error) {
      console.error("Failed to delete thread:", error);
    } finally {
      setIsDeletingThread(false);
    }
  };

  const threadDeleteAlertDialog = (
    <AlertDialog
      open={threadDeleteDialog.type === "confirm"}
      onOpenChange={(open) => {
        if (!open && !isDeletingThread) setThreadDeleteDialog({ type: "idle" });
      }}
    >
      <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-base text-[var(--text-primary)]">
            {threadDeleteDialog.type === "confirm"
              ? `Delete "${threadDeleteDialog.title}"?`
              : ""}
          </AlertDialogTitle>
          <AlertDialogDescription className="text-sm text-[var(--text-secondary)] leading-relaxed">
            This permanently removes the thread and its messages. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeletingThread}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={isDeletingThread}
            className="bg-red-500 hover:bg-red-600 text-white focus:ring-red-500 sm:mt-0"
            onClick={(e) => {
              e.preventDefault();
              void performDeleteThread();
            }}
          >
            {isDeletingThread ? "Deleting…" : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      setAttachedFiles(prev => [...prev, ...files]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      setAttachedFiles(prev => [...prev, ...files]);
    }
  };

  const removeFile = (index: number) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleSendMessage = async () => {
    if (!commentInput.trim()) return;

    const prompt = commentInput;

    // Signed-out: mock ChatGPT-style naming (local only; no backend).
    if (!isAuthenticated && selectedThreadId === "new") {
      const threadId = `${GUEST_THREAD_ID_PREFIX}${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      const nextNumber =
        Math.max(0, ...threads.map((t) => t.threadNumber || 0), ...DEMO_THREADS.map((t) => t.threadNumber || 0)) + 1;
      const initialMessages: Message[] = [
        {
          id: `u-${Date.now()}`,
          author: "user",
          content: prompt,
          timestamp: "Just now",
        },
      ];
      const newThread: Thread = {
        id: threadId,
        threadNumber: nextNumber,
        title: PLACEHOLDER_CHAT_TITLE,
        status: "open",
        createdAt: "Just now",
        updatedAt: "Just now",
        messageCount: initialMessages.length,
        activityCount: 0,
        preview: prompt.substring(0, 100),
      };
      setThreads((prev) => [newThread, ...prev.filter((t) => t.id !== threadId)]);
      setThreadMessages((prev) => ({ ...prev, [threadId]: initialMessages }));
      setAwaitingGeneratedTitleForId(threadId);
      pendingTitleContextRef.current = { threadId, prompt };
      setSelectedThreadId(threadId);
      setView("detail");
      setCommentInput("");
      setAttachedFiles([]);
      const localName =
        deriveThreadTitleFromMessage(prompt) || "Untitled Thread";
      window.setTimeout(() => {
        setAwaitingGeneratedTitleForId((id) => (id === threadId ? null : id));
        beginTitleReveal(threadId, localName);
      }, 650);
      return;
    }

    // Signed-out: append to a local guest thread only (no agent run)
    if (!isAuthenticated && selectedThreadId && isGuestThreadId(selectedThreadId)) {
      const tid = selectedThreadId;
      const newMessage: Message = {
        id: `u-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        author: "user",
        content: prompt,
        timestamp: "Just now",
      };
      setThreadMessages((prev) => ({
        ...prev,
        [tid]: [...(prev[tid] || []), newMessage],
      }));
      setThreads((prev) =>
        prev.map((t) =>
          t.id === tid
            ? {
                ...t,
                messageCount: (t.messageCount || 0) + 1,
                preview: prompt.substring(0, 100),
                updatedAt: "Just now",
              }
            : t,
        ),
      );
      setCommentInput("");
      setAttachedFiles([]);
      return;
    }

    if (!project?.id || !isAuthenticated) return;
    const parseErrorDetail = async (response: Response) => {
      try {
        const data = await response.json();
        return data?.detail || data?.message || `Request failed with status ${response.status}`;
      } catch {
        return `Request failed with status ${response.status}`;
      }
    };

    const createRuntimeThread = async () => {
      const response = await fetch(`${API_URL}/api/threads`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: project.id,
          initial_message: prompt,
          start_agent: true,
          task_type: detectTaskType(prompt),
          task_mode: "local",
        }),
      });

      if (!response.ok) {
        throw new Error(await parseErrorDetail(response));
      }

      return response.json();
    };

    const continueRuntimeThread = async (threadId: string) => {
      const response = await fetch(`${API_URL}/api/threads/${threadId}/messages`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role: "user",
          content: prompt,
          task_type: detectTaskType(prompt),
          task_mode: "local",
          run_agent: true,
        }),
      });

      if (!response.ok) {
        throw { response, detail: await parseErrorDetail(response) };
      }

      return response.json();
    };

    if (selectedThreadId === "new") {
      // Show feedback immediately: create a provisional thread so the user
      // sees their message + "Thinking..." while the API call runs.
      const provisionalId = `provisional-${Date.now()}`;
      const initialMessages: Message[] = [
        { id: "msg-1", author: "user", content: prompt, timestamp: "Just now" },
      ];
      const provisionalThread: Thread = {
        id: provisionalId,
        threadNumber: 0,
        title: PLACEHOLDER_CHAT_TITLE,
        status: "open",
        createdAt: "Just now",
        updatedAt: "Just now",
        messageCount: 1,
        activityCount: 0,
        preview: prompt.substring(0, 100),
      };

      setThreads(prev => [provisionalThread, ...prev]);
      setThreadMessages(prev => ({ ...prev, [provisionalId]: initialMessages }));
      setIsPrimingThreadRun(true);
      setSelectedThreadId(provisionalId);
      setView("detail");
      setCommentInput("");
      setAttachedFiles([]);

      try {
        const threadResponse = await createRuntimeThread();
        const threadId = threadResponse.task?.thread_id || threadResponse.id;
        const threadNumber = threadResponse.task?.thread_number || threadResponse.thread_number || 0;

        // Swap provisional thread for real one
        setThreads(prev =>
          prev.map(t => t.id === provisionalId
            ? { ...t, id: threadId, threadNumber, title: threadResponse.title || PLACEHOLDER_CHAT_TITLE }
            : t
          )
        );
        setThreadMessages(prev => {
          const msgs = prev[provisionalId] || initialMessages;
          // eslint-disable-next-line @typescript-eslint/no-unused-vars
          const { [provisionalId]: _removed, ...rest } = prev;
          return { ...rest, [threadId]: msgs };
        });
        pendingTitleContextRef.current = { threadId, prompt };
        setAwaitingGeneratedTitleForId(threadId);
        setSelectedThreadId(threadId);

        window.dispatchEvent(new CustomEvent('threadCreated'));
      } catch (error) {
        // Revert the provisional thread
        setThreads(prev => prev.filter(t => t.id !== provisionalId));
        setThreadMessages(prev => {
          // eslint-disable-next-line @typescript-eslint/no-unused-vars
          const { [provisionalId]: _removed, ...rest } = prev;
          return rest;
        });
        setIsPrimingThreadRun(false);
        setSelectedThreadId("new");
        setCommentInput(prompt);
        console.error("Failed to start task:", error);
      }
    } else if (selectedThreadId) {
      const tid = selectedThreadId;
      const newMessage: Message = {
        id: `u-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        author: "user",
        content: prompt,
        timestamp: "Just now",
      };

      const revertOptimisticUserMessage = () => {
        setThreadMessages(prev => ({
          ...prev,
          [tid]: (prev[tid] || []).filter(m => m.id !== newMessage.id),
        }));
        setCommentInput(prompt);
      };

      try {
        // Show the user bubble in the thread immediately so "Thinking" appears below it,
        // not while the text still sits in the composer (network latency was ~multi-second).
        setThreadMessages(prev => ({
          ...prev,
          [tid]: [...(prev[tid] || []), newMessage],
        }));
        setCommentInput("");
        setAttachedFiles([]);

        try {
          setIsPrimingThreadRun(true);
          await continueRuntimeThread(tid);
          restartThreadStream();
        } catch (rawError) {
          setIsPrimingThreadRun(false);
          const response = rawError && typeof rawError === "object" && "response" in rawError
            ? (rawError as { response: Response }).response
            : null;
          const detail = rawError && typeof rawError === "object" && "detail" in rawError
            ? String((rawError as { detail: string }).detail)
            : "Request failed";
          if (response?.status === 404 && /thread not found/i.test(detail)) {
            setThreadMessages(prev => ({
              ...prev,
              [tid]: (prev[tid] || []).filter(m => m.id !== newMessage.id),
            }));
            try {
              const threadResponse = await createRuntimeThread();
              const threadId = threadResponse.task?.thread_id || threadResponse.id;
              const threadNumber = threadResponse.task?.thread_number || threadResponse.thread_number || 0;

              const fallbackMessages: Message[] = [newMessage];

              const newThread: Thread = {
                id: threadId,
                threadNumber,
                title: threadResponse.title || PLACEHOLDER_CHAT_TITLE,
                status: "open",
                createdAt: "Just now",
                updatedAt: "Just now",
                messageCount: fallbackMessages.length,
                activityCount: 0,
                preview: prompt.substring(0, 100),
              };

              setThreads(prev => [newThread, ...prev.filter(thread => thread.id !== newThread.id)]);
              setThreadMessages(prev => ({
                ...prev,
                [threadId]: fallbackMessages,
              }));
              pendingTitleContextRef.current = { threadId, prompt };
              setAwaitingGeneratedTitleForId(threadId);
              setSelectedThreadId(threadId);
              setView("detail");
              setAttachedFiles([]);
              setIsPrimingThreadRun(false);

              window.dispatchEvent(new CustomEvent('threadCreated'));
              return;
            } catch (createErr) {
              setCommentInput(prompt);
              throw createErr;
            }
          }
          revertOptimisticUserMessage();
          throw new Error(detail);
        }
      } catch (error) {
        setIsPrimingThreadRun(false);
        console.error("Failed to continue task:", error);
      }
    }
  };

  // Auto-scroll to bottom when messages change or agent starts thinking
  const currentMessageCount = selectedThreadId ? (threadMessages[selectedThreadId]?.length ?? 0) : 0;
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [currentMessageCount, isPrimingThreadRun]);

  // Render threads list view
  if (view === "threads") {
    return (
      <>
        <div className="flex flex-col h-full bg-[var(--bg-primary)]">
          {/* Header */}
          <div className="flex-shrink-0 border-b border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">Threads</h2>
              <Button
                onClick={createNewThread}
                className="h-7 px-3 text-[11px] bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                New Thread
              </Button>
            </div>
          </div>

          {/* Threads List */}
          <ScrollArea className="flex-1">
            <div className="divide-y divide-[var(--border-color)]">
              {paginatedThreads.map((thread) => {
                const statusColors = getStatusColors(thread.status);
                const showDeleteMenu = isAuthenticated && isPersistedBackendThreadId(thread.id);
                return (
                  <div
                    key={thread.id}
                    className="flex w-full items-stretch hover:bg-[var(--bg-secondary)] transition-colors"
                  >
                    <button
                      type="button"
                      onClick={() => openThread(thread.id)}
                      className="min-w-0 flex-1 px-4 py-3 text-left"
                    >
                      <div className="flex items-start gap-2 mb-1">
                        <h3 className="text-[13px] font-medium text-[var(--text-primary)] flex-1 break-words">
                          {thread.title}
                        </h3>
                        <span className={cn(
                          "px-1.5 py-0.5 text-[10px] rounded-full flex-shrink-0",
                          statusColors.badge
                        )}>
                          {statusColors.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)] flex-wrap">
                        <span className="flex-shrink-0">#{thread.threadNumber}</span>
                        <span className="flex-shrink-0">{thread.createdAt}</span>
                        {thread.branch && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0 rounded bg-primary/10 text-primary text-[10px] font-mono">
                            <GitBranch className="h-2.5 w-2.5" />
                            {thread.branch.replace(/^patchapi\//, "")}
                          </span>
                        )}
                      </div>
                    </button>
                    {showDeleteMenu && (
                      <div className="flex flex-shrink-0 items-center pr-2">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              type="button"
                              className="h-7 w-7 flex items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
                              aria-label="Thread actions"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <MoreVertical className="h-4 w-4" />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent
                            align="end"
                            className="w-48 bg-[var(--bg-primary)] border-[var(--border-color)]"
                          >
                            <DropdownMenuItem
                              className="flex items-center gap-2 p-2 cursor-pointer hover:bg-red-500/10 focus:bg-red-500/10"
                              onSelect={() =>
                                setThreadDeleteDialog({
                                  type: "confirm",
                                  id: thread.id,
                                  title: thread.title,
                                })
                              }
                            >
                              <Trash2 className="h-3.5 w-3.5 text-red-500" />
                              <span className="text-xs text-red-500">Delete thread</span>
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </ScrollArea>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex-shrink-0 border-t border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-2">
              <Pagination>
                <PaginationContent className="gap-0.5">
                  <PaginationItem>
                    <PaginationPrevious
                      onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                      className={cn(
                        "h-7 px-2 text-[11px] cursor-pointer bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)]",
                        "hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]",
                        currentPage === 1 && "pointer-events-none opacity-50"
                      )}
                    />
                  </PaginationItem>
                  {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                    <PaginationItem key={page}>
                      <PaginationLink
                        onClick={() => setCurrentPage(page)}
                        isActive={currentPage === page}
                        className={cn(
                          "h-7 w-7 text-[11px] cursor-pointer border",
                          currentPage === page
                            ? "bg-[var(--bg-tertiary)] border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                            : "bg-[var(--bg-primary)] border-transparent text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]"
                        )}
                      >
                        {page}
                      </PaginationLink>
                    </PaginationItem>
                  ))}
                  <PaginationItem>
                    <PaginationNext
                      onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                      className={cn(
                        "h-7 px-2 text-[11px] cursor-pointer bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)]",
                        "hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]",
                        currentPage === totalPages && "pointer-events-none opacity-50"
                      )}
                    />
                  </PaginationItem>
                </PaginationContent>
              </Pagination>
            </div>
          )}
        </div>

        {threadDeleteAlertDialog}
      </>
    );
  }

  // Render thread detail view
  const isNewThread = selectedThreadId === "new";

  // Get current thread data
  let currentThread = threads.find(t => t.id === selectedThreadId);

  /** Waiting for backend (or guest mock) to supply the real title — show gliding “New chat”. */
  const isAwaitingGeneratedTitle =
    !!currentThread &&
    awaitingGeneratedTitleForId === currentThread.id &&
    (currentThread.title === PLACEHOLDER_CHAT_TITLE ||
      !(currentThread.title && currentThread.title.trim()));

  const isTypewritingTitle =
    !!titleReveal &&
    !!currentThread &&
    titleReveal.threadId === currentThread.id;

  // Determine which messages to show
  // If it's a new thread, show empty messages (user will create first message)
  // If it's analyzing thread, show analyzing message with streaming activities
  // If it's a thread with stored messages, use those
  // Otherwise, use mock messages for existing mock threads
  const hasStoredMessages = selectedThreadId && threadMessages[selectedThreadId];
  
  // For analyzing thread, create message with streaming activities from project stream
  // Priority: 1) Live streaming (isAnalyzing), 2) Completed activities ref, 3) Thread stream tasks
  const analyzingActivities = isViewingAnalysisThread
    ? projectEventsToActivities(projectStreamEvents as AgentEvent[], isProjectStreamComplete)
    : analysisJustCompleted && completedActivitiesRef.current.length > 0
      ? completedActivitiesRef.current  // Use captured activities while fetching messages
      : threadStreamTasks.map(task => ({
          id: task.id,
          status: task.status === "waiting" ? "needs_input" as const : task.status,
          title: task.title,
          duration: task.duration,
          content: task.events.length > 0 ? formatTaskEvents(task.events) : undefined,
        }));

  const analyzingMessageWithStreaming: Message = {
    ...ANALYZING_MESSAGE,
    activities: analyzingActivities,
  };
  
  // Demo mode: convert demo tasks to activities format
  // Each task becomes one ActivityRow - displayed vertically one by one
  // Events stream below each task (same as real console)
  const isDemoThread = demo?.isDemo && (selectedThreadId?.startsWith("demo-") || selectedThreadId?.startsWith("live-"));
  
  // Format demo events similar to formatTaskEvents for real streaming
  // Use double newlines for actual line breaks in markdown
  const formatDemoTaskEvents = (events: Array<{ type: string; content: unknown; timestamp: string }>): string => {
    const lines: string[] = [];
    for (const event of events) {
      const text = extractEventText(event.content);
      if (event.type === "thought" || event.type === "thinking") {
        continue;
      } else if (event.type === "progress") {
        lines.push(text);
      } else if (event.type === "tool_result") {
        lines.push(`✓ ${text}`);
      }
    }
    return lines.join("\n\n");
  };
  
  const demoActivities: Activity[] = isDemoThread ? demo.tasks.map(task => {
    // Content shows ALL events below the task (streaming format)
    // - For in_progress: shows as events stream in
    // - For completed: shows when expanded
    const content = task.events.length > 0 
      ? formatDemoTaskEvents(task.events) 
      : undefined;
    
    return {
      id: task.id,
      status: task.status === "in_progress" ? "in_progress" as const 
            : task.status === "completed" ? "completed" as const 
            : "pending" as const,
      title: task.name,
      content,
    };
  }) : [];
  
  // For demo threads: show streaming message during stream, final summary when complete
  const getDemoMessageContent = () => {
    if (!demo?.currentThread) return "";
    
    const isAnalysis = demo.currentThread.type === "analysis";
    const isComplete = demo.currentThread.status === "completed";
    
    if (isAnalysis) {
      // Show summary when analysis is complete, otherwise show streaming message
      if (isComplete && demo.analysisSummary) {
        return demo.analysisSummary;
      }
      return "Analyzing your repository and designing the cloud architecture...";
    } else {
      // DevOps thread
      if (isComplete && demo.devopsSummary) {
        return demo.devopsSummary;
      }
      return "Generating backend code and preparing deployment...";
    }
  };
  
  const demoMessage: Message = isDemoThread ? {
    id: "msg-demo",
    author: "agent",
    content: getDemoMessageContent(),
    timestamp: "Just now",
    activities: demoActivities,
  } : ANALYZING_MESSAGE;
  
  // For real threads: use stored messages (fetched from API or locally created)
  // For mock demo threads (ids 1-20): use MOCK_MESSAGES for demo purposes only
  const isMockDemoThread = selectedThreadId && parseInt(selectedThreadId) >= 1 && parseInt(selectedThreadId) <= 20 && !project;
  const isMockGoogleSessionThread =
    selectedThreadId === MOCK_GOOGLE_TEST_SESSION_THREAD_ID && !project;
  const isMockSecretRequirementThread =
    selectedThreadId === MOCK_SECRET_REQUIREMENT_THREAD_ID && !project;
  const isMockGcpConnectionThread =
    selectedThreadId === MOCK_GCP_CONNECTION_THREAD_ID && !project;
  // Special case: thread "1" or "mock-analysis-1" shows the analysis demo (for unauthenticated users only)
  const isMockAnalysisThread = selectedThreadId === "1" || selectedThreadId === "mock-analysis-1";
  
  // When analyzing or just completed (fetching messages), show the analyzing message with activities
  // Otherwise, show stored messages or fall back appropriately
  const currentMessages = isNewThread 
    ? [] 
    : isDemoThread  // Demo mode threads
      ? [demoMessage]
      : (isViewingAnalysisThread || analysisJustCompleted)  // Keep showing during analysis AND while fetching messages
      ? [analyzingMessageWithStreaming]
      : hasStoredMessages 
        ? threadMessages[selectedThreadId] 
        : isMockGoogleSessionThread
          ? mockGoogleSessionMessages
          : isMockSecretRequirementThread
            ? MOCK_SECRET_REQUIREMENT_MESSAGES
            : isMockGcpConnectionThread
              ? MOCK_GCP_CONNECTION_MESSAGES
          : isMockAnalysisThread && !project
          ? [MOCK_ANALYSIS_MESSAGE]  // Thread #1 shows generic analysis demo for unauthenticated users
          : isMockDemoThread 
            ? MOCK_MESSAGES  // Other mock threads show deployment demo
            : [];  // Real threads show empty until messages are loaded

  const shouldShowPendingAssistantMessage =
    !isNewThread &&
    !isViewingAnalysisThread &&
    !analysisJustCompleted &&
    !isDemoThread &&
    (
      isPrimingThreadRun ||
      (
        (threadHasActiveRun || isRefreshingThreadMessages) &&
        (!currentMessages.length || currentMessages[currentMessages.length - 1]?.author !== "agent")
      )
    );

  const pendingAssistantMessage: Message | null = shouldShowPendingAssistantMessage
    ? {
        id: `streaming-agent-${selectedThreadId || "thread"}`,
        author: "agent",
        content: "",
        timestamp: "Just now",
      }
    : null;

  const renderedMessages = pendingAssistantMessage
    ? [...currentMessages, pendingAssistantMessage]
    : currentMessages;

  const liveAssistantMessageId = (isPrimingThreadRun || threadHasActiveRun || isRefreshingThreadMessages)
    ? (
        pendingAssistantMessage?.id ||
        [...renderedMessages].reverse().find((message) => message.author === "agent")?.id ||
        null
      )
    : null;

  return (
    <ThreadErrorBoundary onRetry={goBackToThreads}>
    <div className="flex flex-col h-full bg-[var(--bg-primary)] @container">
      {/* Header - Compact ticket style */}
      <div className="px-4 py-2 border-b border-[var(--border-color)]">
        <div className="flex items-center justify-between gap-2 mb-1">
          <button
            onClick={goBackToThreads}
            className="p-1 hover:bg-[var(--bg-secondary)] rounded transition-colors flex items-center gap-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span className="text-[11px]">Threads</span>
          </button>
          {!isNewThread &&
            currentThread &&
            currentThread.id !== "0" &&
            isAuthenticated &&
            !isGuestThreadId(currentThread.id) &&
            currentThread.status !== "closed" && (
            <Button
              onClick={() => setShowCloseDialog(true)}
              variant="outline"
              size="sm"
              className="h-7 px-3 text-[11px] border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]"
            >
              Close
            </Button>
          )}
          {!isNewThread &&
            currentThread &&
            currentThread.id !== "0" &&
            isAuthenticated &&
            !isGuestThreadId(currentThread.id) &&
            currentThread.status === "closed" && (
            <Button
              onClick={() => setShowReopenDialog(true)}
              variant="outline"
              size="sm"
              className="h-7 px-3 text-[11px] border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]"
            >
              Reopen
            </Button>
          )}
        </div>
        {!isNewThread && currentThread && (
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <h1 className="text-[14px] font-medium text-[var(--text-tertiary)] break-words flex-1 min-w-0 min-h-[1.25rem]">
                {isTypewritingTitle ? (
                  titleReveal.display
                ) : isAwaitingGeneratedTitle ? (
                  <span className="shimmer-text">{PLACEHOLDER_CHAT_TITLE}</span>
                ) : (
                  currentThread.title
                )}
              </h1>
              <span className="text-[12px] font-mono text-[var(--text-secondary)] flex-shrink-0">
                #{currentThread.threadNumber}
              </span>
              {isAuthenticated && isPersistedBackendThreadId(currentThread.id) && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="h-7 w-7 shrink-0 flex items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
                      aria-label="Thread actions"
                    >
                      <MoreVertical className="h-4 w-4" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="end"
                    className="w-48 bg-[var(--bg-primary)] border-[var(--border-color)]"
                  >
                    <DropdownMenuItem
                      className="flex items-center gap-2 p-2 cursor-pointer hover:bg-red-500/10 focus:bg-red-500/10"
                      onSelect={() =>
                        setThreadDeleteDialog({
                          type: "confirm",
                          id: currentThread.id,
                          title: currentThread.title,
                        })
                      }
                    >
                      <Trash2 className="h-3.5 w-3.5 text-red-500" />
                      <span className="text-xs text-red-500">Delete thread</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className={cn(
                "px-1.5 py-0.5 text-[10px] rounded-full flex-shrink-0",
                getStatusColors(currentThread.status).badge
              )}>
                {getStatusColors(currentThread.status).label}
              </span>
              <span className="text-[10px] text-[var(--text-secondary)]">
                opened {currentThread.createdAt}
              </span>
            </div>
          </div>
        )}
        {isNewThread && (
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <h1 className="text-[14px] font-medium text-[var(--text-tertiary)] break-words flex-1 min-w-0">
                {PLACEHOLDER_CHAT_TITLE}
              </h1>
              <span className="text-[12px] font-mono text-[var(--text-secondary)] flex-shrink-0">
                #new
              </span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={cn(
                  "px-1.5 py-0.5 text-[10px] rounded-full flex-shrink-0",
                  getStatusColors("open").badge,
                )}
              >
                {getStatusColors("open").label}
              </span>
              <span className="text-[10px] text-[var(--text-secondary)]">
                {isAuthenticated
                  ? "Send a message to start"
                  : "Local preview — sign in to save to your project"}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* NOTE: Removed StreamingIndicator here - Tasks in MessageBlock are sufficient */}

      {/* Chat Flow - Message-based */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-6">
          {renderedMessages.map((message) => (
            <MessageBlock
              key={message.id}
              message={message}
              onSelectClarification={handleClarificationSelect}
              userAvatar={user?.avatar_url}
              userName={firstName}
              streamActivities={message.id === liveAssistantMessageId ? (isViewingAnalysisThread ? undefined : isDemoThread ? undefined : threadStreamTasks) : undefined}
              streamTodos={message.id === liveAssistantMessageId ? (isViewingAnalysisThread ? undefined : isDemoThread ? undefined : threadStreamTodos) : undefined}
              streamWorklog={message.id === liveAssistantMessageId ? (isViewingAnalysisThread ? undefined : isDemoThread ? undefined : threadStreamWorklog) : undefined}
              streamContent={message.id === liveAssistantMessageId ? threadStreamContent : undefined}
              isStreaming={
                message.id === liveAssistantMessageId &&
                !message.content?.trim() &&
                (isPrimingThreadRun ||
                  threadHasActiveRun ||
                  isStreaming ||
                  isRefreshingThreadMessages ||
                  (demo?.isStreaming ?? false))
              }
              currentThought={message.id === liveAssistantMessageId && isThreadStreaming ? threadCurrentThought : null}
              activeTool={message.id === liveAssistantMessageId && isThreadStreaming ? threadActiveTool : null}
              waitingState={message.id === liveAssistantMessageId && isThreadStreaming ? threadWaitingState : null}
              isAnalyzingMessage={
                // Real analysis: show content above during analyzing
                ((isViewingAnalysisThread || analysisJustCompleted) && message.id === "msg-analyzing") || 
                // Demo mode: show content above ONLY while streaming, below when complete
                (isDemoThread && message.id === "msg-demo" && demo?.isStreaming)
              }
            />
          ))}

          <div ref={messagesEndRef} />

          {selectedThreadId && pendingApprovals.length > 0 && (
            <ApprovalDialog
              message={pendingApprovals[0]?.reason || pendingApprovals[0]?.title || "Runtime task needs your input"}
              options={pendingApprovals[0]?.options?.length ? pendingApprovals[0].options : ["Approve", "Reject"]}
              context={pendingApprovals[0]?.payload}
              timeoutSeconds={pendingApprovals[0]?.timeout_seconds}
              onResponse={async (option) => {
                if (!selectedThreadId) return;
                const action = option.toLowerCase() === "reject" ? "cancel" : "submit";
                const values = pendingApprovals[0]?.options?.length
                  ? { answer: option }
                  : {};

                await fetch(`${API_URL}/api/threads/${selectedThreadId}/respond`, {
                  method: "POST",
                  credentials: "include",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    request_id: pendingApprovals[0]?.request_id,
                    action,
                    values,
                    message: option,
                  }),
                });
                setPendingApprovals([]);
              }}
            />
          )}

          {/* Add comment - with avatar like GitHub, styled like chat input */}
          <div className="flex gap-3">
            {/* User Avatar */}
            <div className="w-5 h-5 @lg:w-7 @lg:h-7 rounded-full bg-[#c026a6] flex items-center justify-center text-[9px] @lg:text-[11px] font-medium text-white flex-shrink-0 overflow-hidden">
              {user?.avatar_url ? (
                <UserAvatar src={user.avatar_url} name={user.display_name || "You"} fallback="Y" />
              ) : (
                "Y"
              )}
            </div>

            {/* Comment Box - styled like chat textarea */}
            <div className="flex-1">
              <div
                className={cn(
                  "border rounded-xl bg-white dark:bg-black px-3 py-2 transition-colors",
                  isDragging
                    ? "border-primary bg-primary/5 dark:bg-primary/5"
                    : "border-neutral-300 dark:border-neutral-700"
                )}
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
              >
                {/* Attached files preview */}
                {attachedFiles.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-2">
                    {attachedFiles.map((file, index) => (
                      <div
                        key={index}
                        className="relative group flex items-center gap-2 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg px-2 py-1.5"
                      >
                        <FileImage className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
                        <span className="text-[11px] text-[var(--text-primary)] max-w-[150px] truncate">
                          {file.name}
                        </span>
                        <button
                          onClick={() => removeFile(index)}
                          className="ml-1 p-0.5 hover:bg-[var(--bg-tertiary)] rounded transition-colors"
                        >
                          <X className="h-3 w-3 text-[var(--text-secondary)] hover:text-[var(--text-primary)]" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <textarea
                  ref={commentTextareaRef}
                  value={commentInput}
                  onChange={(e) => setCommentInput(e.target.value)}
                  placeholder={isDragging ? "Drop files here..." : "Leave a comment..."}
                  className="min-h-[24px] w-full resize-none border-none bg-transparent px-0 py-0 text-[13px] text-black dark:text-white placeholder:text-neutral-400 dark:placeholder:text-neutral-600 focus:outline-none"
                />
                <div className="flex items-center justify-end gap-1 pt-1">
                  <label className="cursor-pointer">
                    <input
                      type="file"
                      multiple
                      accept="image/*"
                      onChange={handleFileSelect}
                      className="hidden"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-tertiary)] rounded-md pointer-events-none"
                      title="Attach file"
                      asChild
                    >
                      <span className="pointer-events-none">
                        <Paperclip className="h-3.5 w-3.5" />
                      </span>
                    </Button>
                  </label>
                  <Button
                    onClick={handleSendMessage}
                    disabled={!commentInput.trim()}
                    size="sm"
                    className="h-7 w-7 p-0 bg-neutral-800 dark:bg-neutral-200 hover:bg-neutral-900 dark:hover:bg-neutral-100 hover:scale-105 active:scale-95 text-white dark:text-black rounded-md disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:scale-100 transition-all duration-150"
                    title="Send comment"
                  >
                    <Send className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </ScrollArea>

      {/* Close Thread Confirmation Dialog */}
      <AlertDialog open={showCloseDialog} onOpenChange={setShowCloseDialog}>
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-[var(--text-primary)]">Close Thread</AlertDialogTitle>
            <AlertDialogDescription className="text-[var(--text-secondary)]">
              Are you sure you want to close this thread? You can reopen it later if needed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleCloseThread}
              className="bg-primary hover:bg-primary-hover text-primary-foreground"
            >
              Close
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reopen Thread Confirmation Dialog */}
      <AlertDialog open={showReopenDialog} onOpenChange={setShowReopenDialog}>
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-[var(--text-primary)]">Reopen Thread</AlertDialogTitle>
            <AlertDialogDescription className="text-[var(--text-secondary)]">
              Are you sure you want to reopen this thread? It will be marked as open and moved back to active threads.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleReopenThread}
              className="bg-primary hover:bg-primary-hover text-primary-foreground"
            >
              Reopen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {threadDeleteAlertDialog}
    </div>
    </ThreadErrorBoundary>
  );
}
