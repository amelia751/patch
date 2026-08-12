"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { uiTheme } from "@/lib/ui-theme";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Event types for thread streaming.
 * These match the backend EventType enum.
 */
export type ThreadEventType =
  | "thought"           // Agent's internal reasoning
  | "thinking"          // Real-time LLM thinking (ephemeral streaming)
  | "info"              // Informational/non-streaming status
  | "action"            // Agent is taking an action
  | "planning"          // Planning steps
  | "progress"          // Progress update on current task
  | "tool_call"         // Calling a tool/LLM
  | "tool_result"       // Tool output
  | "file_read"         // Reading a file
  | "file_create"       // Creating a new file
  | "file_write"        // Writing to a file
  | "contract"          // Found a contract
  | "error"             // An error occurred
  | "complete"          // All work is done
  | "message"           // Generic message
  | "phase"             // Phase/action events
  | "success"           // Success status
  | "failure"           // Failure status
  | "warning"           // Warning status
  // Structured event types
  | "code_diff"         // Code diff/edit
  | "code_block"        // Code block (generic)
  | "cli_command"       // CLI command execution
  | "cli_output"        // CLI output
  | "cli_complete"      // CLI command completed
  | "resource_create"   // Creating a resource
  | "resource_creating" // Resource being created
  | "resource_verify"   // Verifying a resource
  | "resource_verified" // Resource verified
  // Thread-specific event types
  | "task_started"      // A new task has begun
  | "task_progress"     // Progress update on a task
  | "task_completed"    // A task finished successfully
  | "task_failed"       // A task failed
  | "task_waiting"      // Agent is waiting for user input
  | "todo_update"       // Runtime todo/task-list snapshot
  | "code_generated"    // Agent generated code
  | "command_run"       // Agent ran a CLI command
  | "resource_created" // AWS resource was created
  | "thread_title"     // LLM-generated conversation title
  | "browser_action";  // Browser automation step (navigate, snapshot, click, etc.)

/**
 * A single event from the thread stream.
 */
export interface ThreadEvent {
  type: ThreadEventType;
  content: string | Record<string, any>;
  metadata: {
    task_id?: string;
    title?: string;
    duration?: string;
    error?: string;
    question?: string;
    language?: string;
    filename?: string;
    command?: string;
    output?: string;
    resource_type?: string;
    resource_name?: string;
    arn?: string;
    current?: number;
    total?: number;
    keepalive?: boolean;
    [key: string]: any;
  };
  timestamp: string;
}

/**
 * Represents a task/activity in the thread.
 */
export interface ThreadTask {
  id: string;
  title: string;
  status: "pending" | "in_progress" | "completed" | "failed" | "waiting";
  startedAt?: string;
  completedAt?: string;
  duration?: string;
  events: ThreadEvent[];  // All events for this task
  error?: string;
  question?: string;      // If waiting for input
}

export interface ThreadTodo {
  id: string;
  content: string;
  status: "pending" | "in_progress" | "completed" | "failed" | "cancelled";
}

interface UseThreadStreamOptions {
  enabled?: boolean;
  maxEvents?: number;
  onEvent?: (event: ThreadEvent) => void;
  onTaskUpdate?: (task: ThreadTask) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
  /** Fired when the backend streams a generated thread title (first message). */
  onThreadTitle?: (title: string, threadId?: string) => void;
}

export interface ActiveToolInfo {
  verb: string;
  detail?: string;
  startedAt: number;
}

export interface ThreadWaitingState {
  kind: "queued" | "worker_unavailable";
  message: string;
  retryable?: boolean;
  since: number;
}

interface UseThreadStreamResult {
  // Raw events
  events: ThreadEvent[];
  
  // Processed tasks
  tasks: ThreadTask[];
  todos: ThreadTodo[];
  
  // Connection state
  isConnected: boolean;
  isComplete: boolean;
  isStreaming: boolean;
  /** True from first event until complete/disconnect. Use for content visibility. */
  hasActiveRun: boolean;
  
