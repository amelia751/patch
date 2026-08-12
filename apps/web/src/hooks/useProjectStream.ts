"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { uiTheme } from "@/lib/ui-theme";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Event types from the backend
export type EventType = 
  | "thought"
  | "thinking"  // Real-time LLM thinking (ephemeral streaming)
  | "action"
  | "phase"     // Phase/action events from backend
  | "progress"
  | "tool_call"
  | "tool_result"
  | "file_read"
  | "contract"
  | "error"
  | "complete"
  | "task_started"    // Task lifecycle events (like demo mode)
  | "task_completed"
  | "task_failed"
  | "deployment_status"  // Ops tabs: deployment created/completed/failed
  | "browser_action";   // Browser automation step (navigate, snapshot, click, etc.)

export interface AgentEvent {
  type: EventType;
  content: string | Record<string, any>;
  metadata: Record<string, any>;
  timestamp: string;
}

// Execution step from backend
export interface ExecutionStep {
  id: string;
  name: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  started_at?: string;
  completed_at?: string;
  output?: Record<string, any>;
  error?: string;
  duration_ms?: number;
}

// Full execution state for resume
export interface ExecutionState {
  execution_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  current_step_index: number;
  total_steps: number;
  steps: ExecutionStep[];
  last_event_index: number;
  result?: Record<string, any>;
  error?: string;
  thread_id?: string;
  thread_number?: number;
  started_at?: string;
  updated_at?: string;
  completed_at?: string;
}

interface UseProjectStreamOptions {
  enabled?: boolean;
  maxEvents?: number;
  onEvent?: (event: AgentEvent) => void;
  onComplete?: (allEvents: AgentEvent[]) => void;
  onError?: (error: string) => void;
  onReconnect?: (execution: ExecutionState) => void;  // Called when reconnecting with state
}

// Task structure for analysis (like demo mode)
export interface ProjectTask {
  id: string;
  name: string;
  status: "pending" | "in_progress" | "completed" | "failed";
  events: Array<{ type: string; content: string | Record<string, any>; timestamp: string; metadata?: Record<string, any> }>;
  startedAt?: string;
  completedAt?: string;
}

interface UseProjectStreamResult {
  events: AgentEvent[];
  tasks: ProjectTask[];  // Task list (like demo mode)
  isConnected: boolean;
  isComplete: boolean;
  lastEvent: AgentEvent | null;
  currentAction: string | null;
  progress: { current: number; total: number } | null;
  execution: ExecutionState | null;  // Current execution state
  connect: () => void;
  disconnect: () => void;
  clear: () => void;
  resume: () => Promise<void>;  // Manual resume from last state
}

/**
 * Hook to consume SSE stream of agent events for a project.
 *
 * Reconnection capability:
 * - On disconnect, fetches execution state from /execution endpoint
 * - Resumes SSE from last_event_index using /stream/resume
 * - Rebuilds UI state from completed steps
 *
 * Usage:
 *   const { events, isConnected, currentAction, execution } = useProjectStream("my-project");
 */
