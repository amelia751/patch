"use client";

import { useEffect, useState, useRef } from "react";
import { cn } from "@/lib/utils";
import { ThreadEvent, getThreadEventIcon, getThreadEventColor } from "@/hooks/useThreadStream";
import { Loader2, ChevronDown, ChevronRight, Sparkles } from "lucide-react";

interface StreamingIndicatorProps {
  /**
   * Whether the agent is currently streaming events.
   */
  isStreaming: boolean;
  
  /**
   * Current thought/reasoning from the agent.
   */
  currentThought?: string | null;
  
  /**
   * Current action the agent is taking.
   */
  currentAction?: string | null;
  
  /**
   * Recent events to display in the log.
   */
  events?: ThreadEvent[];
  
  /**
   * Progress indicator (e.g., 2/5 tasks).
   */
  progress?: { current: number; total: number } | null;
  
  /**
   * Maximum number of events to display.
   */
  maxDisplayEvents?: number;
  
  /**
   * Custom className for the container.
   */
  className?: string;
  
  /**
   * Whether to show in compact mode (single line).
   */
  compact?: boolean;
}

/**
 * StreamingIndicator - Shows real-time agent activity.
 *
 * Displays:
 * - Animated indicator when streaming
 * - Current thought/action
 * - Recent event log
 * - Progress indicator
 *
 * Usage:
 * ```tsx
 * <StreamingIndicator
 *   isStreaming={isStreaming}
 *   currentThought={currentThought}
 *   currentAction={currentAction}
 *   events={events.slice(-10)}
 * />
 * ```
 */