  // Current state
  currentTask: ThreadTask | null;
  currentThought: string | null;
  currentAction: string | null;
  activeTool: ActiveToolInfo | null;
  waitingState: ThreadWaitingState | null;
  progress: { current: number; total: number } | null;
  
  // Last event received
  lastEvent: ThreadEvent | null;
  
  // Controls
  connect: () => void;
  disconnect: () => void;
  clear: () => void;
}

/**
 * Hook to consume SSE stream of agent events for a thread.
 * 
 * This hook provides:
 * - Real-time events from the agent
 * - Processed task objects with status tracking
 * - Current thought/action state for UI indicators
 * 
 * Usage:
 * ```tsx
 * const {
 *   events,
 *   tasks,
 *   isConnected,
 *   currentThought,
 *   currentAction,
 * } = useThreadStream(threadId, { enabled: true });
 * 
 * // Show streaming indicator
 * {currentAction && <StreamingIndicator action={currentAction} />}
 * 
 * // Show tasks
 * {tasks.map(task => <TaskCard key={task.id} task={task} />)}
 * ```
 */
export function useThreadStream(
  threadId: string | null,
  options: UseThreadStreamOptions = {}
): UseThreadStreamResult {
  const {
    enabled = true,
    maxEvents = 200,
    onEvent,
    onTaskUpdate,
    onComplete,
    onError,
    onThreadTitle,
  } = options;

  // State
  const [events, setEvents] = useState<ThreadEvent[]>([]);
  const [tasks, setTasks] = useState<ThreadTask[]>([]);
  const [todos, setTodos] = useState<ThreadTodo[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [hasActiveRun, setHasActiveRun] = useState(false);
  const [lastEvent, setLastEvent] = useState<ThreadEvent | null>(null);
  const [currentThought, setCurrentThought] = useState<string | null>(null);
  const [currentAction, setCurrentAction] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<ActiveToolInfo | null>(null);
  const [waitingState, setWaitingState] = useState<ThreadWaitingState | null>(null);
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null);

  // Refs
  const eventSourceRef = useRef<EventSource | null>(null);
  const retriesRef = useRef(0);
  const isCompleteRef = useRef(false);
  const hasSettledRunRef = useRef(false);
  const lastEventTimeRef = useRef<number>(Date.now());
  const maxRetries = 3;

  // Callback refs to avoid recreation
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  const onEventRef = useRef(onEvent);
  const onTaskUpdateRef = useRef(onTaskUpdate);
  const onThreadTitleRef = useRef(onThreadTitle);

  useEffect(() => {
    onCompleteRef.current = onComplete;
    onErrorRef.current = onError;
    onEventRef.current = onEvent;
    onTaskUpdateRef.current = onTaskUpdate;
    onThreadTitleRef.current = onThreadTitle;
  }, [onComplete, onError, onEvent, onTaskUpdate, onThreadTitle]);

  // Get current task
  const currentTask = tasks.find(t => t.status === "in_progress" || t.status === "waiting") || null;

  const settleRun = useCallback((markComplete: boolean) => {
    if (markComplete) {
      isCompleteRef.current = true;
      setIsComplete(true);
    }
    setCurrentAction(null);
    setCurrentThought(null);
    setActiveTool(null);
    setWaitingState(null);
    setIsStreaming(false);
    setHasActiveRun(false);
    if (!hasSettledRunRef.current) {
      hasSettledRunRef.current = true;
      onCompleteRef.current?.();
    }
  }, []);

  /**
   * Process an event and update tasks accordingly.
   */
  const processEvent = useCallback((event: ThreadEvent) => {
    const getContentAsString = (content: unknown): string => {
      if (typeof content === "string") return content;
      if (content && typeof content === "object") {
        const obj = content as Record<string, unknown>;
        return (obj.message || obj.content || obj.text || obj.title || "") as string;
      }
      return "";
    };

    if (event.type === "thread_title") {
      const title = getContentAsString(event.content).trim();
      if (title) {
        const tid =
          typeof event.metadata?.thread_id === "string" ? event.metadata.thread_id : undefined;
        onThreadTitleRef.current?.(title, tid);
      }
      setEvents((prev) => {
        const next = [...prev, event];
        return next.length > maxEvents ? next.slice(-maxEvents) : next;
      });
      setLastEvent(event);
      onEventRef.current?.(event);
      return;
    }

    const idleText = getContentAsString(event.content).trim().toLowerCase();
    if (
      event.metadata?.idle ||
      (event.type === "info" && idleText.includes("no active pipeline"))
    ) {
      return;
    }

    const streamState = typeof event.metadata?.stream_state === "string"
      ? event.metadata.stream_state
      : null;
    if (event.type === "info" && (streamState === "queued" || streamState === "worker_unavailable")) {
      lastEventTimeRef.current = Date.now();
      setIsStreaming(true);
      setHasActiveRun(true);
      setWaitingState(prev => ({
        kind: streamState,
        message: getContentAsString(event.content) || (streamState === "queued" ? "Queued" : "Waiting for worker"),
        retryable: Boolean(event.metadata?.retryable),
        since: prev?.since ?? Date.now(),
      }));
      return;
    }

    setEvents(prev => {
      const newEvents = [...prev, event];
      if (newEvents.length > maxEvents) {
        return newEvents.slice(-maxEvents);
      }
      return newEvents;
    });
    setLastEvent(event);
    lastEventTimeRef.current = Date.now();
    setIsStreaming(true);
    setHasActiveRun(true);
    setWaitingState(null);

    if (event.type === "thought" || event.type === "thinking") {
      const thought = getContentAsString(event.content);
      if (thought) {
        setCurrentThought(thought);
      }
    }
    if (event.type === "action") {
      const action = getContentAsString(event.content);
      if (action) {
        setCurrentAction(action);
      }
    }
    if (event.type === "message" || event.type === "tool_call") {
      setCurrentThought(null);
    }

    // Track active tool for spinner display
    if (event.type === "tool_call") {
      const toolName = (event.metadata?.tool || (typeof event.content === "object" ? (event.content as Record<string, unknown>).tool : "")) as string;
      const args = typeof event.content === "object" ? (event.content as Record<string, unknown>).arguments as Record<string, unknown> | undefined : undefined;
      let verb = "Working";
      let detail: string | undefined;
      if (toolName === "Bash" || toolName === "BashTool") {
        verb = "Running";
        detail = typeof args?.command === "string" ? args.command.slice(0, 60) : undefined;
      } else if (toolName === "Read" || toolName === "FileRead" || toolName === "FileReadTool") {
        verb = "Reading";
        detail = typeof args?.file_path === "string" ? args.file_path.split("/").pop() : undefined;
      } else if (toolName === "Edit" || toolName === "FileEdit" || toolName === "FileEditTool") {
        verb = "Editing";
        detail = typeof args?.file_path === "string" ? args.file_path.split("/").pop() : undefined;
      } else if (toolName === "Write" || toolName === "FileWrite" || toolName === "FileWriteTool") {
        verb = "Writing";
        detail = typeof args?.file_path === "string" ? args.file_path.split("/").pop() : undefined;
      } else if (toolName === "Grep" || toolName === "GrepTool") {
        verb = "Searching";
        detail = typeof args?.pattern === "string" ? args.pattern : undefined;
      } else if (toolName === "Glob" || toolName === "GlobTool") {
        verb = "Finding files";
        detail = typeof args?.pattern === "string" ? args.pattern : undefined;
      } else if (toolName === "WebSearch") {
        verb = "Searching web";
        detail = typeof args?.search_term === "string"
          ? args.search_term
          : typeof args?.query === "string"
            ? args.query
            : undefined;
      } else if (toolName === "WebFetch") {
        verb = "Fetching";
        detail = typeof args?.url === "string" ? args.url : undefined;
      } else if (toolName === "Task" || toolName === "AgentTool") {
        verb = "Delegating";
      } else if (toolName) {
        verb = toolName;
      }
      setActiveTool({ verb, detail, startedAt: Date.now() });
    }
    if (event.type === "tool_result") {
      setActiveTool(null);
    }
    if (event.type === "message") {
      setActiveTool(null);
    }

    // Update progress
    if (event.type === "progress" && event.metadata) {
      if (event.metadata.current !== undefined && event.metadata.total !== undefined) {
        setProgress({ current: event.metadata.current, total: event.metadata.total });
      }
    }

    // Handle task events
    if (event.type === "task_started") {
      const taskId = event.metadata.task_id || `task-${Date.now()}`;
      const title = String(event.metadata.title || getContentAsString(event.content) || "Task");
      
      setTasks(prev => {
        // Check if task already exists
        const existing = prev.find(t => t.id === taskId);
        if (existing) {
          return prev.map(t => t.id === taskId ? {
            ...t,
            status: "in_progress" as const,
            events: [...t.events, event],
          } : t);
        }
        
        const newTask: ThreadTask = {
          id: taskId,
          title,
          status: "in_progress",
          startedAt: event.timestamp,
          events: [event],
        };
        
        onTaskUpdateRef.current?.(newTask);
        return [...prev, newTask];
      });
    }

    if (event.type === "task_completed") {
      const taskId = event.metadata.task_id;
      if (taskId) {
        setTasks(prev => prev.map(t => {
          if (t.id === taskId) {
            const updated: ThreadTask = {
              ...t,
              status: "completed",
              completedAt: event.timestamp,
              duration: event.metadata.duration,
              events: [...t.events, event],
            };
            onTaskUpdateRef.current?.(updated);
            return updated;
          }
          return t;
        }));
        // Runtime headless turn: assistant output is done — drop streaming chrome before cleanup `complete` (avoids stuck "Thinking…")
        if (taskId === "runtime-agent") {
          settleRun(false);
        }
      }
      setProgress(null);
    }

    if (event.type === "task_failed") {
      const taskId = event.metadata.task_id;
      if (taskId) {
        setTasks(prev => prev.map(t => {
          if (t.id === taskId) {
            const updated: ThreadTask = {
              ...t,
              status: "failed",
              error: String(event.metadata.error || getContentAsString(event.content) || "Task failed"),
              events: [...t.events, event],
            };
            onTaskUpdateRef.current?.(updated);
            return updated;
          }
          return t;
        }));
        if (taskId === "runtime-agent") {
          settleRun(false);
        }
      }
      setProgress(null);
    }

    if (event.type === "task_waiting") {
      const taskId = event.metadata.task_id;
      if (taskId) {
        setTasks(prev => prev.map(t => {
          if (t.id === taskId) {
            const updated: ThreadTask = {
              ...t,
              status: "waiting",
              question: typeof event.metadata.question === "string" ? event.metadata.question : undefined,
              events: [...t.events, event],
            };
            onTaskUpdateRef.current?.(updated);
            return updated;
          }
          return t;
        }));
      }
    }

    if (event.type === "todo_update") {
      const rawTodos = typeof event.content === "object" && event.content && Array.isArray((event.content as { todos?: unknown[] }).todos)
        ? (event.content as { todos: unknown[] }).todos
        : [];

      const normalizedTodos: ThreadTodo[] = rawTodos
        .map((todo: unknown) => {
          if (!todo || typeof todo !== "object") return null;
          const item = todo as Record<string, unknown>;
          const id = String(item.id || "").trim();
          const content = String(item.content || item.subject || "").trim();
          const status = String(item.status || "pending").trim() as ThreadTodo["status"];
          if (!id || !content) return null;
          return {
            id,
            content,
            status: status === "in_progress" || status === "completed" || status === "failed" || status === "cancelled"
              ? status
              : "pending",
          };
        })
        .filter((todo): todo is ThreadTodo => !!todo);

      setTodos(normalizedTodos);
    }

    // For other events, add to current in-progress task
    if (!["task_started", "task_completed", "task_failed", "task_waiting", "todo_update"].includes(event.type)) {
      setTasks(prev => {
        const inProgressIdx = prev.findIndex(t => t.status === "in_progress");
        if (inProgressIdx >= 0) {
          return prev.map((t, i) => i === inProgressIdx ? {
            ...t,
            events: [...t.events, event],
          } : t);
        }
        return prev;
      });
    }

    // Handle completion
    if (event.type === "complete") {
      settleRun(true);
    }

    // Handle errors
    if (event.type === "error") {
      onErrorRef.current?.(getContentAsString(event.content));
    }

    onEventRef.current?.(event);
  }, [maxEvents, settleRun]);

  /**
   * Connect to the SSE stream.
   */
  const connect = useCallback(() => {
    if (!threadId || eventSourceRef.current) return;

    const url = `${API_URL}/api/threads/${threadId}/stream`;

    try {
      const eventSource = new EventSource(url, { withCredentials: true });
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        console.log(`[ThreadSSE] Connected to thread ${threadId}`);
        setIsConnected(true);
        isCompleteRef.current = false;
        hasSettledRunRef.current = false;
        setIsComplete(false);
        retriesRef.current = 0;
      };

      eventSource.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data) as ThreadEvent;

          // Skip keepalive events
          if (event.metadata?.keepalive) return;

          processEvent(event);
        } catch (err) {
          console.error("[ThreadSSE] Failed to parse event:", err);
        }
      };

      eventSource.onerror = (err) => {
        const readyState = eventSource.readyState;

        // Stream was already marked complete — closure is expected
        if (isCompleteRef.current) {
          setIsConnected(false);
          eventSource.close();
          eventSourceRef.current = null;
          console.log("[ThreadSSE] Stream closed after completion (expected)");
          return;
        }

        setIsConnected(false);

        // Let the browser keep its built-in SSE reconnect behavior while the
        // socket is still in CONNECTING state. Closing here can freeze the UI
        // on a stale "Thinking..." event during transient reconnects.
        if (readyState === EventSource.CONNECTING) {
          console.warn("[ThreadSSE] Connection interrupted, browser reconnecting");
          return;
        }

        eventSource.close();
        if (eventSourceRef.current === eventSource) {
          eventSourceRef.current = null;
        }

        // Server closed the stream before we saw a complete event.
        // Only retry if we actually received events (hasSettledRunRef tracks this);
        // if the server returned an empty stream, the thread is idle/completed
        // and retrying would just burn backend resources for nothing.
        if (readyState === EventSource.CLOSED) {
          if (!hasSettledRunRef.current && retriesRef.current < maxRetries) {
            retriesRef.current++;
            console.warn(`[ThreadSSE] Server closed mid-run, retry ${retriesRef.current}/${maxRetries}`);
            setTimeout(() => {
              if (!isCompleteRef.current && !eventSourceRef.current) {
                connect();
              }
            }, 1000 * retriesRef.current);
            return;
          }
          console.log("[ThreadSSE] Server closed stream (thread idle or retries exhausted)");
          setIsStreaming(false);
          setHasActiveRun(false);
          setCurrentThought(null);
          setActiveTool(null);
          return;
        }

        // Actual connection error (readyState CONNECTING = 0 means
        // the browser detected a failure and was about to auto-reconnect)
        if (err instanceof ErrorEvent) {
          console.warn("[ThreadSSE] Connection error:", err.message);
        } else {
          console.warn("[ThreadSSE] Connection lost, will retry");
        }

        // Retry on real errors only
        if (retriesRef.current < maxRetries) {
          retriesRef.current++;
          console.log(`[ThreadSSE] Retrying connection (${retriesRef.current}/${maxRetries})`);
          setTimeout(() => {
            if (!isCompleteRef.current && !eventSourceRef.current) {
              connect();
            }
          }, 1000 * retriesRef.current);
        }
      };

    } catch (err) {
      console.error("[ThreadSSE] Failed to connect:", err);
    }
  }, [threadId, processEvent]);

  /**
   * Disconnect from the SSE stream.
   */
  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsConnected(false);
    setIsStreaming(false);
    setHasActiveRun(false);
    setWaitingState(null);
  }, []);

  /**
   * Clear all events and tasks.
   */
  const clear = useCallback(() => {
    setEvents([]);
    setTasks([]);
    setTodos([]);
    setLastEvent(null);
    setCurrentThought(null);
    setCurrentAction(null);
    setActiveTool(null);
    setWaitingState(null);
    setProgress(null);
    isCompleteRef.current = false;
    hasSettledRunRef.current = false;
    setIsComplete(false);
    setIsStreaming(false);
    setHasActiveRun(false);
  }, []);

  // The 3-second idle check was removed because it caused unnecessary
  // re-renders that made streaming content flicker. isStreaming is now only
  // cleared explicitly by: complete event (150ms delay), disconnect(), or clear().
  // hasActiveRun is the stable signal for content visibility.

  useEffect(() => {
    if (!waitingState || waitingState.kind === "worker_unavailable") {
      return;
    }
    const timeout = setTimeout(() => {
      setWaitingState(prev => {
        if (!prev || prev.kind === "worker_unavailable") {
          return prev;
        }
        return {
          kind: "worker_unavailable",
          message: "Still waiting to start. You can retry.",
          retryable: true,
          since: prev.since,
        };
      });
    }, 30000);
    return () => clearTimeout(timeout);
  }, [waitingState]);

  // Auto-connect when threadId changes and enabled
  useEffect(() => {
    if (enabled && threadId) {
      clear();
      connect();
    }

    return () => {
      disconnect();
    };
  }, [threadId, enabled, connect, disconnect, clear]);

  return {
    events,
    tasks,
    todos,
    isConnected,
    isComplete,
    isStreaming,
    hasActiveRun,
    currentTask,
    currentThought,
    currentAction,
    activeTool,
    waitingState,
    progress,
    lastEvent,
    connect,
    disconnect,
    clear,
  };
}