export function useProjectStream(
  projectId: string | null,
  options: UseProjectStreamOptions = {}
): UseProjectStreamResult {
  const {
    enabled = true,
    maxEvents = 1000,
    onEvent,
    onComplete,
    onError,
    onReconnect,
  } = options;

  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [tasks, setTasks] = useState<ProjectTask[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [lastEvent, setLastEvent] = useState<AgentEvent | null>(null);
  const [currentAction, setCurrentAction] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null);
  const [execution, setExecution] = useState<ExecutionState | null>(null);
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const retriesRef = useRef(0);
  const isCompleteRef = useRef(false);
  const eventsRef = useRef<AgentEvent[]>([]);
  const lastEventIndexRef = useRef(0);  // Track last received event index
  const maxRetries = 5;  // Increased for better resilience
  
  // Store callbacks in refs
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  const onEventRef = useRef(onEvent);
  const onReconnectRef = useRef(onReconnect);
  
  useEffect(() => {
    onCompleteRef.current = onComplete;
    onErrorRef.current = onError;
    onEventRef.current = onEvent;
    onReconnectRef.current = onReconnect;
  }, [onComplete, onError, onEvent, onReconnect]);

  const addEvent = useCallback((event: AgentEvent) => {
    eventsRef.current = [...eventsRef.current, event];
    if (eventsRef.current.length > maxEvents) {
      eventsRef.current = eventsRef.current.slice(-maxEvents);
    }
    
    setEvents(eventsRef.current);
    setLastEvent(event);

    // Track event index for resume -- use the sequential index assigned by the backend
    if (event.metadata?.event_index !== undefined) {
      lastEventIndexRef.current = event.metadata.event_index + 1;
    }

    if (event.type === "action" || event.type === "thought" || (event.type === "phase" && event.metadata?.action)) {
      setCurrentAction(typeof event.content === "string" ? event.content : event.content?.name || "Processing...");
    }

    // Handle task lifecycle events (like demo mode)
    if (event.type === "task_started") {
      const taskId = event.metadata?.task_id || `task-${Date.now()}`;
      // Safely extract content as string
      const contentStr = typeof event.content === "string" 
        ? event.content 
        : (event.content?.message || event.content?.content || event.content?.text || event.content?.title || "");
      setTasks(prev => {
        const existing = prev.find(t => t.id === taskId);
        if (existing) {
          // Task is being retried (e.g. activity retry after server restart).
          // Reset it to in_progress so the UI shows the retry.
          return prev.map(t => t.id === taskId ? {
            ...t,
            status: "in_progress" as const,
            events: [],
            startedAt: event.timestamp,
            completedAt: undefined,
          } : t);
        }
        return [...prev, {
          id: taskId,
          name: contentStr || event.metadata?.title || "Task",
          status: "in_progress",
          events: [],
          startedAt: event.timestamp,
        }];
      });
      setCurrentAction(contentStr || event.metadata?.title || "Processing...");
    }

    if (event.type === "task_completed") {
      const taskId = event.metadata?.task_id;
      if (taskId) {
        setTasks(prev => prev.map(t => 
          t.id === taskId 
            ? { ...t, status: "completed" as const, completedAt: event.timestamp }
            : t
        ));
      }
    }

    if (event.type === "task_failed") {
      const taskId = event.metadata?.task_id;
      if (taskId) {
        setTasks(prev => prev.map(t => 
          t.id === taskId 
            ? { ...t, status: "failed" as const }
            : t
        ));
      }
    }

    // Add sub-events (thought, progress, tool_result) to current in-progress task
    if (["thought", "progress", "tool_result"].includes(event.type)) {
      setTasks(prev => {
        const lastTask = prev[prev.length - 1];
        if (lastTask && lastTask.status === "in_progress") {
          return prev.map((t, i) => 
            i === prev.length - 1
              ? { ...t, events: [...t.events, { type: event.type, content: event.content, timestamp: event.timestamp }] }
              : t
          );
        }
        return prev;
      });
    }

    if (event.type === "progress" && event.metadata) {
      if (event.metadata.current !== undefined && event.metadata.total !== undefined) {
        setProgress({ current: event.metadata.current, total: event.metadata.total });
      }
      // Handle catch-up events from resume
      if (event.metadata.catch_up && event.metadata.completed_steps) {
        console.log("[SSE] Caught up with", event.metadata.completed_steps.length, "completed steps");
      }
    }

    if (event.type === "complete") {
      isCompleteRef.current = true;
      setIsComplete(true);
      setCurrentAction(null);
      onCompleteRef.current?.(eventsRef.current);
    }

    if (event.type === "error") {
      const errorStr = typeof event.content === "string" 
        ? event.content 
        : (event.content?.message || event.content?.error || JSON.stringify(event.content));
      onErrorRef.current?.(errorStr);
    }

    onEventRef.current?.(event);
  }, [maxEvents]);

  // Fetch execution state for resume
  const fetchExecutionState = useCallback(async (): Promise<ExecutionState | null> => {
    if (!projectId) return null;
    
    try {
      const response = await fetch(`${API_URL}/api/projects/${projectId}/execution`, {
        credentials: "include",
      });
      
      if (!response.ok) {
        console.warn("[SSE] Failed to fetch execution state:", response.status);
        return null;
      }
      
      const data = await response.json();
      return data.execution_id ? data : (data.execution || null);
    } catch (err) {
      console.error("[SSE] Error fetching execution state:", err);
      return null;
    }
  }, [projectId]);

  // Resume connection from last event index
  const resume = useCallback(async () => {
    if (!projectId) return;
    
    console.log("[SSE] Attempting to resume connection...");
    
    // First, fetch current execution state
    const executionState = await fetchExecutionState();
    
    if (executionState) {
      setExecution(executionState);
      
      // Detect server restart: backend emitter buffer is smaller than our cursor.
      // This means the in-memory emitter was recreated (uvicorn --reload, etc.).
      // Reset all local state so we replay cleanly from the new emitter.
      if (lastEventIndexRef.current > 0 && executionState.last_event_index < lastEventIndexRef.current) {
        console.log(`[SSE] Detected server restart (backend=${executionState.last_event_index}, local=${lastEventIndexRef.current}), resetting state`);
        eventsRef.current = [];
        setEvents([]);
        setTasks([]);
        lastEventIndexRef.current = 0;
      } else if (lastEventIndexRef.current > 0) {
        // Normal reconnect — advance cursor to not re-process old events
        lastEventIndexRef.current = Math.max(lastEventIndexRef.current, executionState.last_event_index);
      }
      
      // Notify caller about reconnection with state
      onReconnectRef.current?.(executionState);
      
      // If execution is already complete, don't reconnect SSE
      if (executionState.status === "completed" || executionState.status === "failed") {
        console.log("[SSE] Execution already finished, no need to reconnect");
        isCompleteRef.current = true;
        setIsComplete(true);
        return;
      }
    }
    
    // Connect to resume endpoint with last event index
    const fromEvent = lastEventIndexRef.current;
    const url = `${API_URL}/api/projects/${projectId}/stream/resume?from_event=${fromEvent}`;
    
    console.log(`[SSE] Resuming from event ${fromEvent}`);
    
    try {
      const eventSource = new EventSource(url, { withCredentials: true });
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        console.log(`[SSE] Resumed connection to ${projectId}`);
        setIsConnected(true);
        retriesRef.current = 0;
      };

      eventSource.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data) as AgentEvent;
          if (event.metadata?.keepalive) return;
          addEvent(event);
        } catch (err) {
          console.error("[SSE] Failed to parse event:", err);
        }
      };

      eventSource.onerror = () => {
        setIsConnected(false);
        eventSource.close();
        eventSourceRef.current = null;
        
        // Auto-retry with exponential backoff
        if (retriesRef.current < maxRetries && !isCompleteRef.current) {
          retriesRef.current++;
          const delay = Math.min(1000 * Math.pow(2, retriesRef.current - 1), 10000);
          console.log(`[SSE] Retrying in ${delay}ms (${retriesRef.current}/${maxRetries})`);
          setTimeout(() => {
            if (!isCompleteRef.current && !eventSourceRef.current) {
              resume();
            }
          }, delay);
        }
      };

    } catch (err) {
      console.error("[SSE] Failed to resume:", err);
    }
  }, [projectId, addEvent, fetchExecutionState]);

  const connect = useCallback(() => {
    if (!projectId || eventSourceRef.current) {
      console.log(`[SSE] Skipping connect: projectId=${projectId}, existing connection=${!!eventSourceRef.current}`);
      return;
    }

    const url = `${API_URL}/api/projects/${projectId}/stream`;
    console.log(`[SSE] Connecting to ${url}`);

    try {
      const eventSource = new EventSource(url, { withCredentials: true });
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        console.log(`[SSE] Connected to ${projectId}`);
        setIsConnected(true);
        isCompleteRef.current = false;
        setIsComplete(false);
        retriesRef.current = 0;
      };

      eventSource.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data) as AgentEvent;
          if (event.metadata?.keepalive) return;
          console.log(`[SSE] ⬇️ Received event:`, event.type, event.content);
          addEvent(event);
        } catch (err) {
          console.error("[SSE] Failed to parse event:", err, e.data);
        }
      };

      eventSource.onerror = () => {
        // Only log error if the stream wasn't already complete
        if (!isCompleteRef.current) {
          console.error("[SSE] Connection error");
        } else {
          console.log("[SSE] Stream closed after completion (expected)");
        }
        
        setIsConnected(false);
        eventSource.close();
        eventSourceRef.current = null;

        // Use resume instead of simple reconnect
        if (retriesRef.current < maxRetries && !isCompleteRef.current) {
          retriesRef.current++;
          const delay = Math.min(1000 * Math.pow(2, retriesRef.current - 1), 10000);
          console.log(`[SSE] Will attempt resume in ${delay}ms`);
          setTimeout(() => {
            if (!isCompleteRef.current && !eventSourceRef.current) {
              resume();  // Use resume for reconnection!
            }
          }, delay);
        }
      };

    } catch (err) {
      console.error("[SSE] Failed to connect:", err);
    }
  }, [projectId, addEvent, resume]);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const clear = useCallback(() => {
    setEvents([]);
    setTasks([]);
    eventsRef.current = [];
    setLastEvent(null);
    setCurrentAction(null);
    setProgress(null);
    setExecution(null);
    isCompleteRef.current = false;
    setIsComplete(false);
    lastEventIndexRef.current = 0;
  }, []);

  // Auto-connect when projectId changes
  useEffect(() => {
    if (enabled && projectId) {
      // Reset ALL state (including tasks) so reconnect starts clean
      setEvents([]);
      setTasks([]);
      setLastEvent(null);
      setCurrentAction(null);
      setProgress(null);
      setExecution(null);
      isCompleteRef.current = false;
      setIsComplete(false);
      lastEventIndexRef.current = 0;
      eventsRef.current = [];
      
      // First, check if there's an existing execution to resume
      fetchExecutionState().then((existingExecution) => {
        if (existingExecution) {
          setExecution(existingExecution);
          
          // If running, resume the stream from the BEGINNING (index 0)
          // We just reset state, so we need all events to rebuild the UI
          if (existingExecution.status === "running" || existingExecution.status === "pending") {
            lastEventIndexRef.current = 0;
            resume();
            return;
          }
          
          // If complete/failed, just show final state
          if (existingExecution.status === "completed" || existingExecution.status === "failed") {
            isCompleteRef.current = true;
            setIsComplete(true);
            onReconnectRef.current?.(existingExecution);
            return;
          }
        }
        
        // No existing execution, connect fresh
        connect();
      });
    }

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [projectId, enabled, connect, resume, fetchExecutionState]);

  return {
    events,
    tasks,
    isConnected,
    isComplete,
    lastEvent,
    currentAction,
    progress,
    execution,
    connect,
    disconnect,
    clear,
    resume,
  };
}

/**
 * Get icon for event type — minimal typographic markers, no emojis.
 */
export function getEventIcon(type: EventType): string {
  switch (type) {
    case "thought": return "·";
    case "action": return "›";
    case "progress": return "·";
    case "tool_call": return "›";
    case "tool_result": return "✓";
    case "error": return "✗";
    case "complete": return "✓";
    default: return "·";
  }
}

/**
 * Get color for event type.
 */
export function getEventColor(type: EventType): string {
  switch (type) {
    case "thought": return "text-gray-400";
    case "action": return "text-blue-400";
    case "progress": return uiTheme.textProgress;
    case "tool_call": return "text-purple-400";
    case "tool_result": return "text-green-400";
    case "error": return "text-red-400";
    case "complete": return "text-green-500";
    default: return "text-gray-400";
  }
}
