"use client";

/**
 * Demo Context
 * 
 * Manages the full demo experience including:
 * - Demo project state
 * - Real-time streaming replay (with actual timing from recordings)
 * - Thread simulation
 * - Notifications
 * 
 * This provides the exact same experience as real usage,
 * just replaying pre-recorded events instead of live compute.
 */

import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Get or create browser session ID for demo isolation
function getBrowserSessionId(): string {
  if (typeof window === "undefined") return "";
  
  let sessionId = localStorage.getItem("demo_browser_session_id");
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem("demo_browser_session_id", sessionId);
    console.log(`[Demo] Created new browser session: ${sessionId}`);
  }
  return sessionId;
}

// ============================================================================
// Types
// ============================================================================

export interface DemoProject {
  slug: string;
  name: string;
  cloud_provider: string;
  stats?: {
    contracts_found?: number;
    services_designed?: number;
    routes_defined?: number;
    files_generated?: number;
  };
}

export interface DemoThread {
  id: string;
  type: "analysis" | "devops";
  thread_number: number;
  title: string;
  status: "pending" | "streaming" | "completed";
  created_at: string;
}

export interface DemoEvent {
  type: string;
  content: string;
  metadata?: Record<string, any>;
  timestamp: string;
  elapsed_ms: number;
}

export interface DemoTask {
  id: string;
  name: string;
  status: "pending" | "in_progress" | "completed";
  events: Array<{ type: string; content: string; timestamp: string }>;
}

export type DemoPhase = "idle" | "importing" | "analyzing" | "analysis_complete" | "devops" | "devops_complete";
export type DemoMode = "replay" | "live";

interface DemoContextType {
  // State
  isDemo: boolean;
  mode: DemoMode;
  phase: DemoPhase;
  project: DemoProject | null;
  threads: DemoThread[];
  currentThread: DemoThread | null;
  events: DemoEvent[];
  tasks: DemoTask[];
  architecture: any;
  codebase: any;
  
  // Final messages (summary after streaming completes)
  analysisSummary: string | null;
  devopsSummary: string | null;
  
  // Streaming state
  isStreaming: boolean;
  currentAction: string | null;
  
  // Actions - replay mode (pre-recorded)
  importDemoProject: (slug: string) => Promise<void>;
  // Actions - live mode (real AI)
  importLiveDemoProject: (slug: string, cloudProvider?: string) => Promise<void>;
  startDevOps: () => Promise<void>;
  reset: () => void;
  // Session restoration (survives page refresh)
  restoreSession: (slug: string) => Promise<any>;
}

const DemoContext = createContext<DemoContextType | null>(null);

// ============================================================================
// Provider
// ============================================================================