/**
 * Get icon for event type — minimal typographic markers, no emojis.
 */
export function getThreadEventIcon(type: ThreadEventType): string {
  switch (type) {
    case "thought": return "·";
    case "action": return "›";
    case "progress": return "·";
    case "tool_call": return "›";
    case "tool_result": return "✓";
    case "error": return "✗";
    case "complete": return "✓";
    case "task_started": return "›";
    case "task_progress": return "·";
    case "task_completed": return "✓";
    case "task_failed": return "✗";
    case "task_waiting": return "·";
    case "todo_update": return "·";
    case "browser_action": return "›";
    default: return "·";
  }
}

/**
 * Get color class for event type.
 */
export function getThreadEventColor(type: ThreadEventType): string {
  switch (type) {
    case "thought": return "text-gray-400";
    case "action": return "text-blue-400";
    case "progress": return uiTheme.textProgress;
    case "tool_call": return "text-purple-400";
    case "tool_result": return "text-green-400";
    case "error": return "text-red-400";
    case "complete": return "text-green-500";
    case "task_started": return "text-blue-400";
    case "task_progress": return uiTheme.textProgress;
    case "task_completed": return "text-green-500";
    case "task_failed": return "text-red-500";
    case "task_waiting": return "text-amber-400";
    case "todo_update": return "text-gray-400";
    case "browser_action": return "text-cyan-400";
    default: return "text-gray-400";
  }
}