export function StreamingIndicator({
  isStreaming,
  currentThought,
  currentAction,
  events = [],
  progress,
  maxDisplayEvents = 8,
  className,
  compact = false,
}: StreamingIndicatorProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  
  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (scrollRef.current && isExpanded) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events.length, isExpanded]);

  // Get the display text (action takes priority over thought)
  const displayText = currentAction || currentThought || "";
  
  // Filter events for display (skip keepalive, limit count)
  const displayEvents = events
    .filter(e => !e.metadata?.keepalive)
    .slice(-maxDisplayEvents);

  if (!isStreaming && events.length === 0) {
    return null;
  }

  // Compact mode - single line indicator
  if (compact) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 px-3 py-2 rounded-lg",
          "bg-[var(--bg-secondary)] border border-[var(--border-color)]",
          isStreaming && "animate-pulse",
          className
        )}
      >
        {isStreaming ? (
          <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" />
        ) : (
          <Sparkles className="h-3.5 w-3.5 text-primary" />
        )}
        <span className="text-[12px] text-[var(--text-secondary)] truncate flex-1">
          {displayText || "Agent is thinking..."}
        </span>
        {progress && (
          <span className="text-[10px] text-[var(--text-tertiary)] font-mono">
            {progress.current}/{progress.total}
          </span>
        )}
      </div>
    );
  }

  // Full mode - expandable with event log
  return (
    <div
      className={cn(
        "rounded-lg overflow-hidden",
        "bg-[var(--bg-secondary)] border border-[var(--border-color)]",
        className
      )}
    >
      {/* Header - clickable to expand/collapse */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-[var(--bg-tertiary)] transition-colors"
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {isStreaming ? (
            <div className="relative">
              <Loader2 className="h-4 w-4 text-primary animate-spin" />
              <div className="absolute inset-0 animate-ping">
                <div className="h-4 w-4 rounded-full bg-primary/20" />
              </div>
            </div>
          ) : (
            <Sparkles className="h-4 w-4 text-primary" />
          )}
          
          <span className="text-[12px] font-medium text-[var(--text-primary)]">
            {isStreaming ? "Agent Working" : "Agent Activity"}
          </span>
          
          {progress && (
            <span className="text-[10px] text-[var(--text-secondary)] bg-[var(--bg-tertiary)] px-1.5 py-0.5 rounded">
              {progress.current}/{progress.total}
            </span>
          )}
        </div>
        
        {isExpanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
        )}
      </button>

      {/* Current action/thought */}
      {displayText && (
        <div className="px-3 py-2 border-t border-[var(--border-color)] bg-[var(--bg-tertiary)]/50">
          <div className="flex items-start gap-2">
            <span className="text-[12px]">
              {currentAction ? "›" : "·"}
            </span>
            <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed">
              {displayText}
            </p>
          </div>
        </div>
      )}

      {/* Event log */}
      {isExpanded && displayEvents.length > 0 && (
        <div
          ref={scrollRef}
          className="max-h-[200px] overflow-y-auto border-t border-[var(--border-color)]"
        >
          <div className="p-2 space-y-1">
            {displayEvents.map((event, idx) => (
              <EventLogItem key={`${event.timestamp}-${idx}`} event={event} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Single event item in the log.
 */
function EventLogItem({ event }: { event: ThreadEvent }) {
  const icon = getThreadEventIcon(event.type);
  const colorClass = getThreadEventColor(event.type);
  
  // Safely extract content as string (handle object content)
  const rawContent = event.content;
  let content: string = typeof rawContent === "string" 
    ? rawContent 
    : (rawContent?.message || rawContent?.content || rawContent?.text || rawContent?.output || 
       rawContent?.filename || rawContent?.command || rawContent?.result || 
       (rawContent ? JSON.stringify(rawContent) : ""));
  
  // Format content based on event type (specific overrides)
  if (event.type === "code_generated" && event.metadata?.filename) {
    content = `Generated ${event.metadata.filename}`;
  }
  
  if (event.type === "command_run") {
    content = event.metadata?.command || content;
  }
  
  if (event.type === "resource_created") {
    content = `Created ${event.metadata?.resource_type}: ${event.metadata?.resource_name}`;
  }
  
  if (event.type === "file_create") {
    const filename = typeof rawContent === "object" ? rawContent?.filename : "";
    content = filename ? `Writing ${filename}` : content;
  }
  
  if (event.type === "cli_command") {
    const cmd = typeof rawContent === "object" ? rawContent?.command : rawContent;
    content = typeof cmd === "string" ? `$ ${cmd}` : content;
  }

  return (
    <div className="flex items-start gap-2 py-0.5">
      <span className="text-[11px] shrink-0">{icon}</span>
      <span className={cn("text-[11px] leading-relaxed", colorClass)}>
        {content}
      </span>
      {event.metadata?.duration && (
        <span className="text-[9px] text-[var(--text-secondary)] ml-auto shrink-0">
          {event.metadata.duration}
        </span>
      )}
    </div>
  );
}


/**
 * Inline streaming indicator for use within messages.
 * Shows a minimal animated indicator when agent is working.
 */
export function InlineStreamingIndicator({
  isStreaming,
  text,
  className,
}: {
  isStreaming: boolean;
  text?: string;
  className?: string;
}) {
  if (!isStreaming) return null;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-1 rounded-full",
        "bg-primary/10 text-primary",
        className
      )}
    >
      <div className="flex gap-0.5">
        <span className="h-1.5 w-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: "0ms" }} />
        <span className="h-1.5 w-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: "150ms" }} />
        <span className="h-1.5 w-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: "300ms" }} />
      </div>
      {text && (
        <span className="text-[11px] font-medium">{text}</span>
      )}
    </div>
  );
}


/**
 * Floating streaming indicator that can be positioned anywhere.
 * Shows current action with a pulsing animation.
 */
export function FloatingStreamingIndicator({
  isStreaming,
  currentAction,
  className,
}: {
  isStreaming: boolean;
  currentAction?: string | null;
  className?: string;
}) {
  if (!isStreaming) return null;

  return (
    <div
      className={cn(
        "fixed bottom-4 right-4 flex items-center gap-2 px-4 py-2.5 rounded-full",
        "bg-[var(--bg-primary)] border border-[var(--border-color)] shadow-lg",
        "animate-in fade-in slide-in-from-bottom-2 duration-300",
        className
      )}
    >
      <div className="relative">
        <Loader2 className="h-4 w-4 text-primary animate-spin" />
        <div className="absolute inset-0 animate-ping">
          <div className="h-4 w-4 rounded-full bg-primary/30" />
        </div>
      </div>
      <span className="text-[12px] text-[var(--text-primary)] max-w-[200px] truncate">
        {currentAction || "Working..."}
      </span>
    </div>
  );
}