export function DemoProvider({ children }: { children: React.ReactNode }) {
  // State
  const [isDemo, setIsDemo] = useState(false);
  const [mode, setMode] = useState<DemoMode>("replay");
  const [phase, setPhase] = useState<DemoPhase>("idle");
  const [project, setProject] = useState<DemoProject | null>(null);
  const [threads, setThreads] = useState<DemoThread[]>([]);
  const [currentThread, setCurrentThread] = useState<DemoThread | null>(null);
  const [events, setEvents] = useState<DemoEvent[]>([]);
  const [tasks, setTasks] = useState<DemoTask[]>([]);
  const [architecture, setArchitecture] = useState<any>(null);
  const [codebase, setCodebase] = useState<any>(null);
  
  // Final summary messages
  const [analysisSummary, setAnalysisSummary] = useState<string | null>(null);
  const [devopsSummary, setDevopsSummary] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentAction, setCurrentAction] = useState<string | null>(null);
  
  // Refs
  const eventSourceRef = useRef<EventSource | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  
  // Track seen events to prevent duplicates (React Strict Mode can cause double-invocation)
  const seenEventsRef = useRef<Set<string>>(new Set());
  
  // =========================================================================
  // Restore session from DynamoDB (survives page refresh)
  // =========================================================================
  const restoreSession = useCallback(async (slug: string) => {
    try {
      const browserSessionId = getBrowserSessionId();
      const response = await fetch(`${API_URL}/api/demo/live/${slug}/session?browser_session_id=${browserSessionId}`);
      if (!response.ok) return null;
      
      const session = await response.json();
      console.log(`[Demo] Restored session for ${slug} (browser=${browserSessionId}):`, session);
      
      if (!session.exists) return null;
      
      // Restore project info
      setProject({
        slug: session.slug,
        name: session.slug.replace(/-/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase()),
        cloud_provider: session.cloud_provider,
        stats: {
          contracts_found: session.contracts_count,
          files_generated: session.generated_files?.length || 0,
        },
      });
      
      // Restore phase based on session state
      if (session.devops_complete) {
        setPhase("devops_complete");
        // Fetch architecture
        const archRes = await fetch(`${API_URL}/api/demo/live/${slug}/architecture?browser_session_id=${browserSessionId}`);
        if (archRes.ok) {
          setArchitecture(await archRes.json());
        }
      } else if (session.analysis_complete) {
        setPhase("analysis_complete");
        // Fetch architecture
        const archRes = await fetch(`${API_URL}/api/demo/live/${slug}/architecture?browser_session_id=${browserSessionId}`);
        if (archRes.ok) {
          setArchitecture(await archRes.json());
        }
      }
      
      setIsDemo(true);
      setMode("live");
      
      return session;
    } catch (error) {
      console.error("[Demo] Failed to restore session:", error);
      return null;
    }
  }, []);
  
  // =========================================================================
  // Stream recorded events with real timing
  // =========================================================================
  const streamEvents = useCallback(async (
    slug: string, 
    type: "analysis" | "devops",
    onEvent: (event: DemoEvent) => void,
    onComplete: () => void,
  ) => {
    // Close any existing connection first (handles React Strict Mode double-invoke)
    if (eventSourceRef.current) {
      console.log(`[Demo] Closing existing connection before starting new one`);
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    
    // Clear seen events for new stream
    seenEventsRef.current.clear();
    
    // Map type to endpoint
    const endpoint = type === "analysis" ? "analyze" : "devops";
    const url = `${API_URL}/api/demo/${slug}/${endpoint}`;
    
    console.log(`[Demo] Starting ${type} replay: POST ${url}`);
    
    try {
      // Start replay session
      const response = await fetch(url, {
        method: "POST",
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`[Demo] Failed to start replay: ${response.status} ${errorText}`);
        onComplete();
        return;
      }
      
      const data = await response.json();
      console.log(`[Demo] Replay started:`, data);
      
      const { stream_url } = data;
      
      // Connect to SSE stream
      const fullStreamUrl = `${API_URL}${stream_url}`;
      console.log(`[Demo] Connecting to SSE: ${fullStreamUrl}`);
      
      const eventSource = new EventSource(fullStreamUrl);
      eventSourceRef.current = eventSource;
      
      let lastElapsed = 0;
      
      eventSource.onopen = () => {
        console.log(`[Demo] SSE connected`);
      };
      
      eventSource.onmessage = (msg) => {
        try {
          const event: DemoEvent = JSON.parse(msg.data);
          
          if (event.type === "_session_end") {
            console.log(`[Demo] Stream ended`);
            eventSource.close();
            eventSourceRef.current = null;
            onComplete();
            return;
          }
          
          // Deduplicate events using elapsed_ms + type + content as key
          // Using ref to persist across potential re-renders
          const eventKey = `${event.elapsed_ms}-${event.type}-${event.content}`;
          if (seenEventsRef.current.has(eventKey)) {
            console.log(`[Demo] Skipping duplicate event: ${eventKey.substring(0, 50)}`);
            return; // Skip duplicate
          }
          seenEventsRef.current.add(eventKey);
          
          // Just emit events - timing is handled by backend
          onEvent(event);
          lastElapsed = event.elapsed_ms || 0;
        } catch (err) {
          console.error("[Demo] Failed to parse event:", err, msg.data);
        }
      };
      
      eventSource.onerror = (err) => {
        console.error("[Demo] SSE error:", err);
        eventSource.close();
        eventSourceRef.current = null;
        onComplete();
      };
    } catch (err) {
      console.error("[Demo] Fetch error:", err);
      onComplete();
    }
  }, []);
  
  // =========================================================================
  // Stream LIVE events (real AI calls)
  // =========================================================================
  const streamLiveEvents = useCallback(async (
    slug: string, 
    type: "analysis" | "devops",
    cloudProvider: string,
    onEvent: (event: DemoEvent) => void,
    onComplete: () => void,
  ) => {
    // Close any existing connection first
    if (eventSourceRef.current) {
      console.log(`[LiveDemo] Closing existing connection`);
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    
    seenEventsRef.current.clear();
    
    const browserSessionId = getBrowserSessionId();
    const endpoint = type === "analysis" ? "analyze" : "devops";
    const url = `${API_URL}/api/demo/live/${slug}/${endpoint}?cloud_provider=${cloudProvider}&browser_session_id=${browserSessionId}`;
    
    console.log(`[LiveDemo] Starting REAL ${type}: POST ${url} (browser=${browserSessionId})`);
    
    try {
      const response = await fetch(url, {
        method: "POST",
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`[LiveDemo] Failed to start: ${response.status} ${errorText}`);
        onComplete();
        return;
      }
      
      const data = await response.json();
      console.log(`[LiveDemo] Started:`, data);
      
      const { stream_url } = data;
      const fullStreamUrl = `${API_URL}${stream_url}`;
      console.log(`[LiveDemo] Connecting to SSE: ${fullStreamUrl}`);
      
      console.log(`[LiveDemo] Creating EventSource for: ${fullStreamUrl}`);
      const eventSource = new EventSource(fullStreamUrl);
      eventSourceRef.current = eventSource;
      
      console.log(`[LiveDemo] EventSource created, readyState=${eventSource.readyState}`);
      
      eventSource.onopen = () => {
        console.log(`[LiveDemo] SSE connected! readyState=${eventSource.readyState}`);
      };
      
      let eventCount = 0;
      eventSource.onmessage = (msg) => {
        eventCount++;
        console.log(`[LiveDemo] Raw message #${eventCount}:`, msg.data?.substring(0, 100));
        try {
          const event: DemoEvent = JSON.parse(msg.data);
          console.log(`[LiveDemo] Parsed event: type=${event.type}, content=${event.content?.substring(0, 50)}`);
          
          if (event.type === "_session_end") {
            console.log(`[LiveDemo] Stream ended after ${eventCount} events`);
            eventSource.close();
            eventSourceRef.current = null;
            onComplete();
            return;
          }
          
          // Deduplicate
          const eventKey = `${event.type}-${event.content}`;
          if (seenEventsRef.current.has(eventKey)) {
            console.log(`[LiveDemo] Skipping duplicate: ${event.type}`);
            return;
          }
          seenEventsRef.current.add(eventKey);
          
          onEvent(event);
        } catch (err) {
          console.error("[LiveDemo] Failed to parse event:", err, msg.data);
        }
      };
      
      eventSource.onerror = (err) => {
        console.error("[LiveDemo] SSE error! readyState=", eventSource.readyState, err);
        eventSource.close();
        eventSourceRef.current = null;
        onComplete();
      };
    } catch (err) {
      console.error("[LiveDemo] Fetch error:", err);
      onComplete();
    }
  }, []);
  
  // =========================================================================
  // Process events into tasks
  // =========================================================================
  const processEventToTasks = useCallback((event: DemoEvent, currentTasks: DemoTask[]): DemoTask[] => {
    const newTasks = [...currentTasks];
    
    const safeContentStr = (c: any): string => {
      if (!c) return "";
      if (typeof c === "string") return c;
      if (typeof c === "object") return c.description || c.message || c.text || c.content || c.result || JSON.stringify(c);
      return String(c);
    };
    
    if (event.type === "task_started") {
      const taskId = event.metadata?.task_id || `task-${Date.now()}`;
      if (!newTasks.find(t => t.id === taskId)) {
        newTasks.push({
          id: taskId,
          name: event.metadata?.title || safeContentStr(event.content),
          status: "in_progress",
          events: [],
        });
      }
    } else if (event.type === "task_completed") {
      const lastTask = newTasks[newTasks.length - 1];
      if (lastTask && lastTask.status !== "completed") {
        lastTask.status = "completed";
        const contentStr = safeContentStr(event.content);
        const eventKey = `${event.type}-${contentStr}`;
        if (!lastTask.events.find(e => `${e.type}-${safeContentStr(e.content)}` === eventKey)) {
          lastTask.events.push({
            type: event.type,
            content: contentStr,
            timestamp: event.timestamp,
          });
        }
      }
    } else if (["thought", "progress", "tool_result"].includes(event.type)) {
      const lastTask = newTasks[newTasks.length - 1];
      if (lastTask && lastTask.status === "in_progress") {
        const contentStr = safeContentStr(event.content);
        const eventKey = `${event.type}-${contentStr}`;
        if (!lastTask.events.find(e => `${e.type}-${safeContentStr(e.content)}` === eventKey)) {
          lastTask.events.push({
            type: event.type,
            content: contentStr,
            timestamp: event.timestamp,
          });
        }
      }
    }
    
    return newTasks;
  }, []);
  
  // =========================================================================
  // Import a demo project (triggers analysis)
  // =========================================================================
  const importDemoProject = useCallback(async (slug: string) => {
    setIsDemo(true);
    setPhase("importing");
    setEvents([]);
    setTasks([]);
    
    try {
      // Fetch project details
      const projectRes = await fetch(`${API_URL}/api/demo/${slug}`);
      if (!projectRes.ok) throw new Error("Project not found");
      const projectData = await projectRes.json();
      setProject(projectData);
      
      // Create analysis thread
      const analysisThread: DemoThread = {
        id: `demo-analysis-${slug}`,
        type: "analysis",
        thread_number: 1,
        title: `Analyzing ${projectData.name}`,
        status: "streaming",
        created_at: new Date().toISOString(),
      };
      setThreads([analysisThread]);
      setCurrentThread(analysisThread);
      
      // Start analysis phase
      setPhase("analyzing");
      setIsStreaming(true);
      
      // Dispatch event for UI to pick up
      window.dispatchEvent(new CustomEvent("demoThreadCreated", {
        detail: { thread: analysisThread, slug }
      }));
      
      // Helper to safely extract content as string
      const getContentStr = (content: unknown): string => {
        if (typeof content === "string") return content;
        if (content && typeof content === "object") {
          const obj = content as Record<string, unknown>;
          return (obj.message || obj.content || obj.text || obj.title || "") as string;
        }
        return "";
      };
      
      // Stream analysis events
      await new Promise<void>((resolve) => {
        streamEvents(slug, "analysis", 
          (event) => {
            // Update current action
            if (event.type === "thought" || event.type === "task_started") {
              setCurrentAction(getContentStr(event.content));
            }
            
            // Add event
            setEvents(prev => [...prev, event]);
            
            // Update tasks
            setTasks(prev => processEventToTasks(event, prev));
          },
          () => {
            resolve();
          }
        );
      });
      
      // Fetch architecture
      const archRes = await fetch(`${API_URL}/api/demo/${slug}/architecture`);
      if (archRes.ok) {
        const archData = await archRes.json();
        // Wrap in expected format
        setArchitecture({
          project: {
            id: `demo_${slug}`,
            name: projectData.name,
            active_version_id: "v1",
            cloud_provider: archData.cloud_provider || "gcp",
            versions: [{
              id: "v1",
              label: "Demo Version",
              status: "ready",
              design: archData,
              environments: {
                dev: { present_nodes: [], overrides: {}, extra_nodes: [], extra_edges: [] },
              }
            }]
          },
          graph: archData.graph,
          api: archData.api,
          database: archData.database,
        });
      }
      
      // Fetch the final summary message from threads
      try {
        const threadsRes = await fetch(`${API_URL}/api/demo/${slug}/threads`);
        if (threadsRes.ok) {
          const threadsData = await threadsRes.json();
          const analysisThread = threadsData.find((t: any) => t.type === "analysis");
          if (analysisThread?.message?.content) {
            setAnalysisSummary(analysisThread.message.content);
          }
          const devopsThread = threadsData.find((t: any) => t.type === "devops");
          if (devopsThread?.message?.content) {
            setDevopsSummary(devopsThread.message.content);
          }
        }
      } catch (e) {
        console.error("Failed to fetch thread summaries:", e);
      }
      
      // Complete analysis
      setIsStreaming(false);
      setCurrentAction(null);
      setPhase("analysis_complete");
      
      // Update thread status
      setThreads(prev => prev.map(t => 
        t.id === analysisThread.id ? { ...t, status: "completed" } : t
      ));
      setCurrentThread(prev => prev ? { ...prev, status: "completed" } : null);
      
      // Dispatch completion event
      window.dispatchEvent(new CustomEvent("demoAnalysisComplete", {
        detail: { slug, architecture: architecture }
      }));
      
      // Get services count from architecture for notification
      const servicesCount = architecture?.graph?.nodes?.length || 8;
      const cloudProvider = projectData.cloud_provider || "gcp";
      
      // Show notification - format matches mock notification exactly
      window.dispatchEvent(new CustomEvent("demoNotification", {
        detail: {
          type: "analysis_complete",
          title: `Architecture generated for ${projectData.name}`,
          message: `Your backend architecture has been successfully designed with ${cloudProvider.toUpperCase()} services. Ready to proceed with DevOps setup?`,
          action: "devops",
          slug,
          servicesCount,
          cloudProvider,
        }
      }));
      
    } catch (error) {
      console.error("Demo import failed:", error);
      setPhase("idle");
      setIsStreaming(false);
    }
  }, [streamEvents, processEventToTasks, architecture]);
  
  // =========================================================================
  // Import a LIVE demo project (real AI - exact same pipeline as authenticated)
  // Falls back to pre-recorded if live fails
  // =========================================================================
  const importLiveDemoProject = useCallback(async (slug: string, cloudProvider: string = "gcp") => {
    console.log(`[LiveDemo] importLiveDemoProject called: slug=${slug}, cloudProvider=${cloudProvider}`);
    
    setIsDemo(true);
    setMode("live");
    setPhase("importing");
    setEvents([]);
    setTasks([]);
    
    // Pre-recorded projects (fallback)
    const preRecordedProjects = ["ecommerce-clone"];
    
    try {
      // Set project from local demo-projects
      const projectData: DemoProject = {
        slug,
        name: slug.replace(/-/g, " ").replace(/\b\w/g, l => l.toUpperCase()),
        cloud_provider: cloudProvider,
      };
      setProject(projectData);
      
      // Create analysis thread
      const analysisThread: DemoThread = {
        id: `live-analysis-${slug}`,
        type: "analysis",
        thread_number: 1,
        title: `Analyzing ${projectData.name}`,
        status: "streaming",
        created_at: new Date().toISOString(),
      };
      setThreads([analysisThread]);
      setCurrentThread(analysisThread);
      
      // Start analysis phase
      setPhase("analyzing");
      setIsStreaming(true);
      
      // Dispatch event for UI
      window.dispatchEvent(new CustomEvent("demoThreadCreated", {
        detail: { thread: analysisThread, slug, live: true }
      }));
      
      // Helper to safely extract content as string (for live analysis)
      const extractContentString = (content: unknown): string => {
        if (typeof content === "string") return content;
        if (content && typeof content === "object") {
          const obj = content as Record<string, unknown>;
          return (obj.message || obj.content || obj.text || obj.title || "") as string;
        }
        return "";
      };
      
      // Stream LIVE analysis events
      console.log(`[LiveDemo] Starting streamLiveEvents for analysis`);
      await new Promise<void>((resolve) => {
        streamLiveEvents(slug, "analysis", cloudProvider,
          (event) => {
            const contentStr = extractContentString(event.content);
            console.log(`[LiveDemo] Event received:`, event.type, contentStr?.substring(0, 50));
            if (event.type === "thought" || event.type === "task_started") {
              setCurrentAction(contentStr);
            }
            setEvents(prev => [...prev, event]);
            setTasks(prev => processEventToTasks(event, prev));
          },
          () => {
            console.log(`[LiveDemo] Stream completed`);
            resolve();
          }
        );
      });
      
      // Fetch architecture generated by live analysis
      try {
        const browserSessionId = getBrowserSessionId();
        const archRes = await fetch(`${API_URL}/api/demo/live/${slug}/architecture?browser_session_id=${browserSessionId}`);
        if (archRes.ok) {
          const archData = await archRes.json();
          setArchitecture({
            project: {
              id: `live_${slug}`,
              name: projectData.name,
              active_version_id: "v1",
              cloud_provider: archData.cloud_provider || cloudProvider,
              versions: [{
                id: "v1",
                label: "Live Version",
                status: "ready",
                design: archData,
                environments: {
                  dev: { present_nodes: [], overrides: {}, extra_nodes: [], extra_edges: [] },
                }
              }]
            },
            graph: archData.graph,
            api: archData.api,
            database: archData.database,
          });
        }
      } catch (e) {
        console.error("[LiveDemo] Failed to fetch architecture:", e);
      }
      
      // Generate summary from last events
      const lastEvents = events.slice(-5);
      const summary = `I've analyzed your ${projectData.name} repository and designed the architecture.`;
      setAnalysisSummary(summary);
      
      // Complete analysis
      setIsStreaming(false);
      setCurrentAction(null);
      setPhase("analysis_complete");
      
      // Update thread status
      setThreads(prev => prev.map(t => 
        t.id === analysisThread.id ? { ...t, status: "completed" } : t
      ));
      setCurrentThread(prev => prev ? { ...prev, status: "completed" } : null);
      
      // Dispatch completion event
      window.dispatchEvent(new CustomEvent("demoAnalysisComplete", {
        detail: { slug, live: true }
      }));
      
      // Get services count from architecture for notification
      const servicesCount = architecture?.graph?.nodes?.length || 8;
      
      // Show notification - format matches mock notification exactly
      window.dispatchEvent(new CustomEvent("demoNotification", {
        detail: {
          type: "analysis_complete",
          title: `Architecture generated for ${projectData.name}`,
          message: `Your backend architecture has been successfully designed with ${cloudProvider.toUpperCase()} services. Ready to proceed with DevOps setup?`,
          action: "devops",
          slug,
          servicesCount,
          cloudProvider,
          live: true,
        }
      }));
      
    } catch (error) {
      console.error("Live demo import failed:", error);
      
      // Fallback to pre-recorded if available
      if (preRecordedProjects.includes(slug)) {
        console.log(`[Demo] Falling back to pre-recorded demo for ${slug}`);
        setMode("replay");
        // Retry with replay mode
        try {
          await importDemoProject(slug);
          return;
        } catch (replayError) {
          console.error("Replay fallback also failed:", replayError);
        }
      }
      
      setPhase("idle");
      setIsStreaming(false);
    }
  }, [streamLiveEvents, processEventToTasks, events, importDemoProject]);
  
  // =========================================================================
  // Start DevOps (after analysis) - supports both replay and live modes
  // =========================================================================
  const startDevOps = useCallback(async () => {
    if (!project) return;
    
    setPhase("devops");
    setEvents([]);
    setTasks([]);
    setIsStreaming(true);
    
    const isLive = mode === "live";
    
    // Create devops thread
    const devopsThread: DemoThread = {
      id: `${isLive ? 'live' : 'demo'}-devops-${project.slug}`,
      type: "devops",
      thread_number: 2,
      title: "DevOps Deployment",
      status: "streaming",
      created_at: new Date().toISOString(),
    };
    setThreads(prev => [...prev, devopsThread]);
    setCurrentThread(devopsThread);
    
    // Dispatch event
    window.dispatchEvent(new CustomEvent("demoThreadCreated", {
      detail: { thread: devopsThread, slug: project.slug, live: isLive }
    }));
    
    // Stream devops events (live or replay)
    await new Promise<void>((resolve) => {
      const streamFn = isLive ? streamLiveEvents : streamEvents;
      
      // Helper to safely extract content as string
      const getContentString = (content: unknown): string => {
        if (typeof content === "string") return content;
        if (content && typeof content === "object") {
          const obj = content as Record<string, unknown>;
          return (obj.message || obj.content || obj.text || obj.title || "") as string;
        }
        return "";
      };
      
      if (isLive) {
        streamLiveEvents(project.slug, "devops", project.cloud_provider,
          (event) => {
            if (event.type === "thought" || event.type === "task_started") {
              setCurrentAction(getContentString(event.content));
            }
            setEvents(prev => [...prev, event]);
            setTasks(prev => processEventToTasks(event, prev));
          },
          () => {
            resolve();
          }
        );
      } else {
        streamEvents(project.slug, "devops",
          (event) => {
            if (event.type === "thought" || event.type === "task_started") {
              setCurrentAction(getContentString(event.content));
            }
            setEvents(prev => [...prev, event]);
            setTasks(prev => processEventToTasks(event, prev));
          },
          () => {
            resolve();
          }
        );
      }
    });
    
    // Complete devops
    setIsStreaming(false);
    setCurrentAction(null);
    setPhase("devops_complete");
    
    // Update thread
    setThreads(prev => prev.map(t => 
      t.id === devopsThread.id ? { ...t, status: "completed" } : t
    ));
    setCurrentThread(prev => prev ? { ...prev, status: "completed" } : null);
    
    // Fetch codebase after DevOps completes (both live and replay modes)
    try {
      const browserSessionId = getBrowserSessionId();
      const codebaseEndpoint = isLive 
        ? `${API_URL}/api/demo/live/${project.slug}/codebase?browser_session_id=${browserSessionId}`
        : `${API_URL}/api/demo/${project.slug}/codebase`;
      const codebaseRes = await fetch(codebaseEndpoint);
      if (codebaseRes.ok) {
        const codebaseData = await codebaseRes.json();
        setCodebase(codebaseData);
        console.log(`[Demo] Fetched codebase:`, codebaseData);
      }
    } catch (e) {
      console.error("[Demo] Failed to fetch codebase:", e);
    }
    
    // Notification - format matches mock notification
    const cloudProvider = project.cloud_provider || "gcp";
    window.dispatchEvent(new CustomEvent("demoNotification", {
      detail: {
        type: "devops_complete",
        title: `DevOps setup complete for ${project.name}`,
        message: `Backend code has been generated and is ready for deployment to ${cloudProvider.toUpperCase()}.`,
        slug: project.slug,
        cloudProvider,
        live: isLive,
      }
    }));
    
  }, [project, mode, streamEvents, streamLiveEvents, processEventToTasks]);
  
  // =========================================================================
  // Reset
  // =========================================================================
  const reset = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsDemo(false);
    setMode("replay");
    setPhase("idle");
    setProject(null);
    setThreads([]);
    setCurrentThread(null);
    setEvents([]);
    setTasks([]);
    setArchitecture(null);
    setCodebase(null);
    setAnalysisSummary(null);
    setDevopsSummary(null);
    setIsStreaming(false);
    setCurrentAction(null);
  }, []);
  
  // Listen for external triggers (e.g., from notifications)
  useEffect(() => {
    const handleStartDevOps = () => {
      if (phase === "analysis_complete") {
        startDevOps();
      }
    };
    
    window.addEventListener("demoStartDevOps", handleStartDevOps);
    return () => {
      window.removeEventListener("demoStartDevOps", handleStartDevOps);
    };
  }, [phase, startDevOps]);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);
  
  return (
    <DemoContext.Provider value={{
      isDemo,
      mode,
      phase,
      project,
      threads,
      currentThread,
      events,
      tasks,
      architecture,
      codebase,
      analysisSummary,
      devopsSummary,
      isStreaming,
      currentAction,
      importDemoProject,
      importLiveDemoProject,
      startDevOps,
      reset,
      restoreSession,
    }}>
      {children}
    </DemoContext.Provider>
  );
}

// ============================================================================
// Hook
// ============================================================================

export function useDemo() {
  const context = useContext(DemoContext);
  if (!context) {
    throw new Error("useDemo must be used within DemoProvider");
  }
  return context;
}

// Optional hook that doesn't throw
export function useDemoOptional() {
  return useContext(DemoContext);
}
