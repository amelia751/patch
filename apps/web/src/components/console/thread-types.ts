import type { ThreadEvent, ThreadTask, ThreadTodo, ActiveToolInfo, ThreadWaitingState } from "@/hooks/useThreadStream";

export interface RawMessage {
  id: string;
  role: string;
  content?: string;
  created_at: string;
  metadata?: {
    incremental?: boolean;
    session_marker?: boolean;
  };
  tool_calls?: string | object;
  todos?: RuntimeTodo[];
  activities?: string | Activity[];
  clarification?: string | Clarification;
}

export interface RawThread {
  id: string;
  thread_number: number;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  total_messages?: number;
  agent_type?: string;
}

export interface StoredEvent {
  type: string;
  content: unknown;
  metadata?: Record<string, unknown>;
  timestamp?: string;
}

export interface ToolCall {
  name?: string;
  status?: string;
  events?: StoredEvent[];
}

export interface Activity {
  id: string;
  status: "completed" | "in_progress" | "pending" | "failed" | "needs_input" | "cancelled";
  title: string;
  duration?: string;
  summary?: string;
  logs?: string[];
  content?: string;
}

export interface RuntimeTodo {
  id: string;
  content: string;
  status: "pending" | "in_progress" | "completed" | "failed" | "cancelled";
}

export interface Clarification {
  id: string;
  question: string;
  context?: string;
  options: string[];
}

export interface Thread {
  id: string;
  threadNumber: number;
  title: string;
  status: "open" | "closed" | "in_progress";
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  activityCount: number;
  preview: string;
  branch?: string | null;
}

export interface Message {
  id: string;
  author: "user" | "agent";
  content: string;
  timestamp: string;
  tool_calls?: string | object;
  worklog?: WorklogEntry[];
  thinking?: string;
  todos?: RuntimeTodo[];
  activities?: Activity[];
  clarification?: Clarification;
  /** Client-only UI: inline CTA in the console (not from the API) */
  clientAttachment?:
    | "google_test_session"
    | "configure_secrets"
    | "configure_gcp_connection";
}

export type WorklogEntry = {
  kind: "action" | "result" | "narration" | "block" | "collapsed_group" | "thinking" | "response";
  text: string;
  toolType?: string;
  toolUseId?: string;
  result?: string;
  filePath?: string;
  items?: { tool: string; detail: string }[];
  durationMs?: number;
};

export interface ThreadsProps {
  project?: {
    id: string;
    name: string;
    status: string;
    threadId?: string;
    threadNumber?: number;
  } | null;
  onAnalysisComplete?: () => void;
  initialThreadId?: string | null;
  onThreadSelect?: (threadId: string | null) => void;
}

export interface MessageBlockProps {
  message: Message;
  onSelectClarification: (option: string) => void;
  userAvatar?: string | null;
  userName?: string;
  streamActivities?: ThreadTask[];
  streamTodos?: ThreadTodo[];
  streamWorklog?: WorklogEntry[];
  isStreaming?: boolean;
  isAnalyzingMessage?: boolean;
  currentThought?: string | null;
  activeTool?: ActiveToolInfo | null;
  waitingState?: ThreadWaitingState | null;
}

export { type ThreadEvent, type ThreadTask, type ThreadTodo, type ActiveToolInfo, type ThreadWaitingState };
